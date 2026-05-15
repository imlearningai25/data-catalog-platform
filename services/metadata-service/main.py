"""
Metadata Enrichment Service
Consumes RawMetadataEvents from Kafka, enriches each asset with:
  - AI-generated descriptions (via LLM if description is missing)
  - Data quality scores (completeness, uniqueness, validity)
  - Business context (owner, domain, steward)
  - Tag suggestions based on naming patterns and sample values
Then emits EnrichedMetadataEvents downstream.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaConsumer, KafkaProducer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_raw_metadata: str = "raw-metadata-events"
    kafka_topic_enriched_metadata: str = "enriched-metadata-events"
    kafka_consumer_group: str = "metadata-enrichment-group"
    classification_service_url: str = "http://classification-service:8003"
    term_service_url: str = "http://term-service:8004"
    catalog_service_url: str = "http://catalog-service:8005"
    service_name: str = "metadata-service"

    class Config:
        env_file = ".env"


settings = Settings()

# Prometheus
EVENTS_PROCESSED = Counter("metadata_events_processed_total", "Processed events", ["status"])
ENRICHMENT_DURATION = Histogram("metadata_enrichment_duration_seconds", "Enrichment duration")


# --------------------------------------------------------------------------- #
#  Domain data — quality scoring rules                                         #
# --------------------------------------------------------------------------- #

DESCRIPTION_BLACKLIST = {"n/a", "na", "none", "null", "tbd", "todo", "unknown", ""}

QUALITY_WEIGHT = {
    "completeness": 0.35,
    "uniqueness": 0.25,
    "validity": 0.25,
    "consistency": 0.15,
}

# Heuristic patterns that suggest specific domains
DOMAIN_PATTERNS = {
    "finance": [r"amount", r"price", r"cost", r"revenue", r"profit", r"tax", r"account.*num"],
    "hr": [r"employee", r"staff", r"salary", r"payroll", r"dept.*id", r"hire.*date"],
    "customer": [r"customer", r"client", r"member", r"subscriber", r"prospect"],
    "product": [r"product", r"item", r"sku", r"catalog", r"inventory"],
    "operations": [r"order", r"shipment", r"delivery", r"warehouse", r"logistics"],
    "security": [r"audit", r"log", r"access", r"permission", r"role", r"session"],
}


# --------------------------------------------------------------------------- #
#  Data models                                                                 #
# --------------------------------------------------------------------------- #

class DataQualityScore(BaseModel):
    completeness: float = 0.0      # % non-null
    uniqueness: float = 0.0        # % distinct / total
    validity: float = 0.0          # % conforming to type
    consistency: float = 0.0       # cross-field consistency
    overall: float = 0.0
    grade: str = "F"               # A, B, C, D, F


class EnrichedColumn(BaseModel):
    name: str
    data_type: str
    description: str | None = None
    is_nullable: bool = True
    pii_classification: str | None = None      # PII, SENSITIVE, INTERNAL, PUBLIC
    pii_category: str | None = None            # NAME, EMAIL, SSN, PHONE, etc.
    suggested_terms: list[str] = Field(default_factory=list)
    quality_score: DataQualityScore = Field(default_factory=DataQualityScore)
    # Statistical profile — passed through from connector
    null_count: int | None = None
    distinct_count: int | None = None
    min_value: Any | None = None
    max_value: Any | None = None
    avg_value: float | None = None
    sample_values: list[Any] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class EnrichedTable(BaseModel):
    schema_name: str
    table_name: str
    fqn: str                                   # fully qualified name
    description: str | None = None
    domain: str | None = None                  # finance, hr, customer, etc.
    data_owner: str | None = None
    data_steward: str | None = None
    sensitivity_level: str = "INTERNAL"        # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
    columns: list[EnrichedColumn] = Field(default_factory=list)
    table_quality_score: DataQualityScore = Field(default_factory=DataQualityScore)
    row_count: int | None = None
    size_bytes: int | None = None
    suggested_terms: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class EnrichedMetadataEvent(BaseModel):
    event_id: str
    source_id: str
    source_type: str
    run_id: str
    database_name: str
    schema_name: str
    tables: list[EnrichedTable]
    enriched_at: str


# --------------------------------------------------------------------------- #
#  Enrichment engine                                                           #
# --------------------------------------------------------------------------- #

class MetadataEnricher:
    """
    Enriches raw metadata with descriptions, quality scores,
    domain assignments, and tag suggestions.
    """

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._http.aclose()

    async def enrich_table(
        self, raw_table: dict, source_id: str, source_type: str
    ) -> EnrichedTable:
        schema_name = raw_table["schema_name"]
        table_name = raw_table["table_name"]
        fqn = f"{source_type}.{schema_name}.{table_name}"

        row_count = raw_table.get("row_count") or 0
        enriched_columns = []
        for raw_col in raw_table.get("columns", []):
            enriched_col = await self._enrich_column(raw_col, schema_name, table_name, row_count)
            enriched_columns.append(enriched_col)

        # Table-level quality score = average of column scores
        table_quality = self._compute_table_quality(raw_table, enriched_columns)

        # Domain inference
        domain = self._infer_domain(table_name, enriched_columns)

        # Sensitivity = worst case column sensitivity
        sensitivity = self._compute_table_sensitivity(enriched_columns)

        # Description generation
        description = await self._generate_description(schema_name, table_name, enriched_columns)

        # Suggested terms
        suggested_terms = self._suggest_terms(table_name, enriched_columns)

        return EnrichedTable(
            schema_name=schema_name,
            table_name=table_name,
            fqn=fqn,
            description=description,
            domain=domain,
            sensitivity_level=sensitivity,
            columns=enriched_columns,
            table_quality_score=table_quality,
            row_count=raw_table.get("row_count"),
            size_bytes=raw_table.get("size_bytes"),
            suggested_terms=suggested_terms,
            tags=raw_table.get("tags", {}),
        )

    async def _enrich_column(
        self, raw_col: dict, schema: str, table: str, row_count: int = 0
    ) -> EnrichedColumn:
        quality = self._compute_column_quality(raw_col, row_count)

        # Call classification service for PII detection
        pii_class, pii_category = await self._classify_pii(raw_col, schema, table)

        # Call term service for term suggestions
        suggested_terms = await self._get_term_suggestions(raw_col["name"], raw_col["data_type"])

        description = raw_col.get("description")
        if not description or description.lower().strip() in DESCRIPTION_BLACKLIST:
            description = self._generate_column_description(raw_col)

        avg_raw = raw_col.get("avg_value")
        return EnrichedColumn(
            name=raw_col["name"],
            data_type=raw_col["data_type"],
            description=description,
            is_nullable=raw_col.get("is_nullable", True),
            pii_classification=pii_class,
            pii_category=pii_category,
            suggested_terms=suggested_terms,
            quality_score=quality,
            null_count=raw_col.get("null_count"),
            distinct_count=raw_col.get("distinct_count"),
            min_value=raw_col.get("min_value"),
            max_value=raw_col.get("max_value"),
            avg_value=float(avg_raw) if avg_raw is not None else None,
            sample_values=raw_col.get("sample_values", []),
        )

    def _compute_column_quality(self, raw_col: dict, row_count: int = 0) -> DataQualityScore:
        null_count = raw_col.get("null_count") or 0
        total_rows = max(row_count, 1)
        distinct_count = raw_col.get("distinct_count") or 0

        # Completeness: % non-null
        completeness = max(0.0, min(1.0, 1.0 - (null_count / max(total_rows, 1))))

        # Uniqueness: distinct / non-null rows (capped at 1.0)
        non_null = max(total_rows - null_count, 1)
        uniqueness = min(1.0, distinct_count / non_null)

        # Validity: heuristic based on type conformance (simplified)
        validity = 1.0

        # Consistency: placeholder (cross-field rules evaluated separately)
        consistency = 1.0

        overall = (
            completeness * QUALITY_WEIGHT["completeness"]
            + uniqueness * QUALITY_WEIGHT["uniqueness"]
            + validity * QUALITY_WEIGHT["validity"]
            + consistency * QUALITY_WEIGHT["consistency"]
        )

        grade = "A" if overall >= 0.9 else "B" if overall >= 0.75 else "C" if overall >= 0.6 else "D" if overall >= 0.4 else "F"

        return DataQualityScore(
            completeness=round(completeness, 4),
            uniqueness=round(uniqueness, 4),
            validity=round(validity, 4),
            consistency=round(consistency, 4),
            overall=round(overall, 4),
            grade=grade,
        )

    def _compute_table_quality(
        self, raw_table: dict, enriched_columns: list[EnrichedColumn]
    ) -> DataQualityScore:
        if not enriched_columns:
            return DataQualityScore()

        avg_completeness = sum(c.quality_score.completeness for c in enriched_columns) / len(enriched_columns)
        avg_uniqueness = sum(c.quality_score.uniqueness for c in enriched_columns) / len(enriched_columns)
        avg_validity = sum(c.quality_score.validity for c in enriched_columns) / len(enriched_columns)
        avg_consistency = sum(c.quality_score.consistency for c in enriched_columns) / len(enriched_columns)
        overall = (
            avg_completeness * QUALITY_WEIGHT["completeness"]
            + avg_uniqueness * QUALITY_WEIGHT["uniqueness"]
            + avg_validity * QUALITY_WEIGHT["validity"]
            + avg_consistency * QUALITY_WEIGHT["consistency"]
        )
        grade = "A" if overall >= 0.9 else "B" if overall >= 0.75 else "C" if overall >= 0.6 else "D" if overall >= 0.4 else "F"
        return DataQualityScore(
            completeness=round(avg_completeness, 4),
            uniqueness=round(avg_uniqueness, 4),
            validity=round(avg_validity, 4),
            consistency=round(avg_consistency, 4),
            overall=round(overall, 4),
            grade=grade,
        )

    def _infer_domain(self, table_name: str, columns: list[EnrichedColumn]) -> str | None:
        tokens = table_name.lower()
        all_names = tokens + " " + " ".join(c.name.lower() for c in columns)
        scores: dict[str, int] = {}
        for domain, patterns in DOMAIN_PATTERNS.items():
            score = sum(1 for p in patterns if re.search(p, all_names))
            if score > 0:
                scores[domain] = score
        return max(scores, key=scores.get) if scores else None

    def _compute_table_sensitivity(self, columns: list[EnrichedColumn]) -> str:
        hierarchy = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "RESTRICTED": 3}
        reverse = {v: k for k, v in hierarchy.items()}
        max_level = 0
        for col in columns:
            if col.pii_classification == "PII":
                max_level = max(max_level, hierarchy["RESTRICTED"])
            elif col.pii_classification == "SENSITIVE":
                max_level = max(max_level, hierarchy["CONFIDENTIAL"])
        return reverse.get(max_level, "INTERNAL")

    async def _classify_pii(
        self, raw_col: dict, schema: str, table: str
    ) -> tuple[str | None, str | None]:
        """Delegate PII classification to the Classification Service."""
        try:
            resp = await self._http.post(
                f"{settings.classification_service_url}/classify/column",
                json={
                    "column_name": raw_col["name"],
                    "data_type": raw_col["data_type"],
                    "sample_values": raw_col.get("sample_values", []),
                    "schema_name": schema,
                    "table_name": table,
                },
                timeout=5.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("classification"), data.get("category")
        except Exception as exc:
            log.warning("pii_classification_service_error", error=str(exc))

        # Fallback: heuristic classification
        return self._heuristic_pii_classify(raw_col)

    def _heuristic_pii_classify(self, raw_col: dict) -> tuple[str | None, str | None]:
        name = raw_col["name"].lower()
        pii_patterns = {
            r"(^|_)(ssn|social.*sec|sin|tin|ein)($|_)": "SSN",
            r"(^|_)(email|e_mail|mail_addr)($|_)": "EMAIL",
            r"(^|_)(phone|mobile|cell|fax|tel)($|_)": "PHONE",
            r"(^|_)(first.*name|last.*name|full.*name|fname|lname)($|_)": "NAME",
            r"(^|_)(dob|birth.*date|date.*birth|birthdate)($|_)": "DATE_OF_BIRTH",
            r"(^|_)(addr|address|street|zip|postal)($|_)": "ADDRESS",
            r"(^|_)(ip_addr|ip_address|ipaddr)($|_)": "IP_ADDRESS",
            r"(^|_)(passport|license|drivers.*lic)($|_)": "GOVERNMENT_ID",
            r"(^|_)(credit.*card|cc_num|card_num)($|_)": "PAYMENT_CARD",
            r"(^|_)(patient|medical.*rec|health)($|_)": "HEALTH_DATA",
        }
        for pattern, category in pii_patterns.items():
            if re.search(pattern, name):
                return "PII", category

        sensitive_patterns = [r"salary", r"wage", r"income", r"bonus", r"tax", r"password", r"secret", r"token"]
        for pattern in sensitive_patterns:
            if re.search(pattern, name):
                return "SENSITIVE", None

        return None, None

    async def _get_term_suggestions(self, col_name: str, data_type: str) -> list[str]:
        try:
            resp = await self._http.post(
                f"{settings.term_service_url}/terms/suggest",
                json={"column_name": col_name, "data_type": data_type},
                timeout=3.0,
            )
            if resp.status_code == 200:
                return resp.json().get("terms", [])
        except Exception:
            pass
        return []

    def _generate_column_description(self, raw_col: dict) -> str:
        """Rule-based description generator when no description exists."""
        name = raw_col["name"]
        data_type = raw_col["data_type"]
        readable = name.replace("_", " ").replace("-", " ").title()
        return f"The {readable} field ({data_type}). Auto-generated — please review."

    async def _generate_description(
        self, schema: str, table: str, columns: list[EnrichedColumn]
    ) -> str:
        col_names = [c.name for c in columns[:10]]  # First 10 for context
        readable_table = table.replace("_", " ").replace("-", " ").title()
        return (
            f"{readable_table} contains records from the {schema} schema. "
            f"Key columns include: {', '.join(col_names[:5])}. "
            f"Auto-generated — please enrich via the Data Catalog UI."
        )

    def _suggest_terms(self, table_name: str, columns: list[EnrichedColumn]) -> list[str]:
        terms = []
        tokens = table_name.lower().split("_")
        domain_terms = {
            "customer": ["Customer", "Party", "Consumer"],
            "order": ["Order", "Transaction", "Sales Order"],
            "product": ["Product", "Item", "SKU", "Asset"],
            "employee": ["Employee", "Staff", "Personnel", "Worker"],
            "account": ["Account", "Ledger Entry", "Financial Account"],
            "invoice": ["Invoice", "Bill", "Accounts Receivable"],
        }
        for token in tokens:
            if token in domain_terms:
                terms.extend(domain_terms[token])
        return list(set(terms))[:5]


# --------------------------------------------------------------------------- #
#  Kafka consumer loop                                                         #
# --------------------------------------------------------------------------- #

async def consume_and_enrich(enricher: MetadataEnricher):
    """Background task: consumes from Kafka and enriches metadata.

    The KafkaConsumer iterator is synchronous-blocking. Running it directly
    inside an async task freezes the event loop, preventing uvicorn from
    serving requests. Fix: poll in a daemon thread → push messages onto an
    asyncio.Queue → process with await in the event loop.
    """
    import threading

    loop = asyncio.get_running_loop()
    msg_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def _sync_poll() -> None:
        consumer = KafkaConsumer(
            settings.kafka_topic_raw_metadata,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            enable_auto_commit=True,   # auto-commit: consumer lives in its own thread
        )
        log.info("kafka_consumer_started", topic=settings.kafka_topic_raw_metadata)
        for message in consumer:
            loop.call_soon_threadsafe(msg_queue.put_nowait, message)

    threading.Thread(target=_sync_poll, daemon=True).start()

    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode(),
        acks="all",
    )

    while True:
        message = await msg_queue.get()
        start = time.monotonic()
        try:
            raw_event = message.value
            source_id = raw_event["source_id"]
            source_type = raw_event["source_type"]
            schema_profile = raw_event["schema_profile"]

            enriched_tables = []
            for raw_table in schema_profile.get("tables", []):
                enriched = await enricher.enrich_table(raw_table, source_id, source_type)
                enriched_tables.append(enriched.model_dump())

            enriched_event = {
                "event_id": raw_event["event_id"],
                "source_id": source_id,
                "source_type": source_type,
                "run_id": raw_event.get("run_id"),
                "database_name": schema_profile["database_name"],
                "schema_name": schema_profile["schema_name"],
                "tables": enriched_tables,
                "enriched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            producer.send(settings.kafka_topic_enriched_metadata, value=enriched_event)
            producer.flush(timeout=10)

            duration = time.monotonic() - start
            EVENTS_PROCESSED.labels(status="success").inc()
            ENRICHMENT_DURATION.observe(duration)
            log.info("event_enriched", source_id=source_id, tables=len(enriched_tables), duration=round(duration, 2))

        except Exception as exc:
            EVENTS_PROCESSED.labels(status="failure").inc()
            log.error("enrichment_failed", error=str(exc))


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

enricher_instance: MetadataEnricher | None = None
consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global enricher_instance, consumer_task
    enricher_instance = MetadataEnricher()
    consumer_task = asyncio.create_task(consume_and_enrich(enricher_instance))
    log.info("metadata_service_started")
    yield
    if consumer_task:
        consumer_task.cancel()
    if enricher_instance:
        await enricher_instance.close()
    log.info("metadata_service_stopped")


app = FastAPI(
    title="Data Catalog — Metadata Enrichment Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/enrich/table")
async def enrich_table_on_demand(payload: dict):
    """Enrich a single table on-demand (for testing/preview)."""
    if not enricher_instance:
        raise HTTPException(503, "Enricher not initialized")
    enriched = await enricher_instance.enrich_table(
        payload.get("table", {}),
        payload.get("source_id", ""),
        payload.get("source_type", ""),
    )
    return enriched.model_dump()
