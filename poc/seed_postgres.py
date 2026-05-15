#!/usr/bin/env python3
"""
POC PostgreSQL Seed Script
Creates the same three-schema dummy dataset as seed_data.py but
inside the local PostgreSQL container that docker-compose.poc.yml starts.

Run AFTER the stack is up:
  docker compose -f docker-compose.yml -f docker-compose.poc.yml up -d
  python poc/seed_postgres.py

Connection defaults match docker-compose.poc.yml:
  host     localhost
  port     5433          (mapped from container port 5432)
  database catalog_poc
  user     poc_user
  password poc_password

Override with env vars:
  PG_HOST / PG_PORT / PG_DB / PG_USER / PG_PASSWORD
"""

import os
import random
import sys
from datetime import date, datetime, timedelta

random.seed(42)

# ── connection settings ───────────────────────────────────────
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_DB   = os.getenv("PG_DB",   "catalog_poc")
PG_USER = os.getenv("PG_USER", "poc_user")
PG_PASS = os.getenv("PG_PASSWORD", "poc_password")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2 is not installed.  Run:\n  pip install psycopg2-binary")
    sys.exit(1)


# ── helpers ───────────────────────────────────────────────────
def rand_date(y0=1955, y1=2000):
    s, e = date(y0, 1, 1), date(y1, 12, 31)
    return s + timedelta(days=random.randint(0, (e - s).days))

def rand_dt(days_ago=365):
    return datetime.now() - timedelta(
        days=random.randint(0, days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )

FIRST = ["Alice","Bob","Carol","David","Emma","Frank","Grace","Hank",
         "Iris","Jack","Karen","Leo","Mia","Nick","Olivia","Paul"]
LAST  = ["Smith","Johnson","Williams","Jones","Brown","Davis","Miller",
         "Wilson","Moore","Taylor","Anderson","Thomas","Jackson","White"]
CITIES  = ["San Francisco","New York","Chicago","Austin","Seattle","Boston"]
STATES  = ["CA","NY","IL","TX","WA","MA"]
SEGS    = ["PREMIUM","STANDARD","BASIC","ENTERPRISE"]
STATUS  = ["COMPLETED","PENDING","FAILED","REVERSED"]
CHANNELS= ["WEB","MOBILE","ATM","BRANCH","API"]
CARDS   = ["VISA","MASTERCARD","AMEX","DISCOVER"]
DEPTS   = ["ENG","FIN","HR","MKT","OPS","LEGAL","SALES","DATA"]
JOBS    = ["Senior Engineer","Data Analyst","Product Manager",
           "Software Engineer","Data Steward","Finance Manager"]
CATS    = ["Electronics","Software","Hardware","Services","Accessories"]
ACCTYPES= ["CHECKING","SAVINGS","MONEY_MARKET","BROKERAGE"]


def connect():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        dbname=PG_DB, user=PG_USER, password=PG_PASS,
        connect_timeout=10,
    )


def create_schemas(cur):
    for schema in ("finance_db", "hr_db", "product_db"):
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")


