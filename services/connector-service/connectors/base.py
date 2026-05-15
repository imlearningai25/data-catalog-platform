"""
Base connector interface — all source connectors implement this contract.
Every connector must: discover schemas, list tables, profile columns, and
compute statistics. Results are emitted as RawMetadataEvents to Kafka.
"""

from __future__ import annotations

import abc
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataSourceType(str, Enum):
    TERADATA = "teradata"
    MSSQL = "mssql"
    BIGQUERY = "bigquery"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SNOWFLAKE = "snowflake"
    ORACLE = "oracle"
    SQLITE = "sqlite"           # POC / local dev only


class ColumnProfile(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    description: str | None = None
    # Statistical profile
    null_count: int | None = None
    distinct_count: int | None = None
    min_value: Any | None = None
    max_value: Any | None = None
    avg_value: float | None = None
    sample_values: list[Any] = Field(default_factory=list)


class TableProfile(BaseModel):
    schema_name: str
    table_name: str
    table_type: str = "TABLE"  # TABLE | VIEW | MATERIALIZED_VIEW
    row_count: int | None = None
    size_bytes: int | None = None
    last_modified: datetime | None = None
    columns: list[ColumnProfile] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_keys: list[dict] = Field(default_factory=list)
    indexes: list[dict] = Field(default_factory=list)
    partitioning: dict | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class SchemaProfile(BaseModel):
    database_name: str
    schema_name: str
    tables: list[TableProfile] = Field(default_factory=list)


class ConnectionConfig(BaseModel):
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_type: DataSourceType
    host: str
    port: int
    database: str
    username: str
    password: str  # Encrypted at rest via Secret Manager
    schema_filter: list[str] = Field(default_factory=list)   # empty = all
    table_filter: list[str] = Field(default_factory=list)
    enable_profiling: bool = True
    profile_sample_pct: float = 10.0  # % of rows to sample for stats
    connect_timeout_secs: int = 30
    extra_params: dict[str, Any] = Field(default_factory=dict)


class RawMetadataEvent(BaseModel):
    """Kafka event emitted after each connector run."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str
    source_type: DataSourceType
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_profile: SchemaProfile
    connector_version: str = "1.0.0"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ConnectorResult(BaseModel):
    success: bool
    source_id: str
    schemas_discovered: int = 0
    tables_discovered: int = 0
    columns_discovered: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_secs: float = 0.0
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class BaseConnector(abc.ABC):
    """
    Abstract base class for all data source connectors.
    Subclasses must implement: connect, disconnect, discover_schemas,
    profile_table, and test_connection.
    """

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection = None
        self._connected = False

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close and clean up the connection."""

    @abc.abstractmethod
    async def test_connection(self) -> bool:
        """Verify the connection is healthy."""

    @abc.abstractmethod
    async def discover_schemas(self) -> list[str]:
        """Return list of accessible schema/database names."""

    @abc.abstractmethod
    async def list_tables(self, schema_name: str) -> list[str]:
        """Return list of tables and views in the given schema."""

    @abc.abstractmethod
    async def profile_table(self, schema_name: str, table_name: str) -> TableProfile:
        """
        Build a full TableProfile including column definitions and statistics.
        Implementations should respect config.profile_sample_pct for large tables.
        """

    async def run_full_hydration(self) -> list[SchemaProfile]:
        """
        Orchestrates full schema hydration:
          1. Discover schemas (applying schema_filter)
          2. List tables in each schema (applying table_filter)
          3. Profile each table
        Returns a list of SchemaProfile objects.
        """
        results: list[SchemaProfile] = []
        schemas = await self.discover_schemas()

        # Apply schema filter
        if self.config.schema_filter:
            schemas = [s for s in schemas if s in self.config.schema_filter]

        for schema_name in schemas:
            tables = await self.list_tables(schema_name)

            # Apply table filter
            if self.config.table_filter:
                tables = [t for t in tables if t in self.config.table_filter]

            table_profiles: list[TableProfile] = []
            for table_name in tables:
                try:
                    profile = await self.profile_table(schema_name, table_name)
                    table_profiles.append(profile)
                except Exception as exc:
                    # Log error but continue — partial results are better than none
                    import structlog
                    log = structlog.get_logger()
                    log.error(
                        "table_profiling_failed",
                        schema=schema_name,
                        table=table_name,
                        error=str(exc),
                    )

            results.append(
                SchemaProfile(
                    database_name=self.config.database,
                    schema_name=schema_name,
                    tables=table_profiles,
                )
            )

        return results

    async def __aenter__(self) -> "BaseConnector":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.disconnect()
