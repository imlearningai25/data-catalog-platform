"""
SQLite audit storage — POC / local dev only.
Append-only audit log in a local SQLite file.
Same interface as AuditStorage (BigQuery-backed).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


class SQLiteAuditStorage:
    """Append-only SQLite audit log for POC environments."""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._ensure_tables()
        log.info("sqlite_audit_storage_ready", db_path=db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id      TEXT PRIMARY KEY,
                timestamp     TEXT NOT NULL,
                event_type    TEXT NOT NULL,
                user_id       TEXT,
                user_email    TEXT,
                user_role     TEXT,
                source_ip     TEXT,
                service       TEXT,
                resource_type TEXT,
                resource_id   TEXT,
                resource_fqn  TEXT,
                action        TEXT,
                outcome       TEXT NOT NULL DEFAULT 'SUCCESS',
                request_id    TEXT,
                session_id    TEXT,
                changes       TEXT,
                metadata      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts    ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_type  ON audit_log(event_type);
            CREATE INDEX IF NOT EXISTS idx_audit_email ON audit_log(user_email);
            """)

    def write_event(self, event) -> None:
        """Append-only write. Never updates or deletes."""
        row = (
            event.audit_id,
            event.timestamp.isoformat(),
            event.event_type.value,
            event.user_id,
            event.user_email,
            event.user_role,
            event.source_ip,
            event.service,
            event.resource_type,
            event.resource_id,
            event.resource_fqn,
            event.action,
            event.outcome,
            event.request_id,
            event.session_id,
            json.dumps(event.changes) if event.changes else None,
            json.dumps(event.metadata),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

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
        params: list = []

        if user_email:
            wheres.append("user_email = ?")
            params.append(user_email)
        if event_type:
            wheres.append("event_type = ?")
            params.append(event_type)
        if resource_fqn:
            wheres.append("resource_fqn LIKE ?")
            params.append(f"%{resource_fqn}%")
        if start_time:
            wheres.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            wheres.append("timestamp <= ?")
            params.append(end_time)

        where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        sql = f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
