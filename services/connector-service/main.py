"""
Connector Service — FastAPI application
Responsibilities:
  - Manage data source connections
  - Trigger schema hydration jobs
  - Emit RawMetadataEvents to Kafka
  - Expose health/metrics endpoints

All endpoints are protected by the auth middleware which validates JWTs
issued by the Auth Service and enforces RBAC via OPA.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaProducer
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from connectors.base import (
    ConnectionConfig, ConnectorResult, DataSourceType, RawMetadataEvent,
)
from connectors.teradata import TeradataConnector
from connectors.mssql import MSSQLConnector
from connectors.bigquery import BigQueryConnector
from connectors.sqlite_connector import SQLiteConnector
from connectors.postgresql import PostgreSQLConnector

log = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
#  Settings                                                                    #
# --------------------------------------------------------------------------- #

class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_raw_metadata: str = "raw-metadata-events"
    auth_service_url: str = "http://auth-service:8006"
    audit_service_url: str = "http://audit-service:8007"
    redis_url: str = "redis://redis:6379"
    service_name: str = "connector-service"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()

# --------------------------------------------------------------------------- #
#  Prometheus metrics                                                          #
# --------------------------------------------------------------------------- #

CONNECTOR_RUNS_TOTAL = Counter(
    "connector_runs_total",
    "Total connector hydration runs",
    ["source_type", "status"],
)
CONNECTOR_RUN_DURATION = Histogram(
    "connector_run_duration_seconds",
    "Duration of connector hydration runs",
    ["source_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)
TABLES_DISCOVERED = Counter(
    "tables_discovered_total",
    "Total tables discovered across all runs",
    ["source_type"],
)
ACTIVE_CONNECTIONS = Gauge(
    "active_source_connections",
    "Number of active source connections",
    ["source_type"],
)

# --------------------------------------------------------------------------- #
#  Audit helper                                                               #
# --------------------------------------------------------------------------- #

_audit_tasks: set = set()


def _audit(event_type: str, **kwargs) -> None:
    """Fire-and-forget audit event — strong task reference prevents GC."""
    async def _post() -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{settings.audit_service_url}/audit/events",
                    json={"event_type": event_type, "service": "connector-service", **kwargs},
                )
        except Exception as exc:
            log.warning("audit_post_failed", event_type=event_type, error=str(exc))
    task = asyncio.ensure_future(_post())
    _audit_tasks.add(task)
    task.add_done_callback(_audit_tasks.discard)


# --------------------------------------------------------------------------- #
#  In-memory job tracker (replace with Redis/DB in production)                #
# --------------------------------------------------------------------------- #

active_jobs: dict[str, dict] = {}
registered_sources: dict[str, ConnectionConfig] = {}

# --------------------------------------------------------------------------- #
#  Kafka producer                                                              #
# --------------------------------------------------------------------------- #

kafka_producer: KafkaProducer | None = None


def get_kafka_producer() -> KafkaProducer:
    global kafka_producer
    if kafka_producer is None:
        kafka_producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: v.model_dump_json().encode(),
            acks="all",            # Strongest durability guarantee
            retries=5,
            compression_type="gzip",
        )
    return kafka_producer


def emit_metadata_event(event: RawMetadataEvent) -> None:
    try:
        producer = get_kafka_producer()
        producer.send(settings.kafka_topic_raw_metadata, value=event)
        producer.flush(timeout=10)
        log.info("metadata_event_emitted", event_id=event.event_id, source_id=event.source_id)
    except Exception as exc:
        log.error("kafka_emit_failed", error=str(exc))


# --------------------------------------------------------------------------- #
#  Connector factory                                                           #
# --------------------------------------------------------------------------- #

def build_connector(config: ConnectionConfig):
    match config.source_type:
        case DataSourceType.TERADATA:
            return TeradataConnector(config)
        case DataSourceType.MSSQL:
            return MSSQLConnector(config)
        case DataSourceType.BIGQUERY:
            return BigQueryConnector(config)
        case DataSourceType.SQLITE:
            return SQLiteConnector(config)
        case DataSourceType.POSTGRESQL:
            return PostgreSQLConnector(config)
        case _:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported source type: {config.source_type}",
            )


# --------------------------------------------------------------------------- #
#  Background hydration job                                                   #
# --------------------------------------------------------------------------- #

async def run_hydration_job(job_id: str, config: ConnectionConfig) -> None:
    active_jobs[job_id]["status"] = "running"
    start = time.monotonic()

    try:
        connector = build_connector(config)
        ACTIVE_CONNECTIONS.labels(source_type=config.source_type.value).inc()

        async with connector:
            is_healthy = await connector.test_connection()
            if not is_healthy:
                raise RuntimeError(f"Cannot connect to {config.source_type} at {config.host}")

            schema_profiles = await connector.run_full_hydration()

        ACTIVE_CONNECTIONS.labels(source_type=config.source_type.value).dec()
        duration = time.monotonic() - start

        # Aggregate stats
        total_tables = sum(len(sp.tables) for sp in schema_profiles)
        total_columns = sum(
            len(t.columns) for sp in schema_profiles for t in sp.tables
        )

        # Emit one Kafka event per schema to keep message sizes manageable
        for sp in schema_profiles:
            event = RawMetadataEvent(
                source_id=config.source_id,
                source_type=config.source_type,
                schema_profile=sp,
                run_id=job_id,
            )
            emit_metadata_event(event)

        # Update job state
        active_jobs[job_id].update({
            "status": "completed",
            "schemas_discovered": len(schema_profiles),
            "tables_discovered": total_tables,
            "columns_discovered": total_columns,
            "duration_secs": round(duration, 2),
            "completed_at": time.time(),
        })

        CONNECTOR_RUNS_TOTAL.labels(source_type=config.source_type.value, status="success").inc()
        CONNECTOR_RUN_DURATION.labels(source_type=config.source_type.value).observe(duration)
        TABLES_DISCOVERED.labels(source_type=config.source_type.value).inc(total_tables)

        _audit(
            "HYDRATION_COMPLETED",
            resource_id=config.source_id,
            details={
                "job_id": job_id,
                "source_type": config.source_type.value,
                "schemas_discovered": len(schema_profiles),
                "tables_discovered": total_tables,
                "columns_discovered": total_columns,
                "duration_secs": round(duration, 2),
            },
        )
        log.info(
            "hydration_completed",
            job_id=job_id,
            schemas=len(schema_profiles),
            tables=total_tables,
            duration_secs=round(duration, 2),
        )

    except Exception as exc:
        duration = time.monotonic() - start
        active_jobs[job_id].update({
            "status": "failed",
            "error": str(exc),
            "duration_secs": round(duration, 2),
        })
        CONNECTOR_RUNS_TOTAL.labels(source_type=config.source_type.value, status="failure").inc()
        log.error("hydration_failed", job_id=job_id, error=str(exc))


# --------------------------------------------------------------------------- #
#  Lifespan                                                                    #
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("connector_service_starting", kafka=settings.kafka_bootstrap_servers)
    yield
    if kafka_producer:
        kafka_producer.close()
    log.info("connector_service_stopped")


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Connector Service",
    version="1.0.0",
    description="Manages source connections and orchestrates schema hydration",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Locked down by ingress / network policy in K8s
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
#  Request models                                                              #
# --------------------------------------------------------------------------- #

class RegisterSourceRequest(BaseModel):
    source_type: DataSourceType
    host: str
    port: int
    database: str
    username: str
    password: str
    schema_filter: list[str] = Field(default_factory=list)
    table_filter: list[str] = Field(default_factory=list)
    enable_profiling: bool = True
    profile_sample_pct: float = Field(default=10.0, ge=0.1, le=100.0)
    extra_params: dict = Field(default_factory=dict)


class TestConnectionRequest(BaseModel):
    source_type: DataSourceType
    host: str
    port: int
    database: str
    username: str
    password: str
    extra_params: dict = Field(default_factory=dict)


class UpdateSourceRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None          # empty string = keep existing
    schema_filter: list[str] | None = None
    table_filter: list[str] | None = None
    enable_profiling: bool | None = None
    profile_sample_pct: float | None = None
    extra_params: dict | None = None


# --------------------------------------------------------------------------- #
#  Routes                                                                      #
# --------------------------------------------------------------------------- #

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/sources", status_code=status.HTTP_201_CREATED)
async def register_source(req: RegisterSourceRequest):
    """Register a new data source for hydration."""
    config = ConnectionConfig(
        source_type=req.source_type,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        password=req.password,
        schema_filter=req.schema_filter,
        table_filter=req.table_filter,
        enable_profiling=req.enable_profiling,
        profile_sample_pct=req.profile_sample_pct,
        extra_params=req.extra_params,
    )
    registered_sources[config.source_id] = config
    log.info("source_registered", source_id=config.source_id, source_type=config.source_type)
    return {"source_id": config.source_id, "source_type": config.source_type}


@app.get("/sources")
async def list_sources():
    """List all registered data sources."""
    return [
        {
            "source_id":          s.source_id,
            "source_type":        s.source_type,
            "host":               s.host,
            "port":               s.port,
            "database":           s.database,
            "username":           s.username,
            "schema_filter":      s.schema_filter,
            "table_filter":       s.table_filter,
            "enable_profiling":   s.enable_profiling,
            "profile_sample_pct": s.profile_sample_pct,
            "extra_params":       s.extra_params,
        }
        for s in registered_sources.values()
    ]


@app.get("/sources/{source_id}")
async def get_source(source_id: str):
    """Get full details for a registered source (password redacted)."""
    if source_id not in registered_sources:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    s = registered_sources[source_id]
    return {
        "source_id":          s.source_id,
        "source_type":        s.source_type,
        "host":               s.host,
        "port":               s.port,
        "database":           s.database,
        "username":           s.username,
        "schema_filter":      s.schema_filter,
        "table_filter":       s.table_filter,
        "enable_profiling":   s.enable_profiling,
        "profile_sample_pct": s.profile_sample_pct,
        "extra_params":       s.extra_params,
    }


@app.put("/sources/{source_id}")
async def update_source(source_id: str, req: UpdateSourceRequest):
    """Update connection parameters for an existing source."""
    if source_id not in registered_sources:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    s = registered_sources[source_id]
    if req.host is not None:
        s.host = req.host
    if req.port is not None:
        s.port = req.port
    if req.database is not None:
        s.database = req.database
    if req.username is not None:
        s.username = req.username
    if req.password:
        s.password = req.password
    if req.schema_filter is not None:
        s.schema_filter = req.schema_filter
    if req.table_filter is not None:
        s.table_filter = req.table_filter
    if req.enable_profiling is not None:
        s.enable_profiling = req.enable_profiling
    if req.profile_sample_pct is not None:
        s.profile_sample_pct = req.profile_sample_pct
    if req.extra_params is not None:
        s.extra_params = req.extra_params
    log.info("source_updated", source_id=source_id)
    return {"source_id": source_id, "status": "updated"}


@app.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str):
    """Remove a registered source and cancel any associated jobs."""
    if source_id not in registered_sources:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    del registered_sources[source_id]
    log.info("source_deleted", source_id=source_id)


@app.post("/sources/{source_id}/hydrate")
async def trigger_hydration(source_id: str, background_tasks: BackgroundTasks):
    """Trigger a schema hydration run for the given source."""
    if source_id not in registered_sources:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    config = registered_sources[source_id]
    job_id = str(uuid.uuid4())
    active_jobs[job_id] = {
        "job_id": job_id,
        "source_id": source_id,
        "status": "queued",
        "started_at": time.time(),
    }

    background_tasks.add_task(run_hydration_job, job_id, config)
    log.info("hydration_job_queued", job_id=job_id, source_id=source_id)
    _audit("HYDRATION_STARTED", resource_id=source_id, details={"job_id": job_id, "source_type": config.source_type.value})
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a hydration job."""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return active_jobs[job_id]


@app.get("/jobs")
async def list_jobs(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent hydration jobs."""
    jobs = list(active_jobs.values())
    if status_filter:
        jobs = [j for j in jobs if j["status"] == status_filter]
    return jobs[-limit:]


@app.post("/test-connection")
async def test_connection(req: TestConnectionRequest):
    """Test a data source connection without registering it."""
    config = ConnectionConfig(
        source_type=req.source_type,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        password=req.password,
        extra_params=req.extra_params,
    )
    connector = build_connector(config)
    try:
        async with connector:
            success = await connector.test_connection()
        return {"success": success, "message": "Connection successful" if success else "Connection failed"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
