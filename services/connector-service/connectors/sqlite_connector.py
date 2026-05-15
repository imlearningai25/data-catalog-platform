"""
SQLite Connector — POC / local development only.
Reads schema metadata from a local SQLite database file.
Groups tables by their logical prefix (finance_*, hr_*, product_*)
into virtual schemas so the pipeline behaves identically to Teradata.
"""

from __future__ import annotations

import asyncio
import sqlite3

import structlog

from connectors.base import (
    BaseConnector,
    ColumnProfile,
    ConnectionConfig,
    TableProfile,
)

log = structlog.get_logger(__name__)

# Map SQLite affinity → canonical type
SQLITE_TYPE_MAP: dict[str, str] = {
    "INTEGER": "INTEGER",
    "INT":     "INTEGER",
    "REAL":    "FLOAT",
    "TEXT":    "VARCHAR",
    "BLOB":    "BINARY",
    "NUMERIC": "DECIMAL",
    "BOOLEAN": "BOOLEAN",
    "DATE":    "DATE",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
}

# Prefix → virtual schema name
# e.g. "finance_customer_master" → schema "FINANCE_DB", table "CUSTOMER_MASTER"
PREFIX_TO_SCHEMA: dict[str, str] = {
    "finance_":  "FINANCE_DB",
    "hr_":       "HR_DB",
    "product_":  "PRODUCT_DB",
}


def _resolve_schema_table(raw_name: str) -> tuple[str, str]:
    """Return (schema_name, table_name) from a prefixed SQLite table name."""
    for prefix, schema in PREFIX_TO_SCHEMA.items():
        if raw_name.lower().startswith(prefix):
            return schema, raw_name[len(prefix):].upper()
    return "MAIN", raw_name.upper()


class SQLiteConnector(BaseConnector):
    """
    Connector for local SQLite databases.  Used exclusively in POC / dev.
    The db_path is read from config.extra_params["db_path"] or config.host.
    """

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self.db_path: str = config.extra_params.get("db_path") or config.host or ""
        self._conn: sqlite3.Connection | None = None

    async def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        log.info("sqlite_connected", db_path=self.db_path)

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── BaseConnector interface ──────────────────────────────────────────────

    async def test_connection(self) -> bool:
        try:
            if not self._conn:
                return False
            self._conn.execute("SELECT 1")
            return True
        except Exception as exc:
            log.error("sqlite_connection_test_failed", error=str(exc))
            return False

    async def discover_schemas(self) -> list[str]:
        """Return unique virtual schema names derived from table prefixes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._discover_schemas_sync)

    def _discover_schemas_sync(self) -> list[str]:
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        schemas: set[str] = set()
        for tbl in tables:
            schema, _ = _resolve_schema_table(tbl)
            schemas.add(schema)
        return sorted(schemas)

    async def list_tables(self, schema_name: str) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_tables_sync, schema_name)

    def _list_tables_sync(self, schema_name: str) -> list[str]:
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = []
        for row in cursor.fetchall():
            raw = row[0]
            s, t = _resolve_schema_table(raw)
            if s == schema_name:
                tables.append(t)
        return tables

    async def profile_table(self, schema_name: str, table_name: str) -> TableProfile:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._profile_table_sync, schema_name, table_name
        )

    def _profile_table_sync(self, schema_name: str, table_name: str) -> TableProfile:
        raw_name = self._find_raw_table(schema_name, table_name)

        # Column metadata via PRAGMA
        pragma = self._conn.execute(f"PRAGMA table_info('{raw_name}')").fetchall()
        columns = []
        for row in pragma:
            _, col_name, col_type, not_null, default_val, pk = row
            affinity = _sqlite_affinity(col_type)
            canonical_type = SQLITE_TYPE_MAP.get(affinity, col_type or "TEXT")

            # Sample values
            sample_rows = self._conn.execute(
                f"SELECT \"{col_name}\" FROM \"{raw_name}\" "
                f"WHERE \"{col_name}\" IS NOT NULL LIMIT 5"
            ).fetchall()
            samples = [str(r[0]) for r in sample_rows if r[0] is not None]

            # Null / distinct count via COUNT
            null_count     = self._conn.execute(
                f"SELECT COUNT(*) FROM \"{raw_name}\" WHERE \"{col_name}\" IS NULL"
            ).fetchone()[0]
            distinct_count = self._conn.execute(
                f"SELECT COUNT(DISTINCT \"{col_name}\") FROM \"{raw_name}\""
            ).fetchone()[0]

            # Min/max/avg for numeric/date columns
            min_value = max_value = avg_value = None
            if affinity in ("INTEGER", "REAL", "NUMERIC", "DATE", "DATETIME", "TIMESTAMP"):
                try:
                    row = self._conn.execute(
                        f"SELECT MIN(\"{col_name}\"), MAX(\"{col_name}\") FROM \"{raw_name}\""
                    ).fetchone()
                    if row:
                        min_value = str(row[0]) if row[0] is not None else None
                        max_value = str(row[1]) if row[1] is not None else None
                    if affinity in ("INTEGER", "REAL", "NUMERIC"):
                        avg_row = self._conn.execute(
                            f"SELECT AVG(\"{col_name}\") FROM \"{raw_name}\""
                        ).fetchone()
                        avg_value = float(avg_row[0]) if avg_row and avg_row[0] is not None else None
                except Exception:
                    pass

            columns.append(ColumnProfile(
                name=col_name.upper(),
                data_type=canonical_type,
                is_nullable=(not_null == 0),
                is_primary_key=(pk > 0),
                sample_values=samples,
                null_count=null_count,
                distinct_count=distinct_count,
                min_value=min_value,
                max_value=max_value,
                avg_value=avg_value,
            ))

        row_count = self._conn.execute(f"SELECT COUNT(*) FROM \"{raw_name}\"").fetchone()[0]
        # SQLite doesn't expose size — approximate from page count
        page_size  = self._conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = self._conn.execute("PRAGMA page_count").fetchone()[0]
        size_bytes = page_size * page_count

        return TableProfile(
            schema_name=schema_name,
            table_name=table_name,
            row_count=row_count,
            size_bytes=size_bytes,
            columns=columns,
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    def _find_raw_table(self, schema_name: str, table_name: str) -> str:
        """Reverse-map (schema_name, table_name) → raw SQLite table name."""
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        for row in cursor.fetchall():
            raw = row[0]
            s, t = _resolve_schema_table(raw)
            if s == schema_name and t == table_name:
                return raw
        raise ValueError(f"Table not found: {schema_name}.{table_name}")


def _sqlite_affinity(col_type: str) -> str:
    """Return SQLite type affinity (simplified)."""
    if not col_type:
        return "TEXT"
    upper = col_type.upper()
    if "INT" in upper:
        return "INTEGER"
    if any(x in upper for x in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if any(x in upper for x in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    if any(x in upper for x in ("BLOB",)):
        return "BLOB"
    if any(x in upper for x in ("DATE", "TIME")):
        return upper.split("(")[0].strip()
    return "NUMERIC"
