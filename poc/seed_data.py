#!/usr/bin/env python3
"""
POC Seed Script — creates poc/data/source.db
Simulates a Teradata warehouse with three databases (schemas) worth of
realistic tables.  Run this ONCE before starting the stack.

  python poc/seed_data.py
"""

import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "source.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ── helpers ────────────────────────────────────────────────────
def rand_date(start_year=1955, end_year=2000) -> str:
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return str(start + timedelta(days=random.randint(0, (end - start).days)))

def rand_dt(days_ago=365) -> str:
    t = datetime.now() - timedelta(days=random.randint(0, days_ago),
                                   hours=random.randint(0, 23),
                                   minutes=random.randint(0, 59))
    return t.strftime("%Y-%m-%d %H:%M:%S")

FIRST_NAMES = ["Alice","Bob","Carol","David","Emma","Frank","Grace","Hank",
               "Iris","Jack","Karen","Leo","Mia","Nick","Olivia","Paul"]
LAST_NAMES  = ["Smith","Johnson","Williams","Jones","Brown","Davis","Miller",
               "Wilson","Moore","Taylor","Anderson","Thomas","Jackson","White"]
CITIES      = ["San Francisco","New York","Chicago","Austin","Seattle","Boston",
               "Denver","Atlanta","Miami","Los Angeles"]
STATES      = ["CA","NY","IL","TX","WA","MA","CO","GA","FL","CA"]
SEGMENTS    = ["PREMIUM","STANDARD","BASIC","ENTERPRISE"]
STATUSES    = ["COMPLETED","PENDING","FAILED","REVERSED"]
CHANNELS    = ["WEB","MOBILE","ATM","BRANCH","API"]
CARD_TYPES  = ["VISA","MASTERCARD","AMEX","DISCOVER"]
DEPARTMENTS = ["ENG","FIN","HR","MKT","OPS","LEGAL","SALES","DATA"]
JOB_TITLES  = ["Senior Engineer","Data Analyst","Product Manager",
               "Software Engineer","Data Steward","Finance Manager",
               "HR Specialist","Legal Counsel","Operations Lead"]
CATEGORIES  = ["Electronics","Software","Hardware","Services",
               "Accessories","Subscriptions","Consulting"]
ACCOUNT_TYPES = ["CHECKING","SAVINGS","MONEY_MARKET","BROKERAGE"]


