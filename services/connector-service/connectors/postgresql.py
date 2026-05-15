"""
PostgreSQL Connector
Discovers schema metadata from any PostgreSQL-compatible database
(PostgreSQL, Aurora, AlloyDB, Supabase, Neon, etc.)

Uses psycopg2 (sync) wrapped in asyncio.run_in_executor so FastAPI
stays non-blocking.

Connection info the caller must supply via ConnectionConfig:
  host      : hostname or IP  (e.g. "localhost" or "db.example.com")
  port      : int             (default 5432)
  database  : database name   (e.g. "my_app_db")
  username  : role / user     (e.g. "readonly_user")
  password  : password
  extra_params:
    schema_filter : list[str]  — only hydrate these schemas (default: all non-system)
    sample_pct    : int        — TABLESAMPLE percentage for large tables (default 5)
    sslmode       : str        — "require" | "disable" | "prefer"  (default "prefer")

Catalogs discovered:
  information_schema.schemata        → list schemas
  information_schema.tables          → list tables per schema
  information_schema.columns         → column metadata
  pg_stats / pg_class                → row counts, size, null/distinct estimates
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from connectors.base import (
    BaseConnector,
    ColumnProfile,
    ConnectionConfig,
    DataSourceType,
    SchemaProfile,
    TableProfile,
)

log = structlog.get_logger(__name__)

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    log.warning("psycopg2 not installed — PostgreSQL connector unavailable. "
                "Install with: pip install psycopg2-binary")

# System schemas to always skip
SYSTEM_SCHEMAS = frozenset({
    "information_schema", "pg_catalog", "pg_toast",
    "pg_temp_1", "pg_toast_temp_1",
})

# Map PostgreSQL data types → canonical type names
PG_TYPE_MAP: dict[str, str] = {
    "int2": "SMALLINT", "int4": "INTEGER", "int8": "BIGINT",
    "float4": "FLOAT", "float8": "DOUBLE",
    "numeric": "DECIMAL", "money": "DECIMAL",
    "bool": "BOOLEAN",
    "bpchar": "CHAR", "varchar": "VARCHAR", "text": "TEXT",
    "date": "DATE",
    "timestamp": "TIMESTAMP", "timestamptz": "TIMESTAMP_TZ",
    "time": "TIME", "timetz": "TIME_TZ",
    "json": "JSON", "jsonb": "JSON",
    "uuid": "UUID",
    "bytea": "BINARY",
    "inet": "INET", "cidr": "CIDR", "macaddr": "MACADDR",
    "xml": "XML",
    "array": "ARRAY",
    "tsvector": "TSVECTOR",
}


def _canonical_type(pg_type: str) -> str:
    base = re.sub(r"\(.*\)", "", pg_type.lower()).strip()
    return PG_TYPE_MAP.get(base, pg_type.upper())


class PostgreSQLConnector(BaseConnector):

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError(
                "psycopg2 is not installed. Run: pip install psycopg2-binary"
            )
        self._conn: Any = None
        self._sample_pct: int = int(config.extra_params.get("sample_pct", 5))
        self._sslmode: str    = config.extra_params.get("sslmode", "prefer")

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        loop = asyncio.get_event_loop()
        self._conn = await loop.run_in_executor(None, self._connect_sync)
        log.info("postgres_connected",
                 host=self.config.host, database=self.config.database)

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _connect_sync(self):
        return psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5432,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
            sslmode=self._sslmode,
            connect_timeout=10,
            options="-c statement_timeout=30000",   # 30-second query cap
        )

    # ── BaseConnector interface ──────────────────────────────────────────────

    async def test_connection(self) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._test_sync)

    def _test_sync(self) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT version(), current_database(), current_user")
            row = cur.fetchone()
            log.info("postgres_version",
                     version=row[0][:50], database=row[1], user=row[2])
        return True

    async def discover_schemas(self) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._discover_schemas_sync)

    def _discover_schemas_sync(self) -> list[str]:
        """
        Returns all non-system schemas the current user can see.
        Applies schema_filter if configured.
        """
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT LIKE 'pg_%'
                  AND schema_name NOT IN ('information_schema')
                ORDER BY schema_name
            """)
            schemas = [row[0] for row in cur.fetchall()
                       if row[0] not in SYSTEM_SCHEMAS]

        schema_filter = self.config.schema_filter or []
        if schema_filter:
            schemas = [s for s in schemas if s in schema_filter]

        return schemas

    async def list_tables(self, schema_name: str) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_tables_sync, schema_name)

    def _list_tables_sync(self, schema_name: str) -> list[str]:
        """
        Lists all BASE TABLEs and VIEWs in the given schema.
        """
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_name
            """, (schema_name,))
            return [row[0] for row in cur.fetchall()]

    async def profile_table(self, schema_name: str, table_name: str) -> TableProfile:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._profile_table_sync, schema_name, table_name
        )

    def _profile_table_sync(self, schema_name: str, table_name: str) -> TableProfile:
        fqt = f'"{schema_name}"."{table_name}"'

        # ── Row count & size ─────────────────────────────────────────────────
        row_count, size_bytes = self._get_table_stats(schema_name, table_name)

        # ── Column metadata from information_schema ──────────────────────────
        with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT
                    c.column_name,
                    c.data_type,
                    c.udt_name,
                    c.is_nullable,
                    c.character_maximum_length,
                    c.numeric_precision,
                    c.numeric_scale,
                    c.column_default,
                    tc.constraint_type          AS pk_flag
                FROM information_schema.columns c
                LEFT JOIN information_schema.key_column_usage kcu
                       ON kcu.table_schema = c.table_schema
                      AND kcu.table_name   = c.table_name
                      AND kcu.column_name  = c.column_name
                LEFT JOIN information_schema.table_constraints tc
                       ON tc.constraint_name = kcu.constraint_name
                      AND tc.constraint_type = 'PRIMARY KEY'
                WHERE c.table_schema = %s
                  AND c.table_name   = %s
                ORDER BY c.ordinal_position
            """, (schema_name, table_name))
            col_rows = cur.fetchall()

        # ── pg_stats estimates (null rate, distinct count) ───────────────────
        stats = self._get_pg_stats(schema_name, table_name)

        # ── Sample values (small TABLESAMPLE) ───────────────────────────────
        col_names = [r["column_name"] for r in col_rows]
        samples   = self._get_samples(fqt, col_names, row_count)

        # ── Column-level aggregates (min/max/avg) for numeric/date columns ─────
        col_stat_types = {
            r["column_name"]: (r["udt_name"] or r["data_type"])
            for r in col_rows
        }
        agg_stats = self._get_column_agg_stats(fqt, col_names, col_stat_types, row_count)

        columns = []
        for row in col_rows:
            col_name   = row["column_name"]
            pg_type    = row["udt_name"] or row["data_type"]
            canon_type = _canonical_type(pg_type)

            st = stats.get(col_name, {})
            null_frac     = st.get("null_frac", 0.0)
            n_distinct_pg = st.get("n_distinct", 0.0)

            # pg_stats.n_distinct: negative = fraction of total rows, positive = absolute count
            if n_distinct_pg < 0 and row_count:
                distinct_count = int(abs(n_distinct_pg) * row_count)
            elif n_distinct_pg > 0:
                distinct_count = int(n_distinct_pg)
            else:
                distinct_count = 0

            null_count = int(null_frac * row_count) if row_count else 0
            agg = agg_stats.get(col_name, {})

            columns.append(ColumnProfile(
                name=col_name.upper(),
                data_type=canon_type,
                is_nullable=(row["is_nullable"] == "YES"),
                is_primary_key=(row["pk_flag"] == "PRIMARY KEY"),
                max_length=row["character_maximum_length"],
                precision=row["numeric_precision"],
                scale=row["numeric_scale"],
                sample_values=samples.get(col_name, []),
                null_count=null_count,
                distinct_count=distinct_count,
                min_value=agg.get("min_value"),
                max_value=agg.get("max_value"),
                avg_value=agg.get("avg_value"),
            ))

        return TableProfile(
            schema_name=schema_name.upper(),
            table_name=table_name.upper(),
            row_count=row_count,
            size_bytes=size_bytes,
            columns=columns,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_table_stats(self, schema: str, table: str) -> tuple[int, int]:
        """
        Returns (estimated_row_count, size_bytes) from pg_class.
        Falls back to COUNT(*) for small tables (<10k rows by estimate).
        """
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT
                    c.reltuples::BIGINT                        AS est_rows,
                    pg_total_relation_size(c.oid)              AS total_bytes
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relname = %s
            """, (schema, table))
            row = cur.fetchone()

        if row and row[0] is not None and row[0] > 10_000:
            return int(row[0]), int(row[1] or 0)

        # Exact count for small tables
        with self._conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            exact = cur.fetchone()[0]
        return exact, int(row[1] or 0) if row else 0

    def _get_pg_stats(self, schema: str, table: str) -> dict[str, dict]:
        """
        Pulls per-column statistics from pg_stats.
        Returns { column_name: {null_frac, n_distinct} }
        """
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute("""
                    SELECT attname, null_frac, n_distinct
                    FROM pg_stats
                    WHERE schemaname = %s AND tablename = %s
                """, (schema, table))
                return {
                    row["attname"]: {
                        "null_frac":  float(row["null_frac"] or 0),
                        "n_distinct": float(row["n_distinct"] or 0),
                    }
                    for row in cur.fetchall()
                }
        except Exception:
            return {}

    def _get_samples(self, fqt: str, col_names: list[str],
                     row_count: int) -> dict[str, list[str]]:
        """
        Returns up to 5 non-null sample values per column.
        Uses TABLESAMPLE BERNOULLI for large tables to keep queries fast.
        """
        if not col_names:
            return {}

        sample_clause = (
            f"TABLESAMPLE BERNOULLI({self._sample_pct})"
            if row_count > 10_000 else ""
        )
        cols_sql = ", ".join(f'"{c}"' for c in col_names)
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    f"SELECT {cols_sql} FROM {fqt} {sample_clause} LIMIT 500"
                )
                rows = cur.fetchall()
        except Exception as exc:
            log.warning("sample_query_failed", table=fqt, error=str(exc))
            return {}

        samples: dict[str, list[str]] = {c: [] for c in col_names}
        for row in rows:
            for col_name, val in zip(col_names, row):
                if val is not None and len(samples[col_name]) < 5:
                    samples[col_name].append(str(val))
        return samples

    # pg type families eligible for MIN/MAX/AVG
    _NUMERIC_TYPES = frozenset({
        "int2", "int4", "int8", "float4", "float8", "numeric", "money",
        "date", "timestamp", "timestamptz",
    })

    def _get_column_agg_stats(
        self, fqt: str, col_names: list[str],
        col_types: dict[str, str], row_count: int,
    ) -> dict[str, dict]:
        """Return {col_name: {min_value, max_value, avg_value}} for numeric/date cols."""
        if not col_names or not row_count:
            return {}

        eligible = [
            c for c in col_names
            if (col_types.get(c, "").lower().split("(")[0].strip()) in self._NUMERIC_TYPES
        ]
        if not eligible:
            return {}

        # Build a single SELECT with MIN/MAX/AVG for all eligible columns
        parts = []
        for c in eligible:
            qc = f'"{c}"'
            parts.append(f"MIN({qc})::TEXT AS min_{c}")
            parts.append(f"MAX({qc})::TEXT AS max_{c}")
            # AVG only meaningful for true numerics, not dates
            base = col_types.get(c, "").lower().split("(")[0].strip()
            if base in {"int2", "int4", "int8", "float4", "float8", "numeric", "money"}:
                parts.append(f"AVG({qc}::NUMERIC)::FLOAT AS avg_{c}")
            else:
                parts.append(f"NULL::FLOAT AS avg_{c}")

        sql = f"SELECT {', '.join(parts)} FROM {fqt}"
        try:
            with self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(sql)
                row = cur.fetchone()
                if not row:
                    return {}
                result = {}
                for c in eligible:
                    result[c] = {
                        "min_value": row[f"min_{c}"],
                        "max_value": row[f"max_{c}"],
                        "avg_value": row[f"avg_{c}"],
                    }
                return result
        except Exception as exc:
            log.warning("column_agg_stats_failed", table=fqt, error=str(exc))
            return {}
