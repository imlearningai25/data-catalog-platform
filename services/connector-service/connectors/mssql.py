"""
Microsoft SQL Server connector.
Uses pyodbc with ODBC Driver 18 for SQL Server.
Supports SQL Server 2016+ and Azure SQL Database.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

try:
    import pyodbc
except ImportError:
    pyodbc = None

from .base import BaseConnector, ColumnProfile, ConnectionConfig, TableProfile

log = structlog.get_logger(__name__)

# Map MSSQL system_type_name → canonical type
MSSQL_TYPE_MAP = {
    "int": "INTEGER", "bigint": "BIGINT", "smallint": "SMALLINT",
    "tinyint": "TINYINT", "bit": "BOOLEAN", "decimal": "DECIMAL",
    "numeric": "NUMERIC", "money": "MONEY", "smallmoney": "MONEY",
    "float": "FLOAT", "real": "REAL", "datetime": "DATETIME",
    "datetime2": "DATETIME2", "smalldatetime": "DATETIME",
    "date": "DATE", "time": "TIME", "datetimeoffset": "TIMESTAMP WITH TIME ZONE",
    "char": "CHAR", "varchar": "VARCHAR", "text": "TEXT",
    "nchar": "NCHAR", "nvarchar": "NVARCHAR", "ntext": "NTEXT",
    "binary": "BINARY", "varbinary": "VARBINARY", "image": "IMAGE",
    "uniqueidentifier": "UUID", "xml": "XML", "json": "JSON",
    "geography": "GEOGRAPHY", "geometry": "GEOMETRY",
    "hierarchyid": "HIERARCHYID", "timestamp": "ROWVERSION",
    "rowversion": "ROWVERSION", "sql_variant": "SQL_VARIANT",
}


class MSSQLConnector(BaseConnector):
    """
    Connector for Microsoft SQL Server.
    Connection string format:
        DRIVER={ODBC Driver 18 for SQL Server};
        SERVER=host,port;DATABASE=db;UID=user;PWD=pass;
        Encrypt=yes;TrustServerCertificate=no;
    """

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._loop = asyncio.get_event_loop()

    # ------------------------------------------------------------------ #
    #  Connection lifecycle                                                #
    # ------------------------------------------------------------------ #

    def _build_connection_string(self) -> str:
        driver = self.config.extra_params.get("driver", "ODBC Driver 18 for SQL Server")
        encrypt = self.config.extra_params.get("encrypt", "yes")
        trust_cert = self.config.extra_params.get("trust_server_certificate", "no")
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.config.host},{self.config.port};"
            f"DATABASE={self.config.database};"
            f"UID={self.config.username};"
            f"PWD={self.config.password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust_cert};"
            f"Connection Timeout={self.config.connect_timeout_secs};"
        )

    async def connect(self) -> None:
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed")

        conn_str = self._build_connection_string()

        def _connect():
            conn = pyodbc.connect(conn_str, autocommit=True)
            conn.timeout = self.config.connect_timeout_secs
            return conn

        self._connection = await self._loop.run_in_executor(None, _connect)
        self._connected = True
        log.info("mssql_connected", host=self.config.host, database=self.config.database)

    async def disconnect(self) -> None:
        if self._connection:
            await self._loop.run_in_executor(None, self._connection.close)
            self._connected = False
            log.info("mssql_disconnected")

    async def test_connection(self) -> bool:
        try:
            await self._execute_query("SELECT 1 AS healthcheck")
            return True
        except Exception as exc:
            log.warning("mssql_connection_test_failed", error=str(exc))
            return False

    # ------------------------------------------------------------------ #
    #  Schema / table discovery                                            #
    # ------------------------------------------------------------------ #

    async def discover_schemas(self) -> list[str]:
        rows = await self._execute_query(
            """
            SELECT SCHEMA_NAME
            FROM   INFORMATION_SCHEMA.SCHEMATA
            WHERE  SCHEMA_NAME NOT IN ('sys','INFORMATION_SCHEMA','guest','db_owner',
                                       'db_accessadmin','db_securityadmin','db_ddladmin',
                                       'db_backupoperator','db_datareader','db_datawriter',
                                       'db_denydatareader','db_denydatawriter')
            ORDER  BY SCHEMA_NAME
            """
        )
        return [r[0] for r in rows]

    async def list_tables(self, schema_name: str) -> list[str]:
        rows = await self._execute_query(
            """
            SELECT TABLE_NAME
            FROM   INFORMATION_SCHEMA.TABLES
            WHERE  TABLE_SCHEMA = ?
              AND  TABLE_TYPE   IN ('BASE TABLE', 'VIEW')
            ORDER  BY TABLE_NAME
            """,
            (schema_name,),
        )
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ #
    #  Table profiling                                                     #
    # ------------------------------------------------------------------ #

    async def profile_table(self, schema_name: str, table_name: str) -> TableProfile:
        columns, pks, fks = await asyncio.gather(
            self._get_columns(schema_name, table_name),
            self._get_primary_keys(schema_name, table_name),
            self._get_foreign_keys(schema_name, table_name),
        )
        row_count, size_bytes, last_modified = await self._get_table_stats(schema_name, table_name)

        if self.config.enable_profiling and row_count and row_count > 0:
            columns = await self._profile_columns(schema_name, table_name, columns, row_count)

        return TableProfile(
            schema_name=schema_name,
            table_name=table_name,
            table_type="TABLE",
            row_count=row_count,
            size_bytes=size_bytes,
            last_modified=last_modified,
            columns=columns,
            primary_keys=pks,
            foreign_keys=fks,
        )

    async def _get_columns(self, schema: str, table: str) -> list[ColumnProfile]:
        rows = await self._execute_query(
            """
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                ep.value AS description
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN sys.extended_properties ep
                ON ep.major_id  = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
                AND ep.minor_id  = c.ORDINAL_POSITION
                AND ep.name      = 'MS_Description'
                AND ep.class     = 1
            WHERE c.TABLE_SCHEMA = ?
              AND c.TABLE_NAME   = ?
            ORDER BY c.ORDINAL_POSITION
            """,
            (schema, table),
        )
        return [
            ColumnProfile(
                name=r[0],
                data_type=MSSQL_TYPE_MAP.get(r[1].lower(), r[1].upper()),
                is_nullable=(r[2] == "YES"),
                max_length=r[3],
                precision=r[4],
                scale=r[5],
                description=str(r[6]) if r[6] else None,
            )
            for r in rows
        ]

    async def _get_table_stats(self, schema: str, table: str) -> tuple[int | None, int | None, datetime | None]:
        rows = await self._execute_query(
            """
            SELECT
                p.rows                                  AS row_count,
                SUM(a.total_pages) * 8 * 1024           AS size_bytes,
                o.modify_date                           AS last_modified
            FROM sys.tables t
            JOIN sys.schemas s      ON s.schema_id = t.schema_id
            JOIN sys.indexes i      ON i.object_id = t.object_id AND i.index_id <= 1
            JOIN sys.partitions p   ON p.object_id = i.object_id AND p.index_id = i.index_id
            JOIN sys.allocation_units a ON a.container_id = p.partition_id
            JOIN sys.objects o      ON o.object_id = t.object_id
            WHERE s.name = ? AND t.name = ?
            GROUP BY p.rows, o.modify_date
            """,
            (schema, table),
        )
        if rows:
            return rows[0][0], rows[0][1], rows[0][2]
        return None, None, None

    async def _get_primary_keys(self, schema: str, table: str) -> list[str]:
        rows = await self._execute_query(
            """
            SELECT kcu.COLUMN_NAME
            FROM   INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN   INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA   = kcu.TABLE_SCHEMA
            WHERE  tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND  tc.TABLE_SCHEMA    = ?
              AND  tc.TABLE_NAME      = ?
            ORDER  BY kcu.ORDINAL_POSITION
            """,
            (schema, table),
        )
        return [r[0] for r in rows]

    async def _get_foreign_keys(self, schema: str, table: str) -> list[dict]:
        rows = await self._execute_query(
            """
            SELECT
                kcu.COLUMN_NAME        AS fk_column,
                ccu.TABLE_SCHEMA       AS ref_schema,
                ccu.TABLE_NAME         AS ref_table,
                ccu.COLUMN_NAME        AS ref_column
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
                ON ccu.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
            WHERE kcu.TABLE_SCHEMA = ? AND kcu.TABLE_NAME = ?
            """,
            (schema, table),
        )
        return [
            {"column": r[0], "referenced_schema": r[1],
             "referenced_table": r[2], "referenced_column": r[3]}
            for r in rows
        ]

    async def _profile_columns(
        self, schema: str, table: str,
        columns: list[ColumnProfile], row_count: int
    ) -> list[ColumnProfile]:
        """
        Use TABLESAMPLE to profile up to profile_sample_pct of rows.
        For small tables (< 10k rows) we read everything.
        """
        sample_pct = self.config.profile_sample_pct
        sample_clause = (
            f"TABLESAMPLE ({sample_pct} PERCENT)"
            if row_count > 10_000 else ""
        )
        numeric_types = {"INTEGER", "BIGINT", "SMALLINT", "DECIMAL", "FLOAT",
                         "NUMERIC", "TINYINT", "REAL", "MONEY"}

        for col in columns:
            col_expr = f"[{col.name}]"
            try:
                stats_rows = await self._execute_query(
                    f"""
                    SELECT
                        COUNT(*) - COUNT({col_expr})          AS null_count,
                        COUNT(DISTINCT {col_expr})             AS distinct_count
                    FROM [{schema}].[{table}] {sample_clause}
                    """
                )
                if stats_rows:
                    col.null_count = stats_rows[0][0]
                    col.distinct_count = stats_rows[0][1]

                if col.data_type in numeric_types:
                    num_rows = await self._execute_query(
                        f"""
                        SELECT
                            MIN(CAST({col_expr} AS FLOAT)),
                            MAX(CAST({col_expr} AS FLOAT)),
                            AVG(CAST({col_expr} AS FLOAT))
                        FROM [{schema}].[{table}] {sample_clause}
                        """
                    )
                    if num_rows:
                        col.min_value = num_rows[0][0]
                        col.max_value = num_rows[0][1]
                        col.avg_value = num_rows[0][2]

                # Sample values (top 5 most frequent)
                sample_rows = await self._execute_query(
                    f"""
                    SELECT TOP 5 CAST({col_expr} AS NVARCHAR(MAX))
                    FROM [{schema}].[{table}] {sample_clause}
                    WHERE {col_expr} IS NOT NULL
                    GROUP BY {col_expr}
                    ORDER BY COUNT(*) DESC
                    """
                )
                col.sample_values = [r[0] for r in sample_rows]

            except Exception as exc:
                log.warning(
                    "column_stat_failed",
                    schema=schema, table=table, column=col.name, error=str(exc)
                )

        return columns

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    async def _execute_query(self, sql: str, params: tuple = ()) -> list[tuple]:
        def _run():
            with self._connection.cursor() as cur:
                cur.execute(sql, params) if params else cur.execute(sql)
                return cur.fetchall()

        return await self._loop.run_in_executor(None, _run)
