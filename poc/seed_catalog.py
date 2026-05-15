"""
Seed the POC catalog.db with realistic sample assets and columns.
Run from the project root:
    python poc/seed_catalog.py
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = "poc/data/catalog.db"

ASSETS = [
    {
        "fqn": "postgres.sales.public.orders",
        "source_type": "postgresql",
        "database_name": "sales",
        "schema_name": "public",
        "table_name": "orders",
        "description": "Customer orders including product, quantity, and payment details.",
        "domain": "Sales",
        "data_owner": "sales-team@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "CONFIDENTIAL",
        "row_count": 1_250_000,
        "size_bytes": 340_000_000,
        "quality_score": 0.94,
        "quality_grade": "A",
        "tags": {"env": "prod", "pii": "true"},
        "columns": [
            {"name": "order_id",    "data_type": "UUID",      "description": "Unique order identifier", "pii_classification": None,        "pii_sensitivity": "PUBLIC"},
            {"name": "customer_id", "data_type": "UUID",      "description": "Reference to customers table", "pii_classification": "IDENTIFIER", "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "email",       "data_type": "VARCHAR",   "description": "Customer email address", "pii_classification": "EMAIL",      "pii_sensitivity": "RESTRICTED"},
            {"name": "total_amount","data_type": "NUMERIC",   "description": "Order total in USD", "pii_classification": None,        "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "status",      "data_type": "VARCHAR",   "description": "Order fulfillment status", "pii_classification": None,        "pii_sensitivity": "INTERNAL"},
            {"name": "created_at",  "data_type": "TIMESTAMP", "description": "Order creation timestamp", "pii_classification": None,        "pii_sensitivity": "PUBLIC"},
        ],
    },
    {
        "fqn": "postgres.sales.public.customers",
        "source_type": "postgresql",
        "database_name": "sales",
        "schema_name": "public",
        "table_name": "customers",
        "description": "Master customer registry with contact and segmentation data.",
        "domain": "Sales",
        "data_owner": "sales-team@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "RESTRICTED",
        "row_count": 85_000,
        "size_bytes": 18_000_000,
        "quality_score": 0.88,
        "quality_grade": "B",
        "tags": {"env": "prod", "pii": "true", "gdpr": "true"},
        "columns": [
            {"name": "customer_id", "data_type": "UUID",    "description": "Unique customer ID", "pii_classification": "IDENTIFIER", "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "full_name",   "data_type": "VARCHAR", "description": "Customer full name", "pii_classification": "NAME",       "pii_sensitivity": "RESTRICTED"},
            {"name": "email",       "data_type": "VARCHAR", "description": "Primary email", "pii_classification": "EMAIL",      "pii_sensitivity": "RESTRICTED"},
            {"name": "phone",       "data_type": "VARCHAR", "description": "Contact phone number", "pii_classification": "PHONE",      "pii_sensitivity": "RESTRICTED"},
            {"name": "country",     "data_type": "VARCHAR", "description": "Country of residence", "pii_classification": None,        "pii_sensitivity": "INTERNAL"},
            {"name": "segment",     "data_type": "VARCHAR", "description": "Customer segment (SMB / Enterprise)", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "created_at",  "data_type": "TIMESTAMP", "description": "Account creation date", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
        ],
    },
    {
        "fqn": "postgres.analytics.dbt.fct_revenue_daily",
        "source_type": "postgresql",
        "database_name": "analytics",
        "schema_name": "dbt",
        "table_name": "fct_revenue_daily",
        "description": "Daily revenue fact table aggregated from orders. Refreshed every 6 hours via dbt.",
        "domain": "Finance",
        "data_owner": "data-platform@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "CONFIDENTIAL",
        "row_count": 1_095,
        "size_bytes": 512_000,
        "quality_score": 0.99,
        "quality_grade": "A",
        "tags": {"env": "prod", "dbt": "true", "tier": "gold"},
        "columns": [
            {"name": "date_day",       "data_type": "DATE",    "description": "Reporting date", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "revenue_usd",    "data_type": "NUMERIC", "description": "Total revenue in USD", "pii_classification": None, "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "order_count",    "data_type": "INTEGER", "description": "Number of completed orders", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "new_customers",  "data_type": "INTEGER", "description": "Count of first-time buyers", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "refund_amount",  "data_type": "NUMERIC", "description": "Total refunded amount", "pii_classification": None, "pii_sensitivity": "CONFIDENTIAL"},
        ],
    },
    {
        "fqn": "mysql.hr.employees.employee_records",
        "source_type": "mysql",
        "database_name": "hr",
        "schema_name": "employees",
        "table_name": "employee_records",
        "description": "HR employee master record including compensation and performance data.",
        "domain": "HR",
        "data_owner": "hr-admin@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "RESTRICTED",
        "row_count": 3_400,
        "size_bytes": 2_100_000,
        "quality_score": 0.91,
        "quality_grade": "A",
        "tags": {"env": "prod", "pii": "true", "sox": "true"},
        "columns": [
            {"name": "employee_id",  "data_type": "INT",      "description": "Unique employee identifier", "pii_classification": "IDENTIFIER", "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "full_name",    "data_type": "VARCHAR",  "description": "Legal full name", "pii_classification": "NAME", "pii_sensitivity": "RESTRICTED"},
            {"name": "email",        "data_type": "VARCHAR",  "description": "Corporate email", "pii_classification": "EMAIL", "pii_sensitivity": "RESTRICTED"},
            {"name": "ssn",          "data_type": "VARCHAR",  "description": "Social Security Number (encrypted)", "pii_classification": "GOVERNMENT_ID", "pii_sensitivity": "RESTRICTED"},
            {"name": "salary",       "data_type": "DECIMAL",  "description": "Annual base salary", "pii_classification": "FINANCIAL", "pii_sensitivity": "RESTRICTED"},
            {"name": "department",   "data_type": "VARCHAR",  "description": "Department name", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "hire_date",    "data_type": "DATE",     "description": "Date of hire", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
        ],
    },
    {
        "fqn": "postgres.marketing.public.campaigns",
        "source_type": "postgresql",
        "database_name": "marketing",
        "schema_name": "public",
        "table_name": "campaigns",
        "description": "Marketing campaign definitions, budgets, and performance metrics.",
        "domain": "Marketing",
        "data_owner": "marketing@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "INTERNAL",
        "row_count": 520,
        "size_bytes": 320_000,
        "quality_score": 0.82,
        "quality_grade": "B",
        "tags": {"env": "prod"},
        "columns": [
            {"name": "campaign_id",  "data_type": "UUID",    "description": "Campaign identifier", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "name",         "data_type": "VARCHAR", "description": "Campaign display name", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "channel",      "data_type": "VARCHAR", "description": "Marketing channel (email / paid / social)", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "budget_usd",   "data_type": "NUMERIC", "description": "Campaign budget in USD", "pii_classification": None, "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "start_date",   "data_type": "DATE",    "description": "Campaign start date", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "end_date",     "data_type": "DATE",    "description": "Campaign end date", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "impressions",  "data_type": "BIGINT",  "description": "Total ad impressions", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "conversions",  "data_type": "INTEGER", "description": "Number of conversions", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
        ],
    },
    {
        "fqn": "postgres.product.public.events",
        "source_type": "postgresql",
        "database_name": "product",
        "schema_name": "public",
        "table_name": "events",
        "description": "Raw product analytics events stream. Partitioned by day. Retention: 90 days.",
        "domain": "Product",
        "data_owner": "product-analytics@company.io",
        "data_steward": "steward@datacatalog.io",
        "sensitivity_level": "INTERNAL",
        "row_count": 48_000_000,
        "size_bytes": 12_000_000_000,
        "quality_score": 0.76,
        "quality_grade": "C",
        "tags": {"env": "prod", "partitioned": "true"},
        "columns": [
            {"name": "event_id",    "data_type": "UUID",      "description": "Unique event ID", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "user_id",     "data_type": "UUID",      "description": "Anonymous user identifier", "pii_classification": "IDENTIFIER", "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "event_type",  "data_type": "VARCHAR",   "description": "Event name (page_view, click, etc.)", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
            {"name": "properties",  "data_type": "JSONB",     "description": "Event properties payload", "pii_classification": None, "pii_sensitivity": "INTERNAL"},
            {"name": "ip_address",  "data_type": "VARCHAR",   "description": "Client IP address", "pii_classification": "IP_ADDRESS", "pii_sensitivity": "CONFIDENTIAL"},
            {"name": "occurred_at", "data_type": "TIMESTAMP", "description": "Event timestamp (UTC)", "pii_classification": None, "pii_sensitivity": "PUBLIC"},
        ],
    },
]


def seed(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS assets (
        asset_id TEXT PRIMARY KEY, fqn TEXT NOT NULL UNIQUE,
        source_id TEXT, source_type TEXT, database_name TEXT, schema_name TEXT,
        table_name TEXT, description TEXT, domain TEXT, data_owner TEXT,
        data_steward TEXT, sensitivity_level TEXT DEFAULT 'INTERNAL',
        row_count INTEGER, size_bytes INTEGER, quality_score REAL,
        quality_grade TEXT, tags TEXT, suggested_terms TEXT,
        is_active INTEGER NOT NULL DEFAULT 1, run_id TEXT,
        ingested_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS columns (
        column_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, fqn TEXT NOT NULL,
        column_name TEXT, data_type TEXT, description TEXT, is_nullable INTEGER,
        pii_classification TEXT, pii_category TEXT, sensitivity_level TEXT,
        suggested_terms TEXT, quality_score REAL, quality_grade TEXT,
        null_count INTEGER, distinct_count INTEGER, asset_fqn TEXT, ingested_at TEXT
    );
    """)

    now = datetime.now(timezone.utc).isoformat()

    for a in ASSETS:
        asset_id = str(uuid.uuid4())
        conn.execute("""
            INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            asset_id, a["fqn"], None, a["source_type"],
            a["database_name"], a["schema_name"], a["table_name"],
            a["description"], a.get("domain"), a.get("data_owner"), a.get("data_steward"),
            a.get("sensitivity_level", "INTERNAL"),
            a.get("row_count"), a.get("size_bytes"),
            a.get("quality_score"), a.get("quality_grade"),
            json.dumps(a.get("tags", {})), json.dumps([]),
            1, "seed-run", now, now,
        ))

        cols = a.get("columns", [])
        for col in cols:
            conn.execute("""
                INSERT OR REPLACE INTO columns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(uuid.uuid4()), asset_id,
                f"{a['fqn']}.{col['name']}",
                col["name"], col.get("data_type"), col.get("description"),
                1, col.get("pii_classification"), col.get("pii_classification"),
                col.get("pii_sensitivity", "PUBLIC"),
                json.dumps([]), None, None, None, None,
                a["fqn"], now,
            ))

    conn.commit()
    conn.close()
    print(f"Seeded {len(ASSETS)} assets into {db_path}")


if __name__ == "__main__":
    seed(DB_PATH)
