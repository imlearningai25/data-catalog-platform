"""
Google BigQuery connector — uses the official google-cloud-bigquery SDK.
Supports dataset discovery, table listing, schema extraction, and
partition/cluster metadata.
"""

from __future__ import annotations

import structlog
from google.cloud import bigquery
from google.cloud.bigquery import Client, Table

from .base import BaseConnector, ColumnProfile, ConnectionConfig, TableProfile

log = structlog.get_logger(__name__)

BQ_TYPE_MAP = {
    "STRING": "VARCHAR", "BYTES": "VARBYTE", "INTEGER": "BIGINT",
    "INT64": "BIGINT", "FLOAT": "FLOAT", "FLOAT64": "FLOAT",
    "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN", "TIMESTAMP": "TIMESTAMP",
    "DATE": "DATE", "TIME": "TIME", "DATETIME": "DATETIME",
    "NUMERIC": "NUMERIC", "BIGNUMERIC": "BIGNUMERIC",
    "RECORD": "STRUCT", "STRUCT": "STRUCT", "ARRAY": "ARRAY",
    "JSON": "JSON", "GEOGRAPHY": "GEOGRAPHY",
}


class BigQueryConnector(BaseConnector):
    """
    Connector for Google BigQuery.
    Authenticates via Application Default Credentials (ADC) or
    service account JSON via extra_params['credentials_path'].
    """

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._client: Client | None = None

    async def connect(self) -> None:
        import asyncio
        loop = asyncio.get_event_loop()

        def _init_client():
            creds_path = self.config.extra_params.get("credentials_path")
            if creds_path:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
                )
                return bigquery.Client(project=self.config.host, credentials=creds)
            return bigquery.Client(project=self.config.host)

        self._client = await loop.run_in_executor(None, _init_client)
        self._connected = True
        log.info("bigquery_connected", project=self.config.host)

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._connected = False

    async def test_connection(self) -> bool:
        list(self._client.list_datasets(max_results=1))
        return True

    async def discover_schemas(self) -> list[str]:
        import asyncio
        loop = asyncio.get_event_loop()

        def _list():
            return [ds.dataset_id for ds in self._client.list_datasets()]

        return await loop.run_in_executor(None, _list)

    async def list_tables(self, schema_name: str) -> list[str]:
        import asyncio
        loop = asyncio.get_event_loop()

        def _list():
            return [t.table_id for t in self._client.list_tables(schema_name)]

        return await loop.run_in_executor(None, _list)

    async def profile_table(self, schema_name: str, table_name: str) -> TableProfile:
        import asyncio
        loop = asyncio.get_event_loop()
        table_ref = f"{self.config.host}.{schema_name}.{table_name}"

        def _get_table():
            return self._client.get_table(table_ref)

        bq_table: Table = await loop.run_in_executor(None, _get_table)
        row_count = bq_table.num_rows or 0

        columns = self._extract_columns(bq_table.schema)

        # Fetch null_count and distinct_count per column (sampled to limit cost)
        if row_count > 0:
            col_stats = await loop.run_in_executor(
                None, self._get_column_stats, table_ref, bq_table.schema, row_count
            )
            for col in columns:
                st = col_stats.get(col.name, {})
                col.null_count = st.get("null_count")
                col.distinct_count = st.get("distinct_count")
                col.min_value = st.get("min_value")
                col.max_value = st.get("max_value")
                col.avg_value = st.get("avg_value")
                col.sample_values = st.get("sample_values", [])

        partitioning = None
        if bq_table.time_partitioning:
            partitioning = {
                "type": bq_table.time_partitioning.type_,
                "field": bq_table.time_partitioning.field,
                "expiration_ms": bq_table.time_partitioning.expiration_ms,
            }

        return TableProfile(
            schema_name=schema_name,
            table_name=table_name,
            table_type="TABLE" if bq_table.table_type == "TABLE" else bq_table.table_type,
            row_count=row_count,
            size_bytes=bq_table.num_bytes,
            last_modified=bq_table.modified,
            columns=columns,
            partitioning=partitioning,
            tags={
                **(bq_table.labels or {}),
                **({"clustering": str(bq_table.clustering_fields)} if bq_table.clustering_fields else {}),
            },
        )

    _BQ_NUMERIC_TYPES = frozenset({
        "INTEGER", "INT64", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC",
    })
    _BQ_COMPARABLE_TYPES = frozenset({
        "INTEGER", "INT64", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC",
        "DATE", "TIMESTAMP", "DATETIME",
    })

    def _get_column_stats(self, table_ref: str, schema, row_count: int) -> dict:
        """Query BigQuery for null_count, distinct_count, min/max/avg per column."""
        # Flatten top-level fields only (skip nested RECORD types)
        flat_cols = [f for f in schema if f.field_type not in ("RECORD", "STRUCT")]
        if not flat_cols:
            return {}

        parts = []
        for field in flat_cols:
            fn = field.name
            ftype = field.field_type
            is_repeated = field.mode == "REPEATED"
            if is_repeated:
                continue  # skip ARRAY columns for profiling
            parts.append(f"COUNTIF(`{fn}` IS NULL) AS null_{fn}")
            parts.append(f"APPROX_COUNT_DISTINCT(`{fn}`) AS dist_{fn}")
            if ftype in self._BQ_COMPARABLE_TYPES:
                parts.append(f"CAST(MIN(`{fn}`) AS STRING) AS min_{fn}")
                parts.append(f"CAST(MAX(`{fn}`) AS STRING) AS max_{fn}")
            else:
                parts.append(f"CAST(NULL AS STRING) AS min_{fn}")
                parts.append(f"CAST(NULL AS STRING) AS max_{fn}")
            if ftype in self._BQ_NUMERIC_TYPES:
                parts.append(f"AVG(CAST(`{fn}` AS FLOAT64)) AS avg_{fn}")
            else:
                parts.append(f"CAST(NULL AS FLOAT64) AS avg_{fn}")

        if not parts:
            return {}

        # Use TABLESAMPLE for large tables to keep costs low
        sample_clause = "TABLESAMPLE SYSTEM (5 PERCENT)" if row_count > 100_000 else ""
        sql = f"SELECT {', '.join(parts)} FROM `{table_ref}` {sample_clause}"

        # Fetch a few sample values per column (STRING only, to avoid type issues)
        sample_sql = (
            f"SELECT {', '.join(f'CAST(`{f.name}` AS STRING) AS `{f.name}`' for f in flat_cols if f.mode != 'REPEATED')} "
            f"FROM `{table_ref}` {sample_clause} LIMIT 500"
        )

        try:
            agg_row = list(self._client.query(sql).result())[0]
            sample_rows = list(self._client.query(sample_sql).result())

            # Build sample_values per column
            samples: dict[str, list[str]] = {f.name: [] for f in flat_cols if f.mode != "REPEATED"}
            for srow in sample_rows:
                for field in flat_cols:
                    if field.mode == "REPEATED":
                        continue
                    val = srow.get(field.name)
                    if val is not None and len(samples[field.name]) < 5:
                        samples[field.name].append(str(val))

            result = {}
            for field in flat_cols:
                fn = field.name
                if field.mode == "REPEATED":
                    continue
                result[fn] = {
                    "null_count": agg_row.get(f"null_{fn}"),
                    "distinct_count": agg_row.get(f"dist_{fn}"),
                    "min_value": agg_row.get(f"min_{fn}"),
                    "max_value": agg_row.get(f"max_{fn}"),
                    "avg_value": agg_row.get(f"avg_{fn}"),
                    "sample_values": samples.get(fn, []),
                }
            return result
        except Exception as exc:
            log.warning("bq_column_stats_failed", table=table_ref, error=str(exc))
            return {}

    def _extract_columns(self, schema: list, prefix: str = "") -> list[ColumnProfile]:
        """Recursively flatten RECORD fields with dot notation."""
        cols = []
        for field in schema:
            full_name = f"{prefix}{field.name}" if not prefix else f"{prefix}.{field.name}"
            cols.append(
                ColumnProfile(
                    name=full_name,
                    data_type=BQ_TYPE_MAP.get(field.field_type, field.field_type),
                    is_nullable=(field.mode != "REQUIRED"),
                    description=field.description or None,
                )
            )
            if field.field_type in ("RECORD", "STRUCT") and field.fields:
                cols.extend(self._extract_columns(field.fields, f"{full_name}."))
        return cols
