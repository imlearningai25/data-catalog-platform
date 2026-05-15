"""
Audit Service — Immutable Audit Trail
Writes all platform events to BigQuery as an immutable audit log.
Supports compliance requirements: SOC 2, GDPR, HIPAA, CCPA.
All writes are append-only — no updates or deletes.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    gcp_project: str = "my-data-platform"
    bq_dataset: str = "data_catalog"
    bq_table_audit: str = "audit_log"
    service_name: str = "audit-service"
    # POC / local-dev: set CATALOG_BACKEND=sqlite to bypass BigQuery
    catalog_backend: str = "bigquery"
    sqlite_db_path: str = "/poc-data/audit.db"

    class Config:
        env_file = ".env"


settings = Settings()

AUDIT_EVENTS_WRITTEN = Counter("audit_events_written_total", "Audit events written", ["event_type", "outcome"])


class EventType(str, Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    LOGIN_FAILED = "LOGIN_FAILED"
    TOKEN_REFRESHED = "TOKEN_REFRESHED"
    ASSET_READ = "ASSET_READ"
    ASSET_WRITE = "ASSET_WRITE"
    ASSET_DELETE = "ASSET_DELETE"
    COLUMN_READ = "COLUMN_READ"
    PII_ACCESS = "PII_ACCESS"
    TERM_CREATED = "TERM_CREATED"
    TERM_UPDATED = "TERM_UPDATED"
    TERM_ASSIGNED = "TERM_ASSIGNED"
    SOURCE_REGISTERED = "SOURCE_REGISTERED"
    HYDRATION_STARTED = "HYDRATION_STARTED"
    HYDRATION_COMPLETED = "HYDRATION_COMPLETED"
    CLASSIFICATION_OVERRIDE = "CLASSIFICATION_OVERRIDE"
    LINEAGE_CREATED = "LINEAGE_CREATED"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_DELETED = "USER_DELETED"
    ACCESS_DENIED = "ACCESS_DENIED"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class AuditEvent(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    user_id: str | None = None
    user_email: str | None = None
    user_role: str | None = None
    source_ip: str | None = None
    service: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    resource_fqn: str | None = None
    action: str | None = None
    outcome: str = "SUCCESS"          # SUCCESS | FAILURE | DENIED
    request_id: str | None = None
    session_id: str | None = None
    changes: dict | None = None       # Before/after for write events
    metadata: dict = Field(default_factory=dict)


def _init_audit_storage():
    """Return the correct storage backend based on CATALOG_BACKEND env var."""
    if settings.catalog_backend.lower() == "sqlite":
        from storage_sqlite import SQLiteAuditStorage
        return SQLiteAuditStorage(settings.sqlite_db_path)
    return AuditStorage()


class AuditStorage:
    def __init__(self):
        self.client = bigquery.Client(project=settings.gcp_project)
        self.table_ref = f"{settings.gcp_project}.{settings.bq_dataset}.{settings.bq_table_audit}"

    def write_event(self, event: AuditEvent) -> None:
        """Write an audit event to BigQuery (append-only)."""
        import json
        row = {
            "audit_id": event.audit_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "user_id": event.user_id,
            "user_email": event.user_email,
            "user_role": event.user_role,
            "source_ip": event.source_ip,
            "service": event.service,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "resource_fqn": event.resource_fqn,
            "action": event.action,
            "outcome": event.outcome,
            "request_id": event.request_id,
            "session_id": event.session_id,
            "changes": json.dumps(event.changes) if event.changes else None,
            "metadata": json.dumps(event.metadata),
        }
        errors = self.client.insert_rows_json(self.table_ref, [row])
        if errors:
            log.error("audit_write_failed", errors=errors)
        AUDIT_EVENTS_WRITTEN.labels(
            event_type=event.event_type.value,
            outcome=event.outcome,
        ).inc()

    def query_events(
        self,
        user_email: str | None = None,
        event_type: str | None = None,
        resource_fqn: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        wheres = []
        params = []

        if user_email:
            wheres.append("user_email = @user_email")
            params.append(bigquery.ScalarQueryParameter("user_email", "STRING", user_email))
        if event_type:
            wheres.append("event_type = @event_type")
            params.append(bigquery.ScalarQueryParameter("event_type", "STRING", event_type))
        if resource_fqn:
            wheres.append("resource_fqn = @resource_fqn")
            params.append(bigquery.ScalarQueryParameter("resource_fqn", "STRING", resource_fqn))
        if start_time:
            wheres.append("timestamp >= @start_time")
            params.append(bigquery.ScalarQueryParameter("start_time", "TIMESTAMP", start_time))
        if end_time:
            wheres.append("timestamp <= @end_time")
            params.append(bigquery.ScalarQueryParameter("end_time", "TIMESTAMP", end_time))

        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))

        sql = f"""
            SELECT *
            FROM `{self.table_ref}`
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT @limit
        """
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        return [dict(row) for row in self.client.query(sql, job_config=job_config).result()]


audit_storage: AuditStorage | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global audit_storage
    audit_storage = _init_audit_storage()
    log.info("audit_service_started", backend=settings.catalog_backend)
    yield
    log.info("audit_service_stopped")


app = FastAPI(
    title="Data Catalog — Audit Service",
    version="1.0.0",
    description="Immutable audit trail backed by BigQuery",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/audit/events", status_code=201)
async def write_audit_event(event: AuditEvent):
    """Write an audit event. Called by all other services."""
    if not audit_storage:
        raise HTTPException(503, "Storage not initialized")

    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, audit_storage.write_event, event)
    log.info("audit_event_written", audit_id=event.audit_id, type=event.event_type.value)
    return {"audit_id": event.audit_id}


@app.get("/audit/events")
async def query_audit_events(
    user_email: str | None = None,
    event_type: str | None = None,
    resource_fqn: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Query the audit log (admin only in production)."""
    if not audit_storage:
        raise HTTPException(503, "Storage not initialized")

    import asyncio
    loop = asyncio.get_event_loop()
    events = await loop.run_in_executor(
        None,
        lambda: audit_storage.query_events(user_email, event_type, resource_fqn, start_time, end_time, limit),
    )
    return {"total": len(events), "events": events}


@app.get("/audit/pii-access-report")
async def pii_access_report(days: int = 30):
    """Compliance report: PII access events in the last N days."""
    if not audit_storage:
        raise HTTPException(503, "Storage not initialized")

    events = audit_storage.query_events(event_type="PII_ACCESS", limit=1000)
    return {
        "report_type": "pii_access",
        "days": days,
        "total_events": len(events),
        "events": events,
    }