def create_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_db.customer_master (
            customer_id      SERIAL PRIMARY KEY,
            first_name       TEXT    NOT NULL,
            last_name        TEXT    NOT NULL,
            email_address    TEXT,
            phone_number     TEXT,
            ssn              TEXT,
            date_of_birth    DATE,
            address_line1    TEXT,
            city             TEXT,
            state_code       CHAR(2),
            zip_code         TEXT,
            account_balance  NUMERIC(18,2),
            customer_segment TEXT,
            created_date     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_updated     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            is_active        BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_db.payment_transactions (
            transaction_id     TEXT PRIMARY KEY,
            customer_id        INTEGER NOT NULL,
            transaction_date   TIMESTAMPTZ NOT NULL,
            transaction_amount NUMERIC(18,2) NOT NULL,
            currency_code      CHAR(3) NOT NULL DEFAULT 'USD',
            merchant_name      TEXT,
            card_number        TEXT,
            card_type          TEXT,
            status             TEXT NOT NULL,
            fraud_score        NUMERIC(5,4),
            ip_address         INET,
            channel            TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_db.account_summary (
            account_id      TEXT PRIMARY KEY,
            customer_id     INTEGER NOT NULL,
            summary_month   DATE NOT NULL,
            opening_balance NUMERIC(18,2) NOT NULL,
            closing_balance NUMERIC(18,2) NOT NULL,
            total_credits   NUMERIC(18,2) NOT NULL DEFAULT 0,
            total_debits    NUMERIC(18,2) NOT NULL DEFAULT 0,
            interest_earned NUMERIC(10,4),
            account_type    TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hr_db.employee_records (
            employee_id         SERIAL PRIMARY KEY,
            first_name          TEXT NOT NULL,
            last_name           TEXT NOT NULL,
            social_security_num TEXT,
            date_of_birth       DATE,
            hire_date           DATE NOT NULL,
            department_code     TEXT NOT NULL,
            job_title           TEXT,
            annual_salary       NUMERIC(12,2) NOT NULL,
            manager_id          INTEGER,
            work_email          TEXT NOT NULL,
            employment_status   TEXT NOT NULL DEFAULT 'ACTIVE',
            password_hash       TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_db.product_catalog (
            product_id     SERIAL PRIMARY KEY,
            product_name   TEXT NOT NULL,
            product_code   TEXT NOT NULL UNIQUE,
            category_name  TEXT NOT NULL,
            unit_price     NUMERIC(10,2) NOT NULL,
            cost_price     NUMERIC(10,2) NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_date   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            supplier_id    INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS product_db.product_reviews (
            review_id     SERIAL PRIMARY KEY,
            product_id    INTEGER NOT NULL,
            customer_id   INTEGER NOT NULL,
            rating        SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            review_text   TEXT,
            review_date   TIMESTAMPTZ NOT NULL,
            is_verified   BOOLEAN NOT NULL DEFAULT FALSE,
            helpful_votes INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Useful indexes for the connector's pg_stats queries
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_customer  ON finance_db.payment_transactions(customer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_date      ON finance_db.payment_transactions(transaction_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_acct_customer ON finance_db.account_summary(customer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_review_product ON product_db.product_reviews(product_id)")


def seed_customers(cur, n=200):
    rows = []
    for i in range(1, n + 1):
        fn, ln = random.choice(FIRST), random.choice(LAST)
        rows.append((
            fn, ln,
            f"{fn.lower()}.{ln.lower()}{i}@email.com",
            f"{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
            f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"
                if random.random() > 0.05 else None,
            rand_date(1955, 2000) if random.random() > 0.01 else None,
            f"{random.randint(100,9999)} {random.choice(['Main','Oak','Elm','Park'])} St",
            random.choice(CITIES), random.choice(STATES),
            str(random.randint(10000, 99999)),
            round(random.uniform(100, 50000), 2),
            random.choice(SEGS),
            rand_dt(1095), rand_dt(30),
            random.random() > 0.05,
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO finance_db.customer_master
        (first_name,last_name,email_address,phone_number,ssn,date_of_birth,
         address_line1,city,state_code,zip_code,account_balance,customer_segment,
         created_date,last_updated,is_active)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} customers")


def seed_transactions(cur, n=1000):
    rows = []
    for i in range(1, n + 1):
        has_card = random.random() > 0.4
        rows.append((
            f"TXN-{i:08d}",
            random.randint(1, 200),
            rand_dt(90),
            round(random.uniform(1.00, 2000.00), 2),
            random.choice(["USD","EUR","GBP","CAD"]),
            random.choice(["AMAZON","WALMART","TARGET","APPLE","NETFLIX"]),
            f"4532-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
                if has_card else None,
            random.choice(CARDS) if has_card else None,
            random.choice(STATUS),
            round(random.uniform(0, 1), 4) if random.random() > 0.3 else None,
            f"192.168.{random.randint(1,254)}.{random.randint(1,254)}"
                if random.random() > 0.1 else None,
            random.choice(CHANNELS),
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO finance_db.payment_transactions
        (transaction_id,customer_id,transaction_date,transaction_amount,
         currency_code,merchant_name,card_number,card_type,status,
         fraud_score,ip_address,channel)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::inet,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} transactions")


def seed_account_summary(cur, n=200):
    rows = []
    for cid in range(1, n + 1):
        opening  = round(random.uniform(500, 20000), 2)
        credits  = round(random.uniform(1000, 5000), 2)
        debits   = round(random.uniform(500, 4000), 2)
        rows.append((
            f"ACC-{cid:06d}", cid, date(2024, 11, 1),
            opening, round(opening + credits - debits, 2),
            credits, debits,
            round(random.uniform(0, 50), 4),
            random.choice(ACCTYPES),
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO finance_db.account_summary
        (account_id,customer_id,summary_month,opening_balance,closing_balance,
         total_credits,total_debits,interest_earned,account_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} account summaries")


def seed_employees(cur, n=50):
    rows = []
    for i in range(1, n + 1):
        fn, ln = random.choice(FIRST), random.choice(LAST)
        rows.append((
            fn, ln,
            f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
            rand_date(1960, 1995),
            rand_date(2010, 2024),
            random.choice(DEPTS),
            random.choice(JOBS),
            round(random.uniform(55000, 180000), 2),
            random.randint(1, 10) if i > 5 else None,
            f"{fn.lower()}.{ln.lower()}@company.com",
            "ACTIVE" if random.random() > 0.1 else "TERMINATED",
            f"$2b$12${'x' * 53}" if random.random() > 0.2 else None,
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO hr_db.employee_records
        (first_name,last_name,social_security_num,date_of_birth,hire_date,
         department_code,job_title,annual_salary,manager_id,work_email,
         employment_status,password_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} employees")


def seed_products(cur, n=80):
    rows = []
    for i in range(1, n + 1):
        cat  = random.choice(CATS)
        cost = round(random.uniform(5, 500), 2)
        rows.append((
            f"{cat[:3].upper()}-{i:04d}",
            f"{cat} Product {i:03d}",
            cat,
            round(cost * random.uniform(1.3, 2.5), 2),
            cost,
            random.randint(0, 1000),
            random.random() > 0.08,
            rand_dt(730),
            random.randint(1, 10),
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO product_db.product_catalog
        (product_code,product_name,category_name,unit_price,cost_price,
         stock_quantity,is_active,created_date,supplier_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} products")


def seed_reviews(cur, n=500):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            random.randint(1, 80),
            random.randint(1, 200),
            random.randint(1, 5),
            random.choice(["Great product!", "Works as expected.",
                           "Highly recommend!", None, "Could be better."]),
            rand_dt(180),
            random.random() > 0.3,
            random.randint(0, 50),
        ))
    psycopg2.extras.execute_batch(cur, """
        INSERT INTO product_db.product_reviews
        (product_id,customer_id,rating,review_text,review_date,is_verified,helpful_votes)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, rows)
    print(f"  ✔ {n} reviews")


def print_summary(cur):
    tables = [
        ("finance_db.customer_master",      "FINANCE_DB"),
        ("finance_db.payment_transactions",  "FINANCE_DB"),
        ("finance_db.account_summary",       "FINANCE_DB"),
        ("hr_db.employee_records",           "HR_DB"),
        ("product_db.product_catalog",       "PRODUCT_DB"),
        ("product_db.product_reviews",       "PRODUCT_DB"),
    ]
    print("\n  Row counts:")
    for tbl, schema in tables:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        cnt = cur.fetchone()[0]
        print(f"    {tbl:<45}  {cnt:>6} rows")


def main():
    print(f"\n  Connecting to PostgreSQL at {PG_HOST}:{PG_PORT}/{PG_DB}…")
    try:
        conn = connect()
    except Exception as e:
        print(f"\n  ERROR: cannot connect to PostgreSQL — {e}")
        print("  Make sure the stack is up:\n"
              "    docker compose -f docker-compose.yml -f docker-compose.poc.yml up -d")
        sys.exit(1)

    print("  Connected.\n")
    cur = conn.cursor()

    print("  Creating schemas…")
    create_schemas(cur)
    print("  Creating tables…")
    create_tables(cur)
    print("  Seeding data…")
    seed_customers(cur)
    seed_transactions(cur)
    seed_account_summary(cur)
    seed_employees(cur)
    seed_products(cur)
    seed_reviews(cur)

    conn.commit()
    print_summary(cur)
    cur.close()
    conn.close()

    print(f"""
  PostgreSQL source ready.  Register it in the catalog with:

    POST /connector/sources
    {{
      "name":        "POC-PostgreSQL-Source",
      "source_type": "postgresql",
      "host":        "poc-postgres",
      "port":        5432,
      "database":    "{PG_DB}",
      "username":    "{PG_USER}",
      "password":    "{PG_PASS}",
      "schema_filter": ["finance_db", "hr_db", "product_db"]
    }}

  (Use host "poc-postgres" from inside Docker, or "localhost:{PG_PORT}" externally.)
""")


if __name__ == "__main__":
    main()
