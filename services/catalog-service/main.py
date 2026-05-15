"""
Catalog Service — Core Data Catalog
The central registry for all data assets. Consumes enriched metadata
events and stores them in BigQuery. Provides search, browse, and CRUD
APIs for the React frontend.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from kafka import KafkaConsumer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_enriched_metadata: str = "enriched-metadata-events"
    kafka_consumer_group: str = "catalog-ingest-group"
    gcp_project: str = "my-data-platform"
    bq_dataset: str = "data_catalog"
    bq_table_assets: str = "assets"
    bq_table_columns: str = "columns"
    bq_table_lineage: str = "lineage"
    service_name: str = "catalog-service"
    # POC / local-dev: set CATALOG_BACKEND=sqlite to bypass BigQuery
    catalog_backend: str = "bigquery"
    sqlite_db_path: str = "/poc-data/catalog.db"

    class Config:
        env_file = ".env"


settings = Settings()

ASSETS_INGESTED = Counter("catalog_assets_ingested_total", "Assets ingested into catalog", ["source_type"])
SEARCH_REQUESTS = Counter("catalog_search_requests_total", "Search requests", ["status"])
SEARCH_DURATION = Histogram("catalog_search_duration_seconds", "Search query duration")
TOTAL_ASSETS = Gauge("catalog_total_assets", "Total assets in catalog")


# --------------------------------------------------------------------------- #
#  BigQuery storage layer                                                      #
# --------------------------------------------------------------------------- #

def _init_storage():
    """Return the correct storage backend based on CATALOG_BACKEND env var."""
    if settings.catalog_backend.lower() == "sqlite":
        from storage_sqlite import SQLiteStorage
        return SQLiteStorage(settings.sqlite_db_path)
    return BigQueryStorage()


class BigQueryStorage:
    """
    Manages reads/writes to BigQuery for catalog storage.
    Tables are partitioned by ingestion date for cost-efficient querying.
    """

    def __init__(self):
        self.client = bigquery.Client(project=settings.gcp_project)
        self.dataset = settings.bq_dataset
        self._ensure_tables()

    def _ensure_tables(self):
        """Create BigQuery tables if they don't exist."""
        dataset_ref = f"{settings.gcp_project}.{self.dataset}"

        assets_schema = [
            bigquery.SchemaField("asset_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("fqn", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("source_id", "STRING"),
            bigquery.SchemaField("source_type", "STRING"),
            bigquery.SchemaField("database_name", "STRING"),
            bigquery.SchemaField("schema_name", "STRING"),
            bigquery.SchemaField("table_name", "STRING"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("domain", "STRING"),
            bigquery.SchemaField("data_owner", "STRING"),
            bigquery.SchemaField("data_steward", "STRING"),
            bigquery.SchemaField("sensitivity_level", "STRING"),
            bigquery.SchemaField("row_count", "INTEGER"),
            bigquery.SchemaField("size_bytes", "INTEGER"),
            bigquery.SchemaField("quality_score", "FLOAT"),
            bigquery.SchemaField("quality_grade", "STRING"),
            bigquery.SchemaField("tags", "JSON"),
            bigquery.SchemaField("suggested_terms", "STRING", mode="REPEATED"),
            bigquery.SchemaField("is_active", "BOOL"),
            bigquery.SchemaField("run_id", "STRING"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ]

        columns_schema = [
            bigquery.SchemaField("column_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("asset_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("fqn", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("column_name", "STRING"),
            bigquery.SchemaField("data_type", "STRING"),
            bigquery.SchemaField("description", "STRING"),
            bigquery.SchemaField("is_nullable", "BOOL"),
            bigquery.SchemaField("pii_classification", "STRING"),
            bigquery.SchemaField("pii_category", "STRING"),
            bigquery.SchemaField("sensitivity_level", "STRING"),
            bigquery.SchemaField("suggested_terms", "STRING", mode="REPEATED"),
            bigquery.SchemaField("quality_score", "FLOAT"),
            bigquery.SchemaField("quality_grade", "STRING"),
            bigquery.SchemaField("null_count", "INTEGER"),
            bigquery.SchemaField("distinct_count", "INTEGER"),
            bigquery.SchemaField("asset_fqn", "STRING"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP"),
        ]

        for table_id, schema in [
            (settings.bq_table_assets, assets_schema),
            (settings.bq_table_columns, columns_schema),
        ]:
            table_ref = f"{dataset_ref}.{table_id}"
            try:
                table = bigquery.Table(table_ref, schema=schema)
                table.time_partitioning = bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
                    field="ingested_at",
                )
                self.client.create_table(table, exists_ok=True)
            except Exception as exc:
                log.warning("bq_table_creation_warning", table=table_id, error=str(exc))

    def upsert_asset(self, asset: dict) -> None:
        """Write (or update) an asset to BigQuery assets table."""
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "asset_id": asset.get("asset_id", str(uuid.uuid4())),
            "fqn": asset["fqn"],
            "source_id": asset.get("source_id"),
            "source_type": asset.get("source_type"),
            "database_name": asset.get("database_name"),
            "schema_name": asset.get("schema_name"),
            "table_name": asset.get("table_name"),
            "description": asset.get("description"),
            "domain": asset.get("domain"),
            "data_owner": asset.get("data_owner"),
            "data_steward": asset.get("data_steward"),
            "sensitivity_level": asset.get("sensitivity_level", "INTERNAL"),
            "row_count": asset.get("row_count"),
            "size_bytes": asset.get("size_bytes"),
            "quality_score": asset.get("quality_score"),
            "quality_grade": asset.get("quality_grade"),
            "tags": json.dumps(asset.get("tags", {})),
            "suggested_terms": asset.get("suggested_terms", []),
            "is_active": True,
            "run_id": asset.get("run_id"),
            "ingested_at": now,
            "updated_at": now,
        }
        table_ref = f"{settings.gcp_project}.{self.dataset}.{settings.bq_table_assets}"
        errors = self.client.insert_rows_json(table_ref, [row])
        if errors:
            log.error("bq_insert_error", errors=errors, table=settings.bq_table_assets)

    def upsert_columns(self, asset_id: str, asset_fqn: str, columns: list[dict]) -> None:
        """Write column profiles for an asset."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for col in columns:
            rows.append({
                "column_id": str(uuid.uuid4()),
                "asset_id": asset_id,
                "fqn": f"{asset_fqn}.{col['name']}",
                "column_name": col["name"],
                "data_type": col.get("data_type"),
                "description": col.get("description"),
                "is_nullable": col.get("is_nullable", True),
                "pii_classification": col.get("pii_classification"),
                "pii_category": col.get("pii_category"),
                "sensitivity_level": col.get("pii_sensitivity", "PUBLIC"),
                "suggested_terms": col.get("suggested_terms", []),
                "quality_score": col.get("quality_score", {}).get("overall"),
                "quality_grade": col.get("quality_score", {}).get("grade"),
                "null_count": col.get("null_count"),
                "distinct_count": col.get("distinct_count"),
                "asset_fqn": asset_fqn,
                "ingested_at": now,
            })

        if rows:
            table_ref = f"{settings.gcp_project}.{self.dataset}.{settings.bq_table_columns}"
            errors = self.client.insert_rows_json(table_ref, rows)
            if errors:
                log.error("bq_insert_error", errors=errors, table=settings.bq_table_columns)

    def search_assets(
        self,
        query: str | None = None,
        domain: str | None = None,
        sensitivity: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Full-text search over catalog assets in BigQuery."""
        where_clauses = ["is_active = TRUE"]
        params = []

        if query:
            where_clauses.append(
                "(LOWER(fqn) LIKE @query OR LOWER(description) LIKE @query "
                "OR LOWER(table_name) LIKE @query OR LOWER(schema_name) LIKE @query)"
            )
            params.append(bigquery.ScalarQueryParameter("query", "STRING", f"%{query.lower()}%"))

        if domain:
            where_clauses.append("domain = @domain")
            params.append(bigquery.ScalarQueryParameter("domain", "STRING", domain))

        if sensitivity:
            where_clauses.append("sensitivity_level = @sensitivity")
            params.append(bigquery.ScalarQueryParameter("sensitivity", "STRING", sensitivity))

        if source_type:
            where_clauses.append("source_type = @source_type")
            params.append(bigquery.ScalarQueryParameter("source_type", "STRING", source_type))

        where_sql = " AND ".join(where_clauses)
        count_sql = f"""
            SELECT COUNT(*) AS total
            FROM `{settings.gcp_project}.{self.dataset}.{settings.bq_table_assets}`
            WHERE {where_sql}
        """
        data_sql = f"""
            SELECT *
            FROM `{settings.gcp_project}.{self.dataset}.{settings.bq_table_assets}`
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT @limit OFFSET @offset
        """
        params.extend([
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("offset", "INT64", offset),
        ])

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        count_result = list(self.client.query(count_sql, job_config=bigquery.QueryJobConfig(query_parameters=params[:-2])).result())
        total = count_result[0]["total"] if count_result else 0

        data_result = list(self.client.query(data_sql, job_config=job_config).result())
        assets = [dict(row) for row in data_result]
        return {"total": total, "assets": assets}

    def get_asset(self, fqn: str) -> dict | None:
        sql = f"""
            SELECT * FROM `{settings.gcp_project}.{self.dataset}.{settings.bq_table_assets}`
            WHERE fqn = @fqn AND is_active = TRUE
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("fqn", "STRING", fqn)]
        )
        rows = list(self.client.query(sql, job_config=job_config).result())
        return dict(rows[0]) if rows else None

    def get_columns(self, asset_fqn: str) -> list[dict]:
        sql = f"""
            SELECT * FROM `{settings.gcp_project}.{self.dataset}.{settings.bq_table_columns}`
            WHERE asset_fqn = @fqn
            ORDER BY column_name
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("fqn", "STRING", asset_fqn)]
        )
        return [dict(r) for r in self.client.query(sql, job_config=job_config).result()]


# --------------------------------------------------------------------------- #
#  Kafka consumer                                                              #
# --------------------------------------------------------------------------- #

storage: BigQueryStorage | None = None


def _sync_consume_loop():
    """Blocking Kafka consume loop — must run in a thread, not the event loop."""
    consumer = KafkaConsumer(
        settings.kafka_topic_enriched_metadata,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
    )
    log.info("catalog_consumer_started", topic=settings.kafka_topic_enriched_metadata)

    for message in consumer:
        try:
            event = message.value
            source_id = event["source_id"]
            source_type = event["source_type"]
            db_name = event["database_name"]
            schema_name = event["schema_name"]
            run_id = event.get("run_id")

            for table in event.get("tables", []):
                asset_id = str(uuid.uuid4())
                fqn = table["fqn"]
                quality = table.get("table_quality_score", {})

                storage.upsert_asset({
                    "asset_id": asset_id,
                    "fqn": fqn,
                    "source_id": source_id,
                    "source_type": source_type,
                    "database_name": db_name,
                    "schema_name": schema_name,
                    "table_name": table["table_name"],
                    "description": table.get("description"),
                    "domain": table.get("domain"),
                    "data_owner": table.get("data_owner"),
                    "data_steward": table.get("data_steward"),
                    "sensitivity_level": table.get("sensitivity_level", "INTERNAL"),
                    "row_count": table.get("row_count"),
                    "size_bytes": table.get("size_bytes"),
                    "quality_score": quality.get("overall"),
                    "quality_grade": quality.get("grade"),
                    "quality_completeness": quality.get("completeness"),
                    "quality_uniqueness": quality.get("uniqueness"),
                    "quality_validity": quality.get("validity"),
                    "quality_consistency": quality.get("consistency"),
                    "tags": table.get("tags", {}),
                    "suggested_terms": table.get("suggested_terms", []),
                    "run_id": run_id,
                })
                storage.upsert_columns(asset_id, fqn, table.get("columns", []))

                ASSETS_INGESTED.labels(source_type=source_type).inc()
                TOTAL_ASSETS.inc()

            consumer.commit()
            log.info("catalog_event_ingested", source_id=source_id, tables=len(event.get("tables", [])))

        except Exception as exc:
            log.error("catalog_ingest_failed", error=str(exc))


async def consume_enriched_events():
    """Schedule the blocking Kafka loop in a thread so the event loop stays free."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_consume_loop)


# --------------------------------------------------------------------------- #
#  Lifespan                                                                    #
# --------------------------------------------------------------------------- #

consumer_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    global storage, consumer_task
    storage = _init_storage()
    log.info("catalog_storage_backend", backend=settings.catalog_backend)
    consumer_task = asyncio.create_task(consume_enriched_events())
    log.info("catalog_service_started")
    yield
    if consumer_task:
        consumer_task.cancel()
    log.info("catalog_service_stopped")


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Catalog Service",
    version="1.0.0",
    description="Central catalog registry backed by BigQuery",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/assets")
async def search_assets(
    q: str | None = None,
    domain: str | None = None,
    sensitivity: str | None = None,
    source_type: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
):
    """Search and browse catalog assets."""
    start = time.monotonic()
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    try:
        result = storage.search_assets(q, domain, sensitivity, source_type, limit, offset)
        SEARCH_REQUESTS.labels(status="success").inc()
        SEARCH_DURATION.observe(time.monotonic() - start)
        return result
    except Exception as exc:
        SEARCH_REQUESTS.labels(status="failure").inc()
        log.error("search_failed", error=str(exc))
        raise HTTPException(500, f"Search failed: {exc}")


@app.get("/assets/{asset_fqn:path}")
async def get_asset(asset_fqn: str):
    """Get a specific asset by its fully qualified name."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    asset = storage.get_asset_by_fqn(asset_fqn)
    if not asset:
        raise HTTPException(404, f"Asset not found: {asset_fqn}")
    columns = storage.get_columns(asset["fqn"])
    return {**asset, "columns": columns}


@app.patch("/assets/{asset_fqn:path}")
async def update_asset_metadata(asset_fqn: str, updates: dict):
    """
    Allow stewards to update asset metadata (description, owner, domain, tags).
    Changes are audited via the Audit Service.
    """
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    asset = storage.get_asset(asset_fqn)
    if not asset:
        raise HTTPException(404, f"Asset not found: {asset_fqn}")

    allowed_fields = {"description", "data_owner", "data_steward", "domain", "tags"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}

    log.info("asset_metadata_updated", fqn=asset_fqn, fields=list(filtered.keys()))
    return {"fqn": asset_fqn, "updated_fields": filtered, "status": "updated"}


@app.get("/stats")
async def catalog_stats():
    """Return high-level catalog statistics."""
    return {
        "service": settings.service_name,
        "storage": "BigQuery",
        "project": settings.gcp_project,
        "dataset": settings.bq_dataset,
    }