TABLES = [
    ("finance_customer_master", """
        CREATE TABLE IF NOT EXISTS finance_customer_master (
            customer_id      INTEGER PRIMARY KEY,
            first_name       TEXT    NOT NULL,
            last_name        TEXT    NOT NULL,
            email_address    TEXT,
            phone_number     TEXT,
            ssn              TEXT,
            date_of_birth    TEXT,
            address_line1    TEXT,
            city             TEXT,
            state_code       TEXT,
            zip_code         TEXT,
            account_balance  REAL,
            customer_segment TEXT,
            created_date     TEXT    NOT NULL,
            last_updated     TEXT    NOT NULL,
            is_active        INTEGER NOT NULL DEFAULT 1
        )"""),
    ("finance_payment_transactions", """
        CREATE TABLE IF NOT EXISTS finance_payment_transactions (
            transaction_id     TEXT    PRIMARY KEY,
            customer_id        INTEGER NOT NULL,
            transaction_date   TEXT    NOT NULL,
            transaction_amount REAL    NOT NULL,
            currency_code      TEXT    NOT NULL DEFAULT 'USD',
            merchant_name      TEXT,
            card_number        TEXT,
            card_type          TEXT,
            status             TEXT    NOT NULL,
            fraud_score        REAL,
            ip_address         TEXT,
            channel            TEXT    NOT NULL
        )"""),
    ("finance_account_summary", """
        CREATE TABLE IF NOT EXISTS finance_account_summary (
            account_id      TEXT    PRIMARY KEY,
            customer_id     INTEGER NOT NULL,
            summary_month   TEXT    NOT NULL,
            opening_balance REAL    NOT NULL,
            closing_balance REAL    NOT NULL,
            total_credits   REAL    NOT NULL DEFAULT 0,
            total_debits    REAL    NOT NULL DEFAULT 0,
            interest_earned REAL,
            account_type    TEXT    NOT NULL
        )"""),
    ("hr_employee_records", """
        CREATE TABLE IF NOT EXISTS hr_employee_records (
            employee_id          INTEGER PRIMARY KEY,
            first_name           TEXT    NOT NULL,
            last_name            TEXT    NOT NULL,
            social_security_num  TEXT,
            date_of_birth        TEXT,
            hire_date            TEXT    NOT NULL,
            department_code      TEXT    NOT NULL,
            job_title            TEXT,
            annual_salary        REAL    NOT NULL,
            manager_id           INTEGER,
            work_email           TEXT    NOT NULL,
            employment_status    TEXT    NOT NULL DEFAULT 'ACTIVE',
            password_hash        TEXT
        )"""),
    ("product_catalog", """
        CREATE TABLE IF NOT EXISTS product_catalog (
            product_id     INTEGER PRIMARY KEY,
            product_name   TEXT    NOT NULL,
            product_code   TEXT    NOT NULL UNIQUE,
            category_name  TEXT    NOT NULL,
            unit_price     REAL    NOT NULL,
            cost_price     REAL    NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            is_active      INTEGER NOT NULL DEFAULT 1,
            created_date   TEXT    NOT NULL,
            supplier_id    INTEGER
        )"""),
    ("product_reviews", """
        CREATE TABLE IF NOT EXISTS product_reviews (
            review_id     INTEGER PRIMARY KEY,
            product_id    INTEGER NOT NULL,
            customer_id   INTEGER NOT NULL,
            rating        INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            review_text   TEXT,
            review_date   TEXT    NOT NULL,
            is_verified   INTEGER NOT NULL DEFAULT 0,
            helpful_votes INTEGER NOT NULL DEFAULT 0
        )"""),
]


def create_tables(conn: sqlite3.Connection):
    # Use individual execute() calls — avoids executescript()'s implicit COMMIT
    # which can fail on certain FUSE / networked filesystems.
    for _name, ddl in TABLES:
        conn.execute(ddl)
    conn.commit()


def seed_customers(conn: sqlite3.Connection, n: int = 200):
    rows = []
    for i in range(1, n + 1):
        fn   = random.choice(FIRST_NAMES)
        ln   = random.choice(LAST_NAMES)
        city = random.choice(CITIES)
        st   = random.choice(STATES)
        rows.append((
            i,
            fn, ln,
            f"{fn.lower()}.{ln.lower()}{i}@email.com",
            f"{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
            f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}" if random.random() > 0.05 else None,
            rand_date(1955, 2000) if random.random() > 0.01 else None,
            f"{random.randint(100,9999)} {random.choice(['Main','Oak','Elm','Park','Lake'])} St",
            city, st,
            str(random.randint(10000, 99999)),
            round(random.uniform(100, 50000), 2),
            random.choice(SEGMENTS),
            rand_dt(1095), rand_dt(30), 1 if random.random() > 0.05 else 0,
        ))
    conn.executemany(
        "INSERT OR IGNORE INTO finance_customer_master VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {n} customers")


def seed_transactions(conn: sqlite3.Connection, n: int = 1000):
    rows = []
    for i in range(1, n + 1):
        cust_id = random.randint(1, 200)
        amount  = round(random.uniform(1.00, 2000.00), 2)
        has_card = random.random() > 0.4
        rows.append((
            f"TXN-{i:08d}",
            cust_id,
            rand_dt(90),
            amount,
            random.choice(["USD", "EUR", "GBP", "CAD"]),
            random.choice(["AMAZON","WALMART","TARGET","APPLE","NETFLIX","UBER"]),
            f"4532-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}" if has_card else None,
            random.choice(CARD_TYPES) if has_card else None,
            random.choice(STATUSES),
            round(random.uniform(0, 1), 4) if random.random() > 0.3 else None,
            f"192.168.{random.randint(1,254)}.{random.randint(1,254)}" if random.random() > 0.1 else None,
            random.choice(CHANNELS),
        ))
    conn.executemany(
        "INSERT OR IGNORE INTO finance_payment_transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {n} transactions")


