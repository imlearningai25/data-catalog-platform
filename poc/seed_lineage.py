#!/usr/bin/env python3
"""
POC Lineage Seed Script
Generates a realistic data lineage graph and stores it in
poc/data/lineage.db.  Also prints an ASCII lineage DAG so
you can see the relationships without needing DataHub or Grafana.

Run AFTER seed_data.py:
  python poc/seed_lineage.py
  python poc/seed_lineage.py --dag          # show ASCII DAG only
  python poc/seed_lineage.py --columns      # show column-level lineage
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "lineage.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ── ANSI colour helpers ────────────────────────────────────────
def _c(code, t): return f"\033[{code}m{t}\033[0m"
BOLD    = lambda t: _c("1", t)
DIM     = lambda t: _c("2", t)
CYAN    = lambda t: _c("36", t)
GREEN   = lambda t: _c("32", t)
YELLOW  = lambda t: _c("33", t)
MAGENTA = lambda t: _c("35", t)
RED     = lambda t: _c("31", t)
BLUE    = lambda t: _c("34", t)


# ══════════════════════════════════════════════════════════════
# Lineage model
# ══════════════════════════════════════════════════════════════

@dataclass
class Dataset:
    """Represents a table / view in the lineage graph."""
    platform: str
    schema:   str
    name:     str
    layer:    str   # raw | staging | curated | serving | ml_feature
    description: str = ""

    @property
    def fqn(self) -> str:
        return f"{self.platform}://{self.schema}.{self.name}"

    @property
    def urn(self) -> str:
        return f"urn:li:dataset:(urn:li:dataPlatform:{self.platform},{self.schema}.{self.name},PROD)"


@dataclass
class ColumnLineage:
    """Column-level transformation between two datasets."""
    source_col:    str
    target_col:    str
    transform_type: str   # DIRECT | AGGREGATED | DERIVED | FILTERED | JOINED
    expression:    str = ""


@dataclass
class LineageEdge:
    """One upstream → downstream relationship, optionally with column mappings."""
    source:      Dataset
    target:      Dataset
    job_name:    str
    job_type:    str   # ETL | ELT | STREAM | ML_TRAINING | REPORT
    schedule:    str   # cron or description
    description: str
    col_lineage: list[ColumnLineage] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# Dataset catalogue (nodes in the DAG)
# ══════════════════════════════════════════════════════════════

# ── Raw / source layer (connector-service hydrates these) ─────
D_CUSTOMER     = Dataset("teradata", "FINANCE_DB", "CUSTOMER_MASTER",
                         "raw", "Core customer master record")
D_TRANSACTIONS = Dataset("teradata", "FINANCE_DB", "PAYMENT_TRANSACTIONS",
                         "raw", "All payment and transfer transactions")
D_EMPLOYEES    = Dataset("teradata", "HR_DB",      "EMPLOYEE_RECORDS",
                         "raw", "All active and terminated employee HR records")
D_PRODUCTS     = Dataset("teradata", "PRODUCT_DB", "PRODUCT_CATALOG",
                         "raw", "Master product list with pricing")
D_REVIEWS      = Dataset("teradata", "PRODUCT_DB", "PRODUCT_REVIEWS",
                         "raw", "Customer product reviews and ratings")

# ── Staging layer (light cleaning / type casting) ─────────────
D_STG_CUSTOMER = Dataset("bigquery", "staging",    "stg_customers",
                         "staging", "Cleaned customer records with PII masked")
D_STG_TXNS     = Dataset("bigquery", "staging",    "stg_transactions",
                         "staging", "Validated and deduplicated transactions")
D_STG_PRODUCTS = Dataset("bigquery", "staging",    "stg_products",
                         "staging", "Normalised product catalogue")

# ── Curated / conformed layer ─────────────────────────────────
D_ACCT_SUMMARY = Dataset("teradata", "FINANCE_DB", "ACCOUNT_SUMMARY",
                         "curated", "Monthly account balance summary")
D_FRAUD_SCORES = Dataset("bigquery", "curated",    "fraud_scores",
                         "curated", "ML-derived fraud risk scores per transaction")
D_CUST_360     = Dataset("bigquery", "curated",    "customer_360",
                         "curated", "Single customer view: demographics + spend + risk")
D_PROD_METRICS = Dataset("bigquery", "curated",    "product_metrics",
                         "curated", "Aggregated product performance metrics")

# ── Serving / reporting layer ─────────────────────────────────
D_RISK_REPORT  = Dataset("bigquery", "serving",    "risk_dashboard_daily",
                         "serving", "Daily risk KPIs fed to Grafana / Looker")
D_EXEC_SUMMARY = Dataset("bigquery", "serving",    "executive_summary",
                         "serving", "Weekly executive KPI snapshot")
D_PRODUCT_RPT  = Dataset("bigquery", "serving",    "product_performance_report",
                         "serving", "Weekly product performance for merchandising team")

# ── ML feature store ──────────────────────────────────────────
D_FRAUD_FEATS  = Dataset("bigquery", "ml_features", "fraud_detection_features",
                         "ml_feature", "Feature vector for fraud detection model v2")
D_CHURN_FEATS  = Dataset("bigquery", "ml_features", "churn_prediction_features",
                         "ml_feature", "Feature vector for customer churn model")


# ══════════════════════════════════════════════════════════════
# Lineage edges (the DAG)
# ══════════════════════════════════════════════════════════════

EDGES: list[LineageEdge] = [

    # ── Raw → Staging ─────────────────────────────────────────
    LineageEdge(
        source=D_CUSTOMER, target=D_STG_CUSTOMER,
        job_name="etl_stage_customers",
        job_type="ETL",
        schedule="0 2 * * *",    # 02:00 daily
        description="Mask PII, standardise phone/email format, cast dates",
        col_lineage=[
            ColumnLineage("CUSTOMER_ID",    "customer_id",      "DIRECT"),
            ColumnLineage("FIRST_NAME",     "full_name",        "DERIVED",
                          "CONCAT(FIRST_NAME, ' ', LAST_NAME)"),
            ColumnLineage("LAST_NAME",      "full_name",        "DERIVED",
                          "CONCAT(FIRST_NAME, ' ', LAST_NAME)"),
            ColumnLineage("EMAIL_ADDRESS",  "email_masked",     "DERIVED",
                          "REGEXP_REPLACE(EMAIL_ADDRESS, r'(.{2}).+(@.+)', r'\\1***\\2')"),
            ColumnLineage("ACCOUNT_BALANCE","account_balance",  "DIRECT"),
            ColumnLineage("CUSTOMER_SEGMENT","segment",         "DIRECT"),
            ColumnLineage("CREATED_DATE",   "created_at",       "DIRECT"),
            ColumnLineage("IS_ACTIVE",      "is_active",        "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_TRANSACTIONS, target=D_STG_TXNS,
        job_name="etl_stage_transactions",
        job_type="STREAM",
        schedule="continuous (Kafka)",
        description="Deduplicate, validate amounts, enrich with merchant category",
        col_lineage=[
            ColumnLineage("TRANSACTION_ID",     "transaction_id",    "DIRECT"),
            ColumnLineage("CUSTOMER_ID",        "customer_id",       "DIRECT"),
            ColumnLineage("TRANSACTION_DATE",   "txn_timestamp",     "DIRECT"),
            ColumnLineage("TRANSACTION_AMOUNT", "amount_usd",        "DERIVED",
                          "TRANSACTION_AMOUNT * fx_rate_to_usd"),
            ColumnLineage("CURRENCY_CODE",      "currency_code",     "DIRECT"),
            ColumnLineage("STATUS",             "is_successful",     "DERIVED",
                          "STATUS = 'COMPLETED'"),
            ColumnLineage("FRAUD_SCORE",        "fraud_score",       "DIRECT"),
            ColumnLineage("CHANNEL",            "channel",           "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_PRODUCTS, target=D_STG_PRODUCTS,
        job_name="etl_stage_products",
        job_type="ETL",
        schedule="0 3 * * *",
        description="Normalise categories, compute margin, flag discontinued items",
        col_lineage=[
            ColumnLineage("PRODUCT_ID",    "product_id",    "DIRECT"),
            ColumnLineage("PRODUCT_CODE",  "sku",           "DIRECT"),
            ColumnLineage("CATEGORY_NAME", "category",      "DIRECT"),
            ColumnLineage("UNIT_PRICE",    "retail_price",  "DIRECT"),
            ColumnLineage("COST_PRICE",    "cost_price",    "DIRECT"),
            ColumnLineage("UNIT_PRICE",    "margin_pct",    "DERIVED",
                          "(UNIT_PRICE - COST_PRICE) / UNIT_PRICE"),
            ColumnLineage("IS_ACTIVE",     "is_active",     "DIRECT"),
        ],
    ),

    # ── Raw / Staging → Curated ───────────────────────────────
    LineageEdge(
        source=D_TRANSACTIONS, target=D_ACCT_SUMMARY,
        job_name="etl_account_aggregation",
        job_type="ETL",
        schedule="0 4 1 * *",    # 1st of each month
        description="Aggregate monthly debits/credits per customer account",
        col_lineage=[
            ColumnLineage("CUSTOMER_ID",        "customer_id",      "DIRECT"),
            ColumnLineage("TRANSACTION_AMOUNT", "total_credits",    "AGGREGATED",
                          "SUM(CASE WHEN STATUS='COMPLETED' AND type='CREDIT' THEN TRANSACTION_AMOUNT END)"),
            ColumnLineage("TRANSACTION_AMOUNT", "total_debits",     "AGGREGATED",
                          "SUM(CASE WHEN STATUS='COMPLETED' AND type='DEBIT' THEN TRANSACTION_AMOUNT END)"),
            ColumnLineage("TRANSACTION_DATE",   "summary_month",    "DERIVED",
                          "DATE_TRUNC(TRANSACTION_DATE, MONTH)"),
        ],
    ),
    LineageEdge(
        source=D_CUSTOMER, target=D_ACCT_SUMMARY,
        job_name="etl_account_aggregation",
        job_type="ETL",
        schedule="0 4 1 * *",
        description="Join customer opening balance for account summary",
        col_lineage=[
            ColumnLineage("ACCOUNT_BALANCE", "opening_balance", "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_STG_TXNS, target=D_FRAUD_SCORES,
        job_name="ml_fraud_scoring",
        job_type="ML_TRAINING",
        schedule="0 1 * * 0",    # weekly
        description="XGBoost model — scores each transaction for fraud probability",
        col_lineage=[
            ColumnLineage("transaction_id", "transaction_id",   "DIRECT"),
            ColumnLineage("amount_usd",     "fraud_score",      "DERIVED",
                          "model.predict([amount, channel, hour, merchant_category])"),
            ColumnLineage("amount_usd",     "risk_tier",        "DERIVED",
                          "CASE WHEN fraud_score > 0.9 THEN 'HIGH' "
                          "WHEN fraud_score > 0.5 THEN 'MEDIUM' ELSE 'LOW' END"),
            ColumnLineage("fraud_score",    "model_version",    "DERIVED",
                          "'fraud-v2.3.1'"),
        ],
    ),
    LineageEdge(
        source=D_STG_CUSTOMER, target=D_CUST_360,
        job_name="etl_customer_360",
        job_type="ELT",
        schedule="0 5 * * *",
        description="Join demographics, spend summary, risk score into unified view",
        col_lineage=[
            ColumnLineage("customer_id",    "customer_id",      "DIRECT"),
            ColumnLineage("full_name",      "full_name",        "DIRECT"),
            ColumnLineage("segment",        "segment",          "DIRECT"),
            ColumnLineage("account_balance","lifetime_value",   "DERIVED",
                          "account_balance + SUM(total_credits) OVER(PARTITION BY customer_id)"),
        ],
    ),
    LineageEdge(
        source=D_ACCT_SUMMARY, target=D_CUST_360,
        job_name="etl_customer_360",
        job_type="ELT",
        schedule="0 5 * * *",
        description="Enrich customer view with monthly spend behaviour",
        col_lineage=[
            ColumnLineage("total_credits",  "avg_monthly_spend", "AGGREGATED",
                          "AVG(total_credits) OVER(PARTITION BY customer_id)"),
            ColumnLineage("total_debits",   "avg_monthly_debits","AGGREGATED",
                          "AVG(total_debits) OVER(PARTITION BY customer_id)"),
        ],
    ),
    LineageEdge(
        source=D_FRAUD_SCORES, target=D_CUST_360,
        job_name="etl_customer_360",
        job_type="ELT",
        schedule="0 5 * * *",
        description="Attach latest fraud risk score to customer profile",
        col_lineage=[
            ColumnLineage("risk_tier",   "fraud_risk_tier",   "DIRECT"),
            ColumnLineage("fraud_score", "max_fraud_score_90d","AGGREGATED",
                          "MAX(fraud_score) OVER(PARTITION BY customer_id ORDER BY "
                          "txn_timestamp ROWS BETWEEN 90 PRECEDING AND CURRENT ROW)"),
        ],
    ),
    LineageEdge(
        source=D_STG_PRODUCTS, target=D_PROD_METRICS,
        job_name="etl_product_metrics",
        job_type="ELT",
        schedule="0 6 * * *",
        description="Join products with review aggregates and inventory health",
        col_lineage=[
            ColumnLineage("product_id",   "product_id",        "DIRECT"),
            ColumnLineage("retail_price", "avg_selling_price", "DIRECT"),
            ColumnLineage("margin_pct",   "margin_pct",        "DIRECT"),
            ColumnLineage("is_active",    "is_active",         "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_REVIEWS, target=D_PROD_METRICS,
        job_name="etl_product_metrics",
        job_type="ELT",
        schedule="0 6 * * *",
        description="Aggregate review stats per product",
        col_lineage=[
            ColumnLineage("rating",       "avg_rating",        "AGGREGATED",
                          "AVG(rating)"),
            ColumnLineage("review_id",    "review_count",      "AGGREGATED",
                          "COUNT(review_id)"),
            ColumnLineage("is_verified",  "verified_review_pct","AGGREGATED",
                          "AVG(is_verified) * 100"),
        ],
    ),

    # ── Curated → Serving ─────────────────────────────────────
    LineageEdge(
        source=D_CUST_360, target=D_RISK_REPORT,
        job_name="rpt_risk_dashboard",
        job_type="REPORT",
        schedule="0 7 * * *",
        description="Daily risk KPIs: high-risk customer counts, exposure by segment",
        col_lineage=[
            ColumnLineage("fraud_risk_tier",     "high_risk_count",   "AGGREGATED",
                          "COUNT(*) FILTER(WHERE fraud_risk_tier='HIGH')"),
            ColumnLineage("max_fraud_score_90d", "p99_fraud_score",   "AGGREGATED",
                          "PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY max_fraud_score_90d)"),
            ColumnLineage("segment",             "segment",           "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_FRAUD_SCORES, target=D_RISK_REPORT,
        job_name="rpt_risk_dashboard",
        job_type="REPORT",
        schedule="0 7 * * *",
        description="Real-time fraud event counts for dashboard",
        col_lineage=[
            ColumnLineage("risk_tier", "fraud_events_today", "AGGREGATED",
                          "COUNT(*) FILTER(WHERE risk_tier='HIGH' AND DATE(scored_at)=CURRENT_DATE)"),
        ],
    ),
    LineageEdge(
        source=D_CUST_360,     target=D_EXEC_SUMMARY,
        job_name="rpt_executive_summary",
        job_type="REPORT",
        schedule="0 8 * * 1",   # Monday 08:00
        description="Weekly executive snapshot: revenue, active customers, churn risk",
        col_lineage=[
            ColumnLineage("lifetime_value",  "total_platform_revenue", "AGGREGATED",
                          "SUM(lifetime_value)"),
            ColumnLineage("customer_id",     "active_customers_wow",   "AGGREGATED",
                          "COUNT(DISTINCT customer_id) WHERE last_txn > CURRENT_DATE - 7"),
        ],
    ),
    LineageEdge(
        source=D_ACCT_SUMMARY, target=D_EXEC_SUMMARY,
        job_name="rpt_executive_summary",
        job_type="REPORT",
        schedule="0 8 * * 1",
        description="Total credits/debits for the week",
        col_lineage=[
            ColumnLineage("total_credits", "weekly_credits", "AGGREGATED", "SUM(total_credits)"),
            ColumnLineage("total_debits",  "weekly_debits",  "AGGREGATED", "SUM(total_debits)"),
        ],
    ),
    LineageEdge(
        source=D_PROD_METRICS, target=D_PRODUCT_RPT,
        job_name="rpt_product_performance",
        job_type="REPORT",
        schedule="0 9 * * 1",
        description="Weekly product report for merchandising: top sellers, low inventory",
        col_lineage=[
            ColumnLineage("avg_rating",         "avg_rating",    "DIRECT"),
            ColumnLineage("review_count",        "review_count",  "DIRECT"),
            ColumnLineage("margin_pct",          "margin_pct",    "DIRECT"),
            ColumnLineage("avg_selling_price",   "price",         "DIRECT"),
        ],
    ),

    # ── Curated → ML Features ─────────────────────────────────
    LineageEdge(
        source=D_STG_TXNS,  target=D_FRAUD_FEATS,
        job_name="feature_eng_fraud",
        job_type="ML_TRAINING",
        schedule="0 0 * * *",
        description="Engineer time-windowed transaction features for fraud model",
        col_lineage=[
            ColumnLineage("transaction_id", "transaction_id",        "DIRECT"),
            ColumnLineage("amount_usd",     "txn_amount_z_score",    "DERIVED",
                          "(amount_usd - mean_amount) / stddev_amount"),
            ColumnLineage("amount_usd",     "spend_7d_rolling_sum",  "AGGREGATED",
                          "SUM(amount_usd) OVER(PARTITION BY customer_id "
                          "ORDER BY txn_timestamp ROWS BETWEEN 7 PRECEDING AND CURRENT ROW)"),
            ColumnLineage("channel",        "channel_encoded",       "DERIVED",
                          "one_hot_encode(channel)"),
            ColumnLineage("is_successful",  "label",                 "DIRECT"),
        ],
    ),
    LineageEdge(
        source=D_CUST_360,  target=D_CHURN_FEATS,
        job_name="feature_eng_churn",
        job_type="ML_TRAINING",
        schedule="0 0 * * 0",
        description="Engineer customer-level features for churn prediction model",
        col_lineage=[
            ColumnLineage("customer_id",        "customer_id",          "DIRECT"),
            ColumnLineage("avg_monthly_spend",  "spend_trend_3m",       "DERIVED",
                          "avg_monthly_spend - LAG(avg_monthly_spend, 3)"),
            ColumnLineage("segment",            "segment_encoded",      "DERIVED",
                          "label_encode(segment)"),
            ColumnLineage("fraud_risk_tier",    "risk_score",           "DERIVED",
                          "CASE WHEN fraud_risk_tier='HIGH' THEN 1.0 "
                          "WHEN fraud_risk_tier='MEDIUM' THEN 0.5 ELSE 0.0 END"),
            ColumnLineage("lifetime_value",     "lifetime_value_log",   "DERIVED",
                          "LOG(lifetime_value + 1)"),
        ],
    ),
]


# ══════════════════════════════════════════════════════════════
# SQLite persistence
# ══════════════════════════════════════════════════════════════

def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lineage_edges (
            edge_id      TEXT PRIMARY KEY,
            source_urn   TEXT NOT NULL,
            source_fqn   TEXT NOT NULL,
            source_layer TEXT,
            target_urn   TEXT NOT NULL,
            target_fqn   TEXT NOT NULL,
            target_layer TEXT,
            job_name     TEXT NOT NULL,
            job_type     TEXT NOT NULL,
            schedule     TEXT,
            description  TEXT,
            created_at   TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS column_lineage (
            id             TEXT PRIMARY KEY,
            edge_id        TEXT NOT NULL,
            source_col     TEXT NOT NULL,
            target_col     TEXT NOT NULL,
            transform_type TEXT NOT NULL,
            expression     TEXT,
            FOREIGN KEY (edge_id) REFERENCES lineage_edges(edge_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_src ON lineage_edges(source_urn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_tgt ON lineage_edges(target_urn)")
    conn.commit()


def persist_edges(conn: sqlite3.Connection, edges: list[LineageEdge]):
    now = datetime.now(timezone.utc).isoformat()
    for e in edges:
        edge_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO lineage_edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (edge_id, e.source.urn, e.source.fqn, e.source.layer,
             e.target.urn, e.target.fqn, e.target.layer,
             e.job_name, e.job_type, e.schedule, e.description, now),
        )
        for cl in e.col_lineage:
            conn.execute(
                "INSERT OR IGNORE INTO column_lineage VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), edge_id,
                 cl.source_col, cl.target_col, cl.transform_type, cl.expression),
            )
    conn.commit()


# ══════════════════════════════════════════════════════════════
# ASCII DAG renderer
# ══════════════════════════════════════════════════════════════

LAYER_ORDER = ["raw", "staging", "curated", "ml_feature", "serving"]
LAYER_COLOURS = {
    "raw":        BLUE,
    "staging":    CYAN,
    "curated":    YELLOW,
    "ml_feature": MAGENTA,
    "serving":    GREEN,
}
JOB_TYPE_ICONS = {
    "ETL":         "⚙",
    "ELT":         "⚙",
    "STREAM":      "~",
    "ML_TRAINING": "*",
    "REPORT":      "#",
}


def _short(dataset: Dataset) -> str:
    return f"{dataset.schema}.{dataset.name}"


def print_dag(edges: list[LineageEdge]):
    print(f"\n{BOLD('═' * 72)}")
    print(BOLD(CYAN("  DATA LINEAGE DAG")))
    print('─' * 72)

    # Collect all datasets keyed by fqn
    all_ds: dict[str, Dataset] = {}
    for e in edges:
        all_ds[e.source.fqn] = e.source
        all_ds[e.target.fqn] = e.target

    # Group by layer
    by_layer: dict[str, list[Dataset]] = {l: [] for l in LAYER_ORDER}
    for ds in all_ds.values():
        by_layer.setdefault(ds.layer, []).append(ds)

    # Build adjacency: source_fqn → list[(target_fqn, edge)]
    adj: dict[str, list[tuple[str, LineageEdge]]] = {}
    for e in edges:
        adj.setdefault(e.source.fqn, [])
        # Only add unique target+job combos for display
        if not any(t == e.target.fqn and j.job_name == e.job_name
                   for t, j in adj[e.source.fqn]):
            adj[e.source.fqn].append((e.target.fqn, e))

    # Print layer by layer
    for layer in LAYER_ORDER:
        datasets = by_layer.get(layer, [])
        if not datasets:
            continue
        colour = LAYER_COLOURS.get(layer, DIM)
        print(f"\n  {colour(BOLD(f'[ {layer.upper()} LAYER ]'))}")

        for ds in sorted(datasets, key=lambda d: d.name):
            ds_label = colour(f"  {_short(ds):<38}")
            print(f"{ds_label}  {DIM(ds.description[:38] if ds.description else '')}")

            # Show outbound edges
            for target_fqn, edge in adj.get(ds.fqn, []):
                tgt = all_ds[target_fqn]
                tgt_colour = LAYER_COLOURS.get(tgt.layer, DIM)
                icon = JOB_TYPE_ICONS.get(edge.job_type, "→")
                print(f"          {DIM('└─')} {icon} {DIM(edge.job_name):<35}"
                      f" → {tgt_colour(_short(tgt))}")

    # Legend
    print(f"\n  {'─' * 68}")
    print(f"  Legend:  ", end="")
    for jt, icon in JOB_TYPE_ICONS.items():
        print(f"{icon}={jt}  ", end="")
    print()
    print(f"  Layers: ", end="")
    for layer, col in LAYER_COLOURS.items():
        print(f"{col(layer)}  ", end="")
    print()
    print(f"\n  Datasets: {BOLD(str(len(all_ds)))}   "
          f"Edges: {BOLD(str(len(edges)))}   "
          f"Unique jobs: {BOLD(str(len({e.job_name for e in edges})))}")
    print(BOLD('═' * 72))


def print_column_lineage(edges: list[LineageEdge]):
    print(f"\n{BOLD('═' * 72)}")
    print(BOLD(CYAN("  COLUMN-LEVEL LINEAGE")))

    # Group edges by job
    by_job: dict[str, list[LineageEdge]] = {}
    for e in edges:
        by_job.setdefault(e.job_name, []).append(e)

    for job_name, job_edges in sorted(by_job.items()):
        all_cols = [cl for e in job_edges for cl in e.col_lineage]
        if not all_cols:
            continue

        src_names = {e.source.fqn for e in job_edges}
        tgt_names = {e.target.fqn for e in job_edges}

        print(f"\n  {BOLD(YELLOW(job_name))}  "
              f"{DIM('(' + job_edges[0].job_type + '  ' + job_edges[0].schedule + ')')}")
        print(f"  {DIM('Sources:')} {', '.join(_short(e.source) for e in job_edges[:2])}")
        print(f"  {DIM('Target:')}  {_short(job_edges[0].target)}")
        print(f"  {'─' * 66}")
        print(f"  {'Source column':<28} {'→'} {'Target column':<28} {'Transform'}")
        print(f"  {'·' * 66}")

        seen = set()
        for cl in all_cols:
            key = (cl.source_col, cl.target_col)
            if key in seen:
                continue
            seen.add(key)
            tfm_colour = {
                "DIRECT":     GREEN,
                "AGGREGATED": YELLOW,
                "DERIVED":    MAGENTA,
                "FILTERED":   CYAN,
                "JOINED":     BLUE,
            }.get(cl.transform_type, DIM)
            expr_short = (cl.expression[:30] + "…") if len(cl.expression) > 30 else cl.expression
            print(f"  {CYAN(cl.source_col):<36}"
                  f"{'→':^3}"
                  f"{CYAN(cl.target_col):<36}"
                  f" {tfm_colour(cl.transform_type)}"
                  f"{DIM(' — ' + expr_short) if expr_short else ''}")

    print(f"\n{BOLD('═' * 72)}\n")


def print_impact_analysis(edges: list[LineageEdge], start_fqn: str):
    """Show all downstream datasets affected if start_fqn changes."""
    # Build adjacency
    adj: dict[str, set[str]] = {}
    all_ds: dict[str, Dataset] = {}
    for e in edges:
        all_ds[e.source.fqn] = e.source
        all_ds[e.target.fqn] = e.target
        adj.setdefault(e.source.fqn, set()).add(e.target.fqn)

    if start_fqn not in all_ds:
        print(f"  Dataset '{start_fqn}' not found in lineage graph.")
        return

    # BFS
    visited = set()
    queue   = [start_fqn]
    order   = []
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        order.append(current)
        queue.extend(adj.get(current, []))

    print(f"\n{BOLD('═' * 72)}")
    print(BOLD(CYAN(f"  IMPACT ANALYSIS — {start_fqn}")))
    print(f"  Changing this dataset would affect {BOLD(str(len(order) - 1))} downstream datasets:\n")
    for i, fqn in enumerate(order):
        ds = all_ds[fqn]
        col = LAYER_COLOURS.get(ds.layer, DIM)
        prefix = "  ◉ SOURCE" if i == 0 else f"  {'  ' * min(i, 4)}└─ {i}."
        print(f"{prefix} {col(_short(ds))}  {DIM('(' + ds.layer + ')')}")
    print(BOLD('═' * 72))


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main(show_dag: bool = True, show_columns: bool = False,
         show_impact: str | None = None):

    print(f"\n  Seeding lineage graph → {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    persist_edges(conn, EDGES)
    conn.close()

    # Summary stats
    conn2 = sqlite3.connect(str(DB_PATH))
    n_edges  = conn2.execute("SELECT COUNT(*) FROM lineage_edges").fetchone()[0]
    n_cols   = conn2.execute("SELECT COUNT(*) FROM column_lineage").fetchone()[0]
    n_nodes  = conn2.execute(
        "SELECT COUNT(DISTINCT source_urn) + COUNT(DISTINCT target_urn) FROM lineage_edges"
    ).fetchone()[0]
    conn2.close()

    print(f"  Datasets (nodes)     : {BOLD(str(len({e.source.fqn for e in EDGES} | {e.target.fqn for e in EDGES})))}")
    print(f"  Lineage edges        : {BOLD(str(n_edges))}")
    print(f"  Column mappings      : {BOLD(str(n_cols))}")
    print(f"  Unique ETL/ML jobs   : {BOLD(str(len({e.job_name for e in EDGES})))}")
    print(f"\n  {GREEN('Lineage database ready.')}\n")

    if show_dag:
        print_dag(EDGES)

    if show_columns:
        print_column_lineage(EDGES)

    if show_impact:
        # Find dataset by short name match
        all_ds = {e.source.fqn: e.source for e in EDGES}
        all_ds.update({e.target.fqn: e.target for e in EDGES})
        matches = [fqn for fqn in all_ds if show_impact.lower() in fqn.lower()]
        if matches:
            print_impact_analysis(EDGES, matches[0])
        else:
            print(f"  No dataset matching '{show_impact}' found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed and visualise POC lineage data")
    parser.add_argument("--dag",     "-d", action="store_true",
                        help="Print the full lineage DAG (default on)")
    parser.add_argument("--columns", "-c", action="store_true",
                        help="Print column-level lineage per job")
    parser.add_argument("--impact",  "-i", metavar="DATASET",
                        help="Show impact analysis for a dataset (e.g. CUSTOMER_MASTER)")
    parser.add_argument("--all",     "-a", action="store_true",
                        help="Show DAG + column lineage + impact for CUSTOMER_MASTER")
    args = parser.parse_args()

    show_dag    = True
    show_cols   = args.columns or args.all
    show_impact = args.impact or ("CUSTOMER_MASTER" if args.all else None)

    main(show_dag=show_dag, show_columns=show_cols, show_impact=show_impact)
