"""
Seed lineage edges (via HTTP) and business terms (directly in catalog.db).

Run after services are up:
    python poc/seed_lineage_terms.py

Lineage is in-memory so must be re-run after each container restart.
Terms are persisted in catalog.db so only needed once.
"""

import json
import sqlite3
import urllib.request
import urllib.error

CATALOG_DB  = "poc/data/catalog.db"
LINEAGE_URL = "http://localhost:8008"
TERMS_URL   = "http://localhost:8004"

# ── Lineage edges ──────────────────────────────────────────────────────────────
# source_fqn ->target_fqn describes data flowing FROM source INTO target.

EDGES = [
    {
        "source_fqn":      "postgres.sales.public.orders",
        "target_fqn":      "postgres.analytics.dbt.fct_revenue_daily",
        "source_platform": "postgresql",
        "target_platform": "postgresql",
        "relationship":    "TRANSFORMED",
        "transformation_sql": "SELECT date_trunc('day', created_at) AS date_day, SUM(total_amount) AS revenue_usd, COUNT(*) AS order_count FROM orders WHERE status = 'completed' GROUP BY 1",
        "pipeline_id":     "dbt-daily-revenue",
    },
    {
        "source_fqn":      "postgres.sales.public.customers",
        "target_fqn":      "postgres.analytics.dbt.fct_revenue_daily",
        "source_platform": "postgresql",
        "target_platform": "postgresql",
        "relationship":    "JOINED",
        "transformation_sql": "JOIN customers ON orders.customer_id = customers.customer_id",
        "pipeline_id":     "dbt-daily-revenue",
    },
    {
        "source_fqn":      "postgres.product.public.events",
        "target_fqn":      "postgres.sales.public.orders",
        "source_platform": "postgresql",
        "target_platform": "postgresql",
        "relationship":    "DERIVED",
        "transformation_sql": "SELECT * FROM events WHERE event_type = 'order_placed'",
        "pipeline_id":     "events-to-orders",
    },
    {
        "source_fqn":      "postgres.sales.public.orders",
        "target_fqn":      "postgres.marketing.public.campaigns",
        "source_platform": "postgresql",
        "target_platform": "postgresql",
        "relationship":    "JOINED",
        "transformation_sql": "SELECT campaign_id, COUNT(order_id) AS conversions FROM orders JOIN campaigns USING (campaign_id) GROUP BY 1",
        "pipeline_id":     "campaign-attribution",
    },
    {
        "source_fqn":      "postgres.sales.public.orders",
        "target_fqn":      "mysql.hr.employees.employee_records",
        "source_platform": "postgresql",
        "target_platform": "mysql",
        "relationship":    "REFERENCED",
        "transformation_sql": "Revenue per rep joined from orders.sales_rep_id",
        "pipeline_id":     "hr-performance",
    },
]

# ── Business terms per asset (names only — stored in catalog.db) ───────────────

ASSET_TERMS = {
    "postgres.sales.public.orders": [
        "Order ID", "Revenue", "Transaction Date", "PII",
    ],
    "postgres.sales.public.customers": [
        "Customer", "PII", "GDPR", "KYC", "Master Data",
    ],
    "postgres.analytics.dbt.fct_revenue_daily": [
        "Revenue", "Fiscal Year", "Net Income", "Master Data",
    ],
    "mysql.hr.employees.employee_records": [
        "Employee ID", "PII", "Cost Center", "SLA",
    ],
    "postgres.marketing.public.campaigns": [
        "Revenue", "Customer", "SLA",
    ],
    "postgres.product.public.events": [
        "Data Lineage", "PII", "Transaction Date",
    ],
}


def post_json(url: str, payload: dict) -> dict | None:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def seed_lineage():
    print("\nSeeding lineage edges")
    for edge in EDGES:
        result = post_json(f"{LINEAGE_URL}/lineage/edge", edge)
        if result:
            print(f"  OK  {edge['source_fqn']} ->{edge['target_fqn']}  [{edge['relationship']}]")
        else:
            print(f"  FAIL  {edge['source_fqn']} ->{edge['target_fqn']}")


def seed_terms():
    print("\nWriting business terms to catalog.db")
    conn = sqlite3.connect(CATALOG_DB)
    for fqn, terms in ASSET_TERMS.items():
        conn.execute(
            "UPDATE assets SET suggested_terms = ? WHERE fqn = ?",
            (json.dumps(terms), fqn),
        )
        rows = conn.execute("SELECT changes()").fetchone()[0]
        status = "OK" if rows else "FAIL (not found)"
        print(f"  {status}  {fqn}: {', '.join(terms)}")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_lineage()
    seed_terms()
    print("\nDone. Lineage is in-memory — re-run this script after restarting lineage-service.")