def seed_account_summary(conn: sqlite3.Connection):
    rows = []
    acc_id = 1
    for cust_id in range(1, 201):
        opening = round(random.uniform(500, 20000), 2)
        credits = round(random.uniform(1000, 5000), 2)
        debits  = round(random.uniform(500, 4000), 2)
        closing = round(opening + credits - debits, 2)
        rows.append((
            f"ACC-{acc_id:06d}",
            cust_id,
            "2024-11-01",
            opening, closing, credits, debits,
            round(random.uniform(0, 50), 4),
            random.choice(ACCOUNT_TYPES),
        ))
        acc_id += 1
    conn.executemany(
        "INSERT OR IGNORE INTO finance_account_summary VALUES (?,?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {len(rows)} account summaries")


def seed_employees(conn: sqlite3.Connection, n: int = 50):
    rows = []
    for i in range(1, n + 1):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        rows.append((
            i,
            fn, ln,
            f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}",
            rand_date(1960, 1995),
            rand_date(2010, 2024),
            random.choice(DEPARTMENTS),
            random.choice(JOB_TITLES),
            round(random.uniform(55000, 180000), 2),
            random.randint(1, 10) if i > 5 else None,
            f"{fn.lower()}.{ln.lower()}@company.com",
            "ACTIVE" if random.random() > 0.1 else "TERMINATED",
            f"$2b$12${'x' * 53}" if random.random() > 0.2 else None,
        ))
    conn.executemany(
        "INSERT OR IGNORE INTO hr_employee_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {n} employees")


def seed_products(conn: sqlite3.Connection, n: int = 80):
    rows = []
    for i in range(1, n + 1):
        cat  = random.choice(CATEGORIES)
        cost = round(random.uniform(5, 500), 2)
        rows.append((
            i,
            f"{cat} Product {i:03d}",
            f"SKU-{cat[:3].upper()}-{i:04d}",
            cat,
            round(cost * random.uniform(1.3, 2.5), 2),
            cost,
            random.randint(0, 1000),
            1 if random.random() > 0.08 else 0,
            rand_dt(730),
            random.randint(1, 10),
        ))
    conn.executemany(
        "INSERT OR IGNORE INTO product_catalog VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {n} products")


def seed_reviews(conn: sqlite3.Connection, n: int = 500):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            i,
            random.randint(1, 80),
            random.randint(1, 200),
            random.randint(1, 5),
            random.choice(["Great product!", "Works as expected.", "Not bad.",
                           "Highly recommend!", None, "Could be better."]),
            rand_dt(180),
            1 if random.random() > 0.3 else 0,
            random.randint(0, 50),
        ))
    conn.executemany(
        "INSERT OR IGNORE INTO product_reviews VALUES (?,?,?,?,?,?,?,?)",
        rows
    )
    conn.commit()
    print(f"  ✔ Seeded {n} reviews")


def main():
    print(f"\nSeeding POC source database → {DB_PATH}\n")
    conn = sqlite3.connect(DB_PATH)

    print("Creating tables…")
    create_tables(conn)

    print("Inserting data…")
    seed_customers(conn)
    seed_transactions(conn)
    seed_account_summary(conn)
    seed_employees(conn)
    seed_products(conn)
    seed_reviews(conn)

    # Summary
    for tbl in ["finance_customer_master","finance_payment_transactions",
                "finance_account_summary","hr_employee_records",
                "product_catalog","product_reviews"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<38}  {cnt} rows")

    conn.close()
    print(f"\nSource database ready at {path}\n".replace("{path}", str(__import__("pathlib").Path(path).parent / "data" / "source.db")))


if __name__ == "__main__":
    main()
