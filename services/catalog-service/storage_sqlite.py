"""
SQLite storage backend for catalog-service — POC / local dev only.
Provides the same interface as BigQueryStorage so main.py can swap
backends via the CATALOG_BACKEND env var without changing any logic.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


class SQLiteStorage:
    """
    Drop-in replacement for BigQueryStorage backed by a local SQLite file.
    All method signatures are identical to BigQueryStorage.
    """

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._ensure_tables()
        self._migrate()
        log.info("sqlite_catalog_storage_ready", db_path=db_path)

    # ── schema bootstrap ──────────────────────────────────────────────────────

    def _ensure_tables(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id              TEXT PRIMARY KEY,
                fqn                   TEXT NOT NULL UNIQUE,
                source_id             TEXT,
                source_type           TEXT,
                database_name         TEXT,
                schema_name           TEXT,
                table_name            TEXT,
                description           TEXT,
                domain                TEXT,
                data_owner            TEXT,
                data_steward          TEXT,
                sensitivity_level     TEXT DEFAULT 'INTERNAL',
                row_count             INTEGER,
                size_bytes            INTEGER,
                quality_score         REAL,
                quality_grade         TEXT,
                quality_completeness  REAL,
                quality_uniqueness    REAL,
                quality_validity      REAL,
                quality_consistency   REAL,
                tags                  TEXT,
                suggested_terms       TEXT,
                is_active             INTEGER NOT NULL DEFAULT 1,
                run_id                TEXT,
                ingested_at           TEXT,
                updated_at            TEXT
            );

            CREATE TABLE IF NOT EXISTS columns (
                column_id         TEXT PRIMARY KEY,
                asset_id          TEXT NOT NULL,
                fqn               TEXT NOT NULL,
                column_name       TEXT,
                data_type         TEXT,
                description       TEXT,
                is_nullable       INTEGER,
                pii_classification TEXT,
                pii_category      TEXT,
                sensitivity_level TEXT,
                suggested_terms   TEXT,
                quality_score     REAL,
                quality_grade     TEXT,
                null_count        INTEGER,
                distinct_count    INTEGER,
                min_value         TEXT,
                max_value         TEXT,
                avg_value         REAL,
                sample_values     TEXT,
                asset_fqn         TEXT,
                ingested_at       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_assets_schema   ON assets(schema_name);
            CREATE INDEX IF NOT EXISTS idx_assets_domain   ON assets(domain);
            CREATE INDEX IF NOT EXISTS idx_assets_sens     ON assets(sensitivity_level);
            CREATE INDEX IF NOT EXISTS idx_columns_asset   ON columns(asset_id);
            """)

    def _migrate(self):
        """Add new columns to existing tables without dropping data."""
        migrations = [
            ("columns", "min_value",            "TEXT"),
            ("columns", "max_value",            "TEXT"),
            ("columns", "avg_value",            "REAL"),
            ("columns", "sample_values",        "TEXT"),
            ("assets",  "quality_completeness", "REAL"),
            ("assets",  "quality_uniqueness",   "REAL"),
            ("assets",  "quality_validity",     "REAL"),
            ("assets",  "quality_consistency",  "REAL"),
        ]
        with self._connect() as conn:
            existing_cols = {}
            for tbl in ("columns", "assets"):
                existing_cols[tbl] = {
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info({tbl})").fetchall()
                }
            for table, col, coltype in migrations:
                if col not in existing_cols[table]:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                        log.info("sqlite_column_migrated", table=table, column=col)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc):
                            raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── writes ────────────────────────────────────────────────────────────────

    def upsert_asset(self, asset: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO assets (
                    asset_id, fqn, source_id, source_type, database_name,
                    schema_name, table_name, description, domain, data_owner,
                    data_steward, sensitivity_level, row_count, size_bytes,
                    quality_score, quality_grade,
                    quality_completeness, quality_uniqueness, quality_validity, quality_consistency,
                    tags, suggested_terms, is_active, run_id, ingested_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fqn) DO UPDATE SET
                    sensitivity_level    = excluded.sensitivity_level,
                    row_count            = excluded.row_count,
                    size_bytes           = excluded.size_bytes,
                    quality_score        = excluded.quality_score,
                    quality_grade        = excluded.quality_grade,
                    quality_completeness = excluded.quality_completeness,
                    quality_uniqueness   = excluded.quality_uniqueness,
                    quality_validity     = excluded.quality_validity,
                    quality_consistency  = excluded.quality_consistency,
                    suggested_terms      = excluded.suggested_terms,
                    updated_at           = excluded.updated_at
            """, (
                asset.get("asset_id", str(uuid.uuid4())),
                asset["fqn"],
                asset.get("source_id"),
                asset.get("source_type"),
                asset.get("database_name"),
                asset.get("schema_name"),
                asset.get("table_name"),
                asset.get("description"),
                asset.get("domain"),
                asset.get("data_owner"),
                asset.get("data_steward"),
                asset.get("sensitivity_level", "INTERNAL"),
                asset.get("row_count"),
                asset.get("size_bytes"),
                asset.get("quality_score"),
                asset.get("quality_grade"),
                asset.get("quality_completeness"),
                asset.get("quality_uniqueness"),
                asset.get("quality_validity"),
                asset.get("quality_consistency"),
                json.dumps(asset.get("tags", {})),
                json.dumps(asset.get("suggested_terms", [])),
                1,
                asset.get("run_id"),
                now, now,
            ))
        log.info("sqlite_asset_upserted", fqn=asset["fqn"])

    def upsert_columns(self, asset_id: str, asset_fqn: str, columns: list[dict]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for col in columns:
            qs = col.get("quality_score")
            qs_overall = qs.get("overall") if isinstance(qs, dict) else qs
            qs_grade   = qs.get("grade")   if isinstance(qs, dict) else None
            sv = col.get("sample_values", [])
            rows.append((
                str(uuid.uuid4()),
                asset_id,
                f"{asset_fqn}.{col['name']}",
                col["name"],
                col.get("data_type"),
                col.get("description"),
                1 if col.get("is_nullable", True) else 0,
                col.get("pii_classification"),
                col.get("pii_category"),
                col.get("pii_sensitivity", "PUBLIC"),
                json.dumps(col.get("suggested_terms", [])),
                qs_overall,
                qs_grade,
                col.get("null_count"),
                col.get("distinct_count"),
                asset_fqn,
                now,
                str(col["min_value"]) if col.get("min_value") is not None else None,
                str(col["max_value"]) if col.get("max_value") is not None else None,
                float(col["avg_value"]) if col.get("avg_value") is not None else None,
                json.dumps(sv) if isinstance(sv, list) else sv,
            ))
        with self._connect() as conn:
            # Delete stale columns from previous hydration runs before inserting fresh ones
            conn.execute("DELETE FROM columns WHERE asset_fqn = ?", (asset_fqn,))
            if rows:
                conn.executemany(
                    """INSERT INTO columns (
                        column_id, asset_id, fqn, column_name, data_type, description,
                        is_nullable, pii_classification, pii_category, sensitivity_level,
                        suggested_terms, quality_score, quality_grade,
                        null_count, distinct_count, asset_fqn, ingested_at,
                        min_value, max_value, avg_value, sample_values
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    rows,
                )

    # ── reads ─────────────────────────────────────────────────────────────────

    def search_assets(
        self,
        query: str | None = None,
        domain: str | None = None,
        sensitivity: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        where_clauses = ["is_active = 1"]
        params: list = []

        if query:
            where_clauses.append(
                "(LOWER(fqn) LIKE ? OR LOWER(description) LIKE ? "
                "OR LOWER(table_name) LIKE ? OR LOWER(schema_name) LIKE ?)"
            )
            q = f"%{query.lower()}%"
            params.extend([q, q, q, q])

        if domain:
            where_clauses.append("domain = ?")
            params.append(domain)

        if sensitivity:
            where_clauses.append("sensitivity_level = ?")
            params.append(sensitivity.upper())

        if source_type:
            where_clauses.append("source_type = ?")
            params.append(source_type)

        where = " AND ".join(where_clauses)
        sql = f"SELECT * FROM assets WHERE {where} ORDER BY ingested_at DESC LIMIT ? OFFSET ?"

        with self._connect() as conn:
            rows = conn.execute(sql, params + [limit, offset]).fetchall()
            total = conn.execute(f"SELECT COUNT(*) FROM assets WHERE {where}", params).fetchone()[0]

        results = []
        for row in rows:
            d = dict(row)
            d["tags"]            = json.loads(d.get("tags") or "{}")
            d["suggested_terms"] = json.loads(d.get("suggested_terms") or "[]")
            results.append(d)

        return {"total": total, "assets": results, "limit": limit, "offset": offset}

    def get_asset_by_fqn(self, fqn: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE fqn = ?", (fqn,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"]            = json.loads(d.get("tags") or "{}")
        d["suggested_terms"] = json.loads(d.get("suggested_terms") or "[]")
        return d

    def get_columns(self, asset_fqn: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM columns WHERE asset_fqn = ? ORDER BY column_name",
                (asset_fqn,),
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["suggested_terms"] = json.loads(d.get("suggested_terms") or "[]")
            d["sample_values"]   = json.loads(d.get("sample_values") or "[]")
            result.append(d)
        return result

    def count_assets(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM assets WHERE is_active=1").fetchone()[0]
