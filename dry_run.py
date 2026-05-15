#!/usr/bin/env python3
"""
============================================================
Data Catalog Platform — Teradata Dry Run Simulator
============================================================
Simulates the full hydration pipeline end-to-end using
realistic mock Teradata data.  No Docker, no Kafka, no real
database needed — just Python 3.11+.

Pipeline stages executed:
  1. Mock Teradata schema discovery (connector-service logic)
  2. Metadata enrichment & quality scoring (metadata-service)
  3. PII classification (classification-service)
  4. Business term assignment (term-service)
  5. Catalog asset assembly (catalog-service)
  6. Simulated BigQuery write + audit log
  7. Simulated DataHub lineage emit

Run:
  python dry_run.py
  python dry_run.py --verbose      # show all column details
  python dry_run.py --json         # dump final catalog as JSON
============================================================
"""

import argparse
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ── ANSI colour helpers ────────────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

GREEN   = lambda t: _c("32", t)
YELLOW  = lambda t: _c("33", t)
RED     = lambda t: _c("31", t)
CYAN    = lambda t: _c("36", t)
BOLD    = lambda t: _c("1",  t)
DIM     = lambda t: _c("2",  t)
MAGENTA = lambda t: _c("35", t)


# ══════════════════════════════════════════════════════════════
# STAGE 1 — Mock Teradata connector
# Mirrors connector-service/connectors/teradata.py logic
# ══════════════════════════════════════════════════════════════

class DataSourceType(str, Enum):
    TERADATA = "teradata"

class PIICategory(str, Enum):
    NONE = "none"
    PERSONAL = "personal"
    FINANCIAL = "financial"
    HEALTH = "health"
    CREDENTIALS = "credentials"

class SensitivityLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


@dataclass
class MockColumn:
    name: str
    data_type: str          # Teradata native type
    nullable: bool
    max_length: Optional[int]
    # sample values for classification
    sample_values: list[str] = field(default_factory=list)
    # stats (normally from TABLESAMPLE query)
    null_count: int = 0
    distinct_count: int = 0
    total_count: int = 100


@dataclass
class MockTable:
    schema_name: str
    table_name: str
    row_count: int
    size_bytes: int
    columns: list[MockColumn]
    comment: str = ""


# ── Realistic mock Teradata dataset ───────────────────────────
MOCK_TERADATA_SCHEMAS = {
    "FINANCE_DB": [
        MockTable(
            schema_name="FINANCE_DB",
            table_name="CUSTOMER_MASTER",
            row_count=4_823_901,
            size_bytes=1_843_200_000,
            comment="Core customer master record — source of truth for CRM",
            columns=[
                MockColumn("CUSTOMER_ID",       "INTEGER",        False, None,  ["10001", "10002", "10003"], null_count=0,  distinct_count=4823901, total_count=4823901),
                MockColumn("FIRST_NAME",         "VARCHAR(50)",    False, 50,   ["John", "Jane", "Robert"],  null_count=0,  distinct_count=312000,  total_count=4823901),
                MockColumn("LAST_NAME",          "VARCHAR(50)",    False, 50,   ["Smith", "Doe", "Johnson"], null_count=0,  distinct_count=480000,  total_count=4823901),
                MockColumn("EMAIL_ADDRESS",      "VARCHAR(120)",   True,  120,  ["john.smith@email.com"],     null_count=92400, distinct_count=4710000, total_count=4823901),
                MockColumn("PHONE_NUMBER",       "VARCHAR(20)",    True,  20,   ["415-555-0192", "800-555-0199"], null_count=320000, distinct_count=4400000, total_count=4823901),
                MockColumn("SSN",                "CHAR(11)",       True,  11,   ["123-45-6789", "987-65-4321"], null_count=200000, distinct_count=4600000, total_count=4823901),
                MockColumn("DATE_OF_BIRTH",      "DATE",           True,  None, ["1985-03-14", "1990-07-22"], null_count=50000, distinct_count=25000, total_count=4823901),
                MockColumn("ADDRESS_LINE1",      "VARCHAR(200)",   True,  200,  ["123 Main St", "456 Oak Ave"], null_count=100000, distinct_count=4700000, total_count=4823901),
                MockColumn("CITY",               "VARCHAR(80)",    True,  80,   ["San Francisco", "New York"], null_count=100000, distinct_count=8000, total_count=4823901),
                MockColumn("STATE_CODE",         "CHAR(2)",        True,  2,    ["CA", "NY", "TX"],           null_count=100000, distinct_count=52,    total_count=4823901),
                MockColumn("ZIP_CODE",           "VARCHAR(10)",    True,  10,   ["94105", "10001"],           null_count=110000, distinct_count=42000, total_count=4823901),
                MockColumn("ACCOUNT_BALANCE",    "DECIMAL(18,2)",  True,  None, ["1250.00", "87432.50"],      null_count=5000, distinct_count=3800000, total_count=4823901),
                MockColumn("CUSTOMER_SEGMENT",   "VARCHAR(30)",    True,  30,   ["PREMIUM", "STANDARD"],      null_count=10000, distinct_count=5,  total_count=4823901),
                MockColumn("CREATED_DATE",       "TIMESTAMP",      False, None, ["2021-01-15 09:23:11"],      null_count=0,  distinct_count=4823901, total_count=4823901),
                MockColumn("LAST_UPDATED",       "TIMESTAMP",      False, None, ["2024-11-02 14:55:00"],      null_count=0,  distinct_count=4823000, total_count=4823901),
                MockColumn("IS_ACTIVE",          "BYTEINT",        False, None, ["1", "0"],                   null_count=0,  distinct_count=2,       total_count=4823901),
            ]
        ),
        MockTable(
            schema_name="FINANCE_DB",
            table_name="PAYMENT_TRANSACTIONS",
            row_count=98_441_320,
            size_bytes=42_000_000_000,
            comment="All payment and transfer transactions",
            columns=[
                MockColumn("TRANSACTION_ID",     "BIGINT",         False, None, ["TXN-00000001"],             null_count=0,  distinct_count=98441320, total_count=98441320),
                MockColumn("CUSTOMER_ID",        "INTEGER",        False, None, ["10001", "10002"],           null_count=0,  distinct_count=4800000,  total_count=98441320),
                MockColumn("TRANSACTION_DATE",   "TIMESTAMP",      False, None, ["2024-11-01 10:23:00"],      null_count=0,  distinct_count=98000000, total_count=98441320),
                MockColumn("TRANSACTION_AMOUNT", "DECIMAL(18,2)",  False, None, ["99.99", "1500.00"],         null_count=0,  distinct_count=5000000,  total_count=98441320),
                MockColumn("CURRENCY_CODE",      "CHAR(3)",        False, 3,    ["USD", "EUR", "GBP"],        null_count=0,  distinct_count=32,       total_count=98441320),
                MockColumn("MERCHANT_NAME",      "VARCHAR(200)",   True,  200,  ["AMAZON", "WALMART"],        null_count=200000, distinct_count=800000, total_count=98441320),
                MockColumn("CARD_NUMBER",        "VARCHAR(19)",    True,  19,   ["4532-1234-5678-9010"],      null_count=50000000, distinct_count=10000000, total_count=98441320),
                MockColumn("CARD_TYPE",          "VARCHAR(20)",    True,  20,   ["VISA", "MASTERCARD"],       null_count=50000000, distinct_count=5,   total_count=98441320),
                MockColumn("STATUS",             "VARCHAR(20)",    False, 20,   ["COMPLETED", "PENDING"],     null_count=0,  distinct_count=4,        total_count=98441320),
                MockColumn("FRAUD_SCORE",        "DECIMAL(5,4)",   True,  None, ["0.0012", "0.9987"],         null_count=5000000, distinct_count=9000, total_count=98441320),
                MockColumn("IP_ADDRESS",         "VARCHAR(45)",    True,  45,   ["192.168.1.100", "10.0.0.5"], null_count=2000000, distinct_count=5000000, total_count=98441320),
                MockColumn("CHANNEL",            "VARCHAR(20)",    False, 20,   ["WEB", "MOBILE", "ATM"],     null_count=0,  distinct_count=6,        total_count=98441320),
            ]
        ),
        MockTable(
            schema_name="FINANCE_DB",
            table_name="ACCOUNT_SUMMARY",
            row_count=6_100_204,
            size_bytes=980_000_000,
            comment="Monthly account balance summary (denormalized for reporting)",
            columns=[
                MockColumn("ACCOUNT_ID",         "BIGINT",         False, None, ["ACC-10001"],                null_count=0,  distinct_count=6100204, total_count=6100204),
                MockColumn("CUSTOMER_ID",        "INTEGER",        False, None, ["10001"],                   null_count=0,  distinct_count=4800000, total_count=6100204),
                MockColumn("SUMMARY_MONTH",      "DATE",           False, None, ["2024-11-01"],              null_count=0,  distinct_count=84,      total_count=6100204),
                MockColumn("OPENING_BALANCE",    "DECIMAL(18,2)",  False, None, ["5000.00"],                 null_count=0,  distinct_count=3000000, total_count=6100204),
                MockColumn("CLOSING_BALANCE",    "DECIMAL(18,2)",  False, None, ["5234.50"],                 null_count=0,  distinct_count=3200000, total_count=6100204),
                MockColumn("TOTAL_CREDITS",      "DECIMAL(18,2)",  False, None, ["3400.00"],                 null_count=0,  distinct_count=2000000, total_count=6100204),
                MockColumn("TOTAL_DEBITS",       "DECIMAL(18,2)",  False, None, ["3165.50"],                 null_count=0,  distinct_count=2000000, total_count=6100204),
                MockColumn("INTEREST_EARNED",    "DECIMAL(10,4)",  True,  None, ["12.3400"],                 null_count=1000000, distinct_count=500000, total_count=6100204),
                MockColumn("ACCOUNT_TYPE",       "VARCHAR(30)",    False, 30,   ["CHECKING", "SAVINGS"],     null_count=0,  distinct_count=4,       total_count=6100204),
            ]
        ),
    ],
    "HR_DB": [
        MockTable(
            schema_name="HR_DB",
            table_name="EMPLOYEE_RECORDS",
            row_count=48_230,
            size_bytes=28_000_000,
            comment="All active and terminated employee HR records",
            columns=[
                MockColumn("EMPLOYEE_ID",        "INTEGER",        False, None, ["EMP-00101"],               null_count=0,  distinct_count=48230, total_count=48230),
                MockColumn("FIRST_NAME",         "VARCHAR(50)",    False, 50,   ["Alice", "Bob"],            null_count=0,  distinct_count=4000,  total_count=48230),
                MockColumn("LAST_NAME",          "VARCHAR(50)",    False, 50,   ["Wong", "Martinez"],        null_count=0,  distinct_count=12000, total_count=48230),
                MockColumn("SOCIAL_SECURITY_NUM","CHAR(11)",       False, 11,   ["123-45-6789"],             null_count=0,  distinct_count=48230, total_count=48230),
                MockColumn("DATE_OF_BIRTH",      "DATE",           False, None, ["1982-06-15"],              null_count=0,  distinct_count=18000, total_count=48230),
                MockColumn("HIRE_DATE",          "DATE",           False, None, ["2019-03-01"],              null_count=0,  distinct_count=5000,  total_count=48230),
                MockColumn("DEPARTMENT_CODE",    "VARCHAR(10)",    False, 10,   ["FIN", "ENG", "HR"],        null_count=0,  distinct_count=45,    total_count=48230),
                MockColumn("JOB_TITLE",          "VARCHAR(100)",   False, 100,  ["Senior Engineer"],         null_count=0,  distinct_count=300,   total_count=48230),
                MockColumn("ANNUAL_SALARY",      "DECIMAL(12,2)",  False, None, ["95000.00", "145000.00"],   null_count=0,  distinct_count=8000,  total_count=48230),
                MockColumn("MANAGER_ID",         "INTEGER",        True,  None, ["EMP-00010"],               null_count=500, distinct_count=2000, total_count=48230),
                MockColumn("WORK_EMAIL",         "VARCHAR(120)",   False, 120,  ["alice.wong@company.com"],  null_count=0,  distinct_count=48230, total_count=48230),
                MockColumn("EMPLOYMENT_STATUS",  "VARCHAR(20)",    False, 20,   ["ACTIVE", "TERMINATED"],   null_count=0,  distinct_count=3,     total_count=48230),
                MockColumn("PASSWORD_HASH",      "VARCHAR(128)",   True,  128,  ["$2b$12$abc..."],           null_count=10000, distinct_count=38000, total_count=48230),
            ]
        ),
    ],
    "PRODUCT_DB": [
        MockTable(
            schema_name="PRODUCT_DB",
            table_name="PRODUCT_CATALOG",
            row_count=142_800,
            size_bytes=95_000_000,
            comment="Master product list with pricing and classification",
            columns=[
                MockColumn("PRODUCT_ID",         "INTEGER",        False, None, ["PRD-1001"],                null_count=0,   distinct_count=142800, total_count=142800),
                MockColumn("PRODUCT_NAME",       "VARCHAR(200)",   False, 200,  ["Widget Pro", "DataKit"],   null_count=0,   distinct_count=142800, total_count=142800),
                MockColumn("PRODUCT_CODE",       "VARCHAR(20)",    False, 20,   ["WGT-PRO-001"],             null_count=0,   distinct_count=142800, total_count=142800),
                MockColumn("CATEGORY_NAME",      "VARCHAR(80)",    False, 80,   ["Electronics", "Software"], null_count=0,   distinct_count=120,    total_count=142800),
                MockColumn("UNIT_PRICE",         "DECIMAL(10,2)",  False, None, ["29.99", "199.00"],         null_count=0,   distinct_count=9000,   total_count=142800),
                MockColumn("COST_PRICE",         "DECIMAL(10,2)",  False, None, ["14.50", "102.00"],         null_count=0,   distinct_count=8000,   total_count=142800),
                MockColumn("STOCK_QUANTITY",     "INTEGER",        False, None, ["500", "12"],               null_count=0,   distinct_count=2000,   total_count=142800),
                MockColumn("IS_ACTIVE",          "BYTEINT",        False, None, ["1", "0"],                  null_count=0,   distinct_count=2,      total_count=142800),
                MockColumn("CREATED_DATE",       "TIMESTAMP",      False, None, ["2022-01-10 08:00:00"],     null_count=0,   distinct_count=142800, total_count=142800),
                MockColumn("SUPPLIER_ID",        "INTEGER",        True,  None, ["SUP-001"],                 null_count=2000, distinct_count=800,   total_count=142800),
            ]
        ),
        MockTable(
            schema_name="PRODUCT_DB",
            table_name="PRODUCT_REVIEWS",
            row_count=2_341_000,
            size_bytes=410_000_000,
            comment="Customer product reviews and ratings",
            columns=[
                MockColumn("REVIEW_ID",          "BIGINT",         False, None, ["REV-000001"],              null_count=0,   distinct_count=2341000, total_count=2341000),
                MockColumn("PRODUCT_ID",         "INTEGER",        False, None, ["PRD-1001"],                null_count=0,   distinct_count=142800,  total_count=2341000),
                MockColumn("CUSTOMER_ID",        "INTEGER",        False, None, ["10001"],                   null_count=0,   distinct_count=1200000, total_count=2341000),
                MockColumn("RATING",             "BYTEINT",        False, None, ["4", "5", "3"],             null_count=0,   distinct_count=5,       total_count=2341000),
                MockColumn("REVIEW_TEXT",        "VARCHAR(4000)",  True,  4000, ["Great product!"],          null_count=800000, distinct_count=1400000, total_count=2341000),
                MockColumn("REVIEW_DATE",        "TIMESTAMP",      False, None, ["2024-10-15 14:22:00"],     null_count=0,   distinct_count=2341000, total_count=2341000),
                MockColumn("IS_VERIFIED",        "BYTEINT",        False, None, ["1", "0"],                  null_count=0,   distinct_count=2,       total_count=2341000),
                MockColumn("HELPFUL_VOTES",      "INTEGER",        False, None, ["0", "12", "3"],            null_count=0,   distinct_count=800,     total_count=2341000),
            ]
        ),
    ],
}


# ══════════════════════════════════════════════════════════════
# STAGE 2 — Metadata enrichment  (metadata-service logic)
# ══════════════════════════════════════════════════════════════

DOMAIN_VOCABULARIES: dict[str, list[str]] = {
    "finance":    ["payment", "transaction", "account", "balance", "credit", "debit", "currency", "amount", "invoice", "revenue", "financial", "interest", "salary"],
    "hr":         ["employee", "hire", "department", "salary", "payroll", "manager", "staff", "workforce", "job", "position", "termination", "employment"],
    "customer":   ["customer", "client", "user", "member", "subscriber", "consumer", "address", "email", "phone", "contact"],
    "product":    ["product", "catalog", "sku", "item", "inventory", "stock", "price", "supplier", "category", "review", "rating"],
    "compliance": ["audit", "fraud", "risk", "compliance", "control", "regulation", "policy", "breach", "incident", "violation"],
    "operations": ["system", "status", "flag", "active", "created", "updated", "deleted", "modified", "timestamp", "log"],
}


def infer_domain(schema_name: str, table_name: str) -> str:
    combined = (schema_name + " " + table_name).lower()
    best_domain = "general"
    best_score  = 0
    for domain, keywords in DOMAIN_VOCABULARIES.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score  = score
            best_domain = domain
    return best_domain


def compute_quality_score(table: MockTable) -> dict:
    scores = {}
    for col in table.columns:
        null_rate = col.null_count / max(col.total_count, 1)
        completeness = 1.0 - null_rate

        distinct_rate = col.distinct_count / max(col.total_count, 1)
        uniqueness = min(distinct_rate, 1.0)

        # Validity: penalise if >50% nulls or suspiciously low distinct (enum-like ok, flat bad)
        if null_rate > 0.5:
            validity = 0.5
        elif distinct_rate < 0.001 and col.total_count > 10000:
            validity = 0.7   # almost all same value
        else:
            validity = 0.95

        consistency = 0.9  # assumed from connector — no contradictions found

        overall = (
            completeness * 0.35
            + uniqueness  * 0.25
            + validity    * 0.25
            + consistency * 0.15
        )
        scores[col.name] = round(overall, 4)

    avg = sum(scores.values()) / len(scores)
    if   avg >= 0.90: grade = "A"
    elif avg >= 0.75: grade = "B"
    elif avg >= 0.60: grade = "C"
    elif avg >= 0.40: grade = "D"
    else:             grade = "F"

    return {"column_scores": scores, "overall": round(avg, 4), "grade": grade}


# ══════════════════════════════════════════════════════════════
# STAGE 3 — PII Classification  (classification-service logic)
# ══════════════════════════════════════════════════════════════

# (name_pattern, value_pattern, PIICategory, SensitivityLevel)
CLASSIFICATION_RULES: list[tuple] = [
    # ---- RESTRICTED -------------------------------------------------------
    (r"ssn|social.?sec|social_security",   r"\d{3}-\d{2}-\d{4}",         PIICategory.PERSONAL,     SensitivityLevel.RESTRICTED),
    (r"passport",                           r"[A-Z]{1,2}\d{6,9}",         PIICategory.PERSONAL,     SensitivityLevel.RESTRICTED),
    (r"credit.?card|card.?number|card_num", r"\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}", PIICategory.FINANCIAL, SensitivityLevel.RESTRICTED),
    (r"password|passwd|pwd|secret",        r".",                          PIICategory.CREDENTIALS,  SensitivityLevel.RESTRICTED),
    (r"biometric|fingerprint|iris_scan",   r".",                          PIICategory.PERSONAL,     SensitivityLevel.RESTRICTED),
    (r"genetic|dna_seq",                   r".",                          PIICategory.HEALTH,       SensitivityLevel.RESTRICTED),
    (r"medical_record|diagnosis|icd_code", r".",                          PIICategory.HEALTH,       SensitivityLevel.RESTRICTED),
    (r"token|auth_token|api_key|secret_key",r"[A-Za-z0-9_\-]{20,}",      PIICategory.CREDENTIALS,  SensitivityLevel.RESTRICTED),

    # ---- CONFIDENTIAL -----------------------------------------------------
    (r"(^|_)dob$|date.of.birth|birth.?date",r"\d{4}-\d{2}-\d{2}",        PIICategory.PERSONAL,     SensitivityLevel.CONFIDENTIAL),
    (r"salary|compensation|pay.?rate|wage", r"[\d\.,]+",                  PIICategory.PERSONAL,     SensitivityLevel.CONFIDENTIAL),
    (r"ip.?addr|ip_address|remote_addr",   r"\d{1,3}\.\d{1,3}\.\d{1,3}", PIICategory.PERSONAL,     SensitivityLevel.CONFIDENTIAL),
    (r"account.?balance|closing_balance|opening_balance", r"[\d\.,]+",    PIICategory.FINANCIAL,    SensitivityLevel.CONFIDENTIAL),
    (r"fraud.?score|risk.?score",          r"[\d\.]+",                   PIICategory.FINANCIAL,    SensitivityLevel.CONFIDENTIAL),

    # ---- INTERNAL ---------------------------------------------------------
    (r"(^|_)(first|last|full|middle).?name$|employee_name|person_name",
                                            r"[A-Za-z\s\-']{2,}",         PIICategory.PERSONAL,     SensitivityLevel.INTERNAL),
    (r"email|e.?mail|mail.?addr",          r"[^@\s]+@[^@\s]+\.[^@\s]+",  PIICategory.PERSONAL,     SensitivityLevel.INTERNAL),
    (r"phone|mobile|cell|tel",             r"[\d\s\-\+\(\)]{7,}",        PIICategory.PERSONAL,     SensitivityLevel.INTERNAL),
    (r"address|addr|street|city|state|zip|postal", r".",                  PIICategory.PERSONAL,     SensitivityLevel.INTERNAL),
]

SENSITIVITY_RANK = {
    SensitivityLevel.PUBLIC:       0,
    SensitivityLevel.INTERNAL:     1,
    SensitivityLevel.CONFIDENTIAL: 2,
    SensitivityLevel.RESTRICTED:   3,
}

SENSITIVITY_COLOURS = {
    SensitivityLevel.PUBLIC:       DIM,
    SensitivityLevel.INTERNAL:     YELLOW,
    SensitivityLevel.CONFIDENTIAL: lambda t: _c("33;1", t),
    SensitivityLevel.RESTRICTED:   RED,
}


def _luhn_check(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"[^0-9]", "", number)]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


@dataclass
class ClassificationResult:
    column_name: str
    pii_category: PIICategory
    sensitivity_level: SensitivityLevel
    matched_rule: str


def classify_column(col: MockColumn) -> ClassificationResult:
    best_level = SensitivityLevel.PUBLIC
    best_cat   = PIICategory.NONE
    best_rule  = "no-match"

    for name_pat, val_pat, category, level in CLASSIFICATION_RULES:
        name_match = bool(re.search(name_pat, col.name, re.IGNORECASE))
        val_match  = any(re.search(val_pat, v, re.IGNORECASE) for v in col.sample_values) if col.sample_values else name_match

        # Credit card: additionally validate Luhn
        if "card" in name_pat and val_match:
            val_match = any(_luhn_check(v) for v in col.sample_values) or name_match

        if name_match and val_match:
            if SENSITIVITY_RANK[level] > SENSITIVITY_RANK[best_level]:
                best_level = level
                best_cat   = category
                best_rule  = name_pat

    return ClassificationResult(
        column_name=col.name,
        pii_category=best_cat,
        sensitivity_level=best_level,
        matched_rule=best_rule,
    )


def classify_table(table: MockTable) -> dict[str, ClassificationResult]:
    results = {}
    for col in table.columns:
        results[col.name] = classify_column(col)
    return results


def table_sensitivity(classification: dict[str, ClassificationResult]) -> SensitivityLevel:
    """Highest sensitivity level across all columns."""
    max_level = SensitivityLevel.PUBLIC
    for r in classification.values():
        if SENSITIVITY_RANK[r.sensitivity_level] > SENSITIVITY_RANK[max_level]:
            max_level = r.sensitivity_level
    return max_level


# ══════════════════════════════════════════════════════════════
# STAGE 4 — Business term assignment  (term-service logic)
# ══════════════════════════════════════════════════════════════

BUSINESS_TERMS: list[dict] = [
    {"id": "BT-001", "name": "Customer ID",           "domain": "customer",   "synonyms": ["client_id", "cust_id", "customer_number"]},
    {"id": "BT-002", "name": "Account Balance",       "domain": "finance",    "synonyms": ["balance", "closing_balance", "net_balance"]},
    {"id": "BT-003", "name": "Transaction Amount",    "domain": "finance",    "synonyms": ["amount", "txn_amount", "payment_amount"]},
    {"id": "BT-004", "name": "Employee ID",           "domain": "hr",         "synonyms": ["emp_id", "staff_id", "worker_id"]},
    {"id": "BT-005", "name": "Annual Salary",         "domain": "hr",         "synonyms": ["salary", "compensation", "yearly_pay", "base_salary"]},
    {"id": "BT-006", "name": "Product SKU",           "domain": "product",    "synonyms": ["sku", "product_code", "item_code", "part_number"]},
    {"id": "BT-007", "name": "Email Address",         "domain": "customer",   "synonyms": ["email", "mail", "email_addr", "contact_email"]},
    {"id": "BT-008", "name": "Fraud Score",           "domain": "compliance", "synonyms": ["risk_score", "fraud_probability", "anomaly_score"]},
    {"id": "BT-009", "name": "Date of Birth",         "domain": "hr",         "synonyms": ["dob", "birth_date", "birthdate", "date_of_birth"]},
    {"id": "BT-010", "name": "Department Code",       "domain": "hr",         "synonyms": ["dept_code", "department", "org_unit"]},
    {"id": "BT-011", "name": "Currency Code",         "domain": "finance",    "synonyms": ["currency", "iso_currency", "fx_code"]},
    {"id": "BT-012", "name": "Product Category",      "domain": "product",    "synonyms": ["category", "product_type", "item_class", "category_name"]},
    {"id": "BT-013", "name": "Unit Price",            "domain": "product",    "synonyms": ["price", "list_price", "retail_price", "unit_cost"]},
    {"id": "BT-014", "name": "Customer Segment",      "domain": "customer",   "synonyms": ["segment", "tier", "customer_tier", "client_category"]},
]


def _tokenize(name: str) -> set[str]:
    """Split CamelCase and snake_case into lowercase tokens."""
    name = re.sub(r"([A-Z])", r"_\1", name)
    tokens = re.split(r"[_\s\-]+", name.lower())
    return {t for t in tokens if len(t) > 1}


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def suggest_terms(col_name: str, threshold: float = 0.2) -> list[dict]:
    col_tokens = _tokenize(col_name)
    suggestions = []
    for term in BUSINESS_TERMS:
        # Exact match on name slug
        term_slug = term["name"].lower().replace(" ", "_")
        if col_name.lower() == term_slug:
            suggestions.append({**term, "score": 1.0, "match_type": "exact"})
            continue
        # Synonym exact match
        if any(syn.lower() == col_name.lower() for syn in term["synonyms"]):
            suggestions.append({**term, "score": 0.99, "match_type": "synonym"})
            continue
        # Jaccard on term name tokens
        term_tokens = _tokenize(term["name"])
        for syn in [term["name"]] + term["synonyms"]:
            syn_tokens = _tokenize(syn)
            score = _jaccard(col_tokens, syn_tokens)
            if score >= threshold:
                suggestions.append({**term, "score": round(score, 4), "match_type": "fuzzy"})
                break

    return sorted(suggestions, key=lambda x: x["score"], reverse=True)[:3]


# ══════════════════════════════════════════════════════════════
# STAGE 5 — Catalog asset assembly
# ══════════════════════════════════════════════════════════════

@dataclass
class CatalogAsset:
    asset_id: str
    source_type: str
    schema_name: str
    table_name: str
    fully_qualified_name: str
    domain: str
    sensitivity_level: str
    row_count: int
    size_bytes: int
    quality_score: float
    quality_grade: str
    pii_column_count: int
    column_count: int
    business_terms: list[str]
    comment: str
    ingested_at: str
    columns: list[dict]


def build_catalog_asset(
    table: MockTable,
    quality: dict,
    classification: dict[str, ClassificationResult],
    term_assignments: dict[str, list[dict]],
) -> CatalogAsset:

    domain = infer_domain(table.schema_name, table.table_name)
    table_sensitivity_lvl = table_sensitivity(classification)

    pii_cols = [
        c for c, r in classification.items()
        if r.sensitivity_level != SensitivityLevel.PUBLIC
    ]

    all_terms: set[str] = set()
    columns_out = []
    for col in table.columns:
        clf = classification[col.name]
        terms = term_assignments.get(col.name, [])
        if terms:
            all_terms.add(terms[0]["name"])
        columns_out.append({
            "name":             col.name,
            "data_type":        col.data_type,
            "nullable":         col.nullable,
            "quality_score":    quality["column_scores"][col.name],
            "pii_category":     clf.pii_category.value,
            "sensitivity":      clf.sensitivity_level.value,
            "top_term":         terms[0]["name"] if terms else None,
            "term_confidence":  terms[0]["score"] if terms else 0.0,
        })

    fqn = f"teradata://PROD-TERA-01/{table.schema_name}/{table.table_name}"

    return CatalogAsset(
        asset_id            = "asset-" + hashlib.md5(fqn.encode()).hexdigest()[:12],
        source_type         = "teradata",
        schema_name         = table.schema_name,
        table_name          = table.table_name,
        fully_qualified_name= fqn,
        domain              = domain,
        sensitivity_level   = table_sensitivity_lvl.value,
        row_count           = table.row_count,
        size_bytes          = table.size_bytes,
        quality_score       = quality["overall"],
        quality_grade       = quality["grade"],
        pii_column_count    = len(pii_cols),
        column_count        = len(table.columns),
        business_terms      = sorted(all_terms),
        comment             = table.comment,
        ingested_at         = datetime.now(timezone.utc).isoformat(),
        columns             = columns_out,
    )


# ══════════════════════════════════════════════════════════════
# STAGE 6 — Simulated BigQuery write
# ══════════════════════════════════════════════════════════════

def simulate_bq_write(asset: CatalogAsset) -> dict:
    return {
        "operation":   "insert_rows_json",
        "table":       "my-data-platform.data_catalog.assets",
        "rows_written": 1,
        "asset_id":    asset.asset_id,
        "partition":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def simulate_audit_event(asset: CatalogAsset) -> dict:
    return {
        "event_id":    str(uuid.uuid4()),
        "event_type":  "asset.hydrated",
        "actor":       "connector-service",
        "resource_id": asset.asset_id,
        "resource_type": "asset",
        "details": {
            "source":          asset.source_type,
            "table":           asset.fully_qualified_name,
            "columns_hydrated": asset.column_count,
            "pii_columns":     asset.pii_column_count,
            "sensitivity":     asset.sensitivity_level,
        },
        "timestamp": asset.ingested_at,
    }


# ══════════════════════════════════════════════════════════════
# STAGE 7 — Simulated DataHub lineage emit
# ══════════════════════════════════════════════════════════════

def simulate_datahub_emit(asset: CatalogAsset) -> dict:
    dataset_urn = f"urn:li:dataset:(urn:li:dataPlatform:teradata,{asset.schema_name}.{asset.table_name},PROD)"
    return {
        "action":         "ingestProposal",
        "endpoint":       "http://datahub-gms:8080/aspects?action=ingestProposal",
        "aspectName":     "schemaMetadata",
        "entityUrn":      dataset_urn,
        "fields_emitted": asset.column_count,
        "lineage_urn":    f"urn:li:dataJob:(urn:li:dataFlow:(teradata,PROD-TERA-01,PROD),hydration-job)",
        "status":         "SIMULATED — would POST to DataHub GMS",
    }


# ══════════════════════════════════════════════════════════════
# OUTPUT — pretty-print pipeline report
# ══════════════════════════════════════════════════════════════

def _hr(char: str = "─", width: int = 72) -> str:
    return char * width


def _size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def _rows(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def print_pipeline_header():
    print()
    print(BOLD(_hr("═")))
    print(BOLD(CYAN("  DATA CATALOG PLATFORM — TERADATA DRY RUN SIMULATION")))
    print(BOLD(_hr("═")))
    print(f"  Source     : {BOLD('PROD-TERA-01')}  (mock — no real connection)")
    print(f"  Schemas    : {BOLD(str(len(MOCK_TERADATA_SCHEMAS)))}  ({', '.join(MOCK_TERADATA_SCHEMAS.keys())})")
    tables = sum(len(v) for v in MOCK_TERADATA_SCHEMAS.values())
    print(f"  Tables     : {BOLD(str(tables))}")
    print(f"  Started at : {BOLD(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
    print(_hr())
    print()


def print_stage(n: int, name: str):
    print(f"\n{BOLD(CYAN(f'  ┌── STAGE {n}'))}: {BOLD(name)}")
    print(f"  {'└' + _hr('─', 60)}")


def print_table_result(asset: CatalogAsset, classification: dict, terms: dict, verbose: bool):
    sens_col = SENSITIVITY_COLOURS.get(SensitivityLevel(asset.sensitivity_level), DIM)

    print(f"\n  {BOLD('┌─ ' + asset.schema_name + '.' + asset.table_name)}")
    print(f"  │  {DIM('Asset ID')}     : {asset.asset_id}")
    print(f"  │  {DIM('FQN')}          : {DIM(asset.fully_qualified_name)}")
    print(f"  │  {DIM('Domain')}       : {MAGENTA(asset.domain.upper())}")
    print(f"  │  {DIM('Rows / Size')}  : {_rows(asset.row_count)} rows  /  {_size(asset.size_bytes)}")
    print(f"  │  {DIM('Quality')}      : {BOLD(GREEN(asset.quality_grade))} ({asset.quality_score:.4f})")
    print(f"  │  {DIM('Sensitivity')}  : {sens_col(BOLD(asset.sensitivity_level.upper()))}")
    print(f"  │  {DIM('PII Columns')}  : {RED(str(asset.pii_column_count)) if asset.pii_column_count else GREEN('0')} / {asset.column_count}")
    if asset.business_terms:
        print(f"  │  {DIM('Terms')}        : {', '.join(CYAN(t) for t in asset.business_terms)}")
    print(f"  │  {DIM('Comment')}      : {DIM(asset.comment[:65])}")

    if verbose:
        print(f"  │")
        print(f"  │  {'Column':<28}{'Type':<18}{'Sensitivity':<16}{'Quality':<9}{'Top Term'}")
        print(f"  │  {_hr('·', 86)}")
        for col in asset.columns:
            slvl  = SensitivityLevel(col["sensitivity"])
            scol  = SENSITIVITY_COLOURS.get(slvl, DIM)
            qscore = col["quality_score"]
            qcol  = GREEN if qscore >= 0.8 else (YELLOW if qscore >= 0.5 else RED)
            term  = col["top_term"] or "—"
            print(
                f"  │  {col['name']:<28}"
                f"{DIM(col['data_type']):<26}"
                f"{scol(col['sensitivity'].upper()):<24}"
                f"{qcol(str(qscore)):<17}"
                f"{CYAN(term)}"
            )

    print(f"  └{'─' * 68}")


def print_summary(all_assets: list[CatalogAsset]):
    print(f"\n{BOLD(_hr('═'))}")
    print(BOLD(CYAN("  PIPELINE SUMMARY")))
    print(_hr())

    total_rows  = sum(a.row_count    for a in all_assets)
    total_bytes = sum(a.size_bytes   for a in all_assets)
    total_cols  = sum(a.column_count for a in all_assets)
    total_pii   = sum(a.pii_column_count for a in all_assets)

    grades = {}
    for a in all_assets:
        grades[a.quality_grade] = grades.get(a.quality_grade, 0) + 1

    sens_counts = {}
    for a in all_assets:
        sens_counts[a.sensitivity_level] = sens_counts.get(a.sensitivity_level, 0) + 1

    print(f"  Tables hydrated      : {BOLD(str(len(all_assets)))}")
    print(f"  Total rows cataloged : {BOLD(_rows(total_rows))}")
    print(f"  Total data volume    : {BOLD(_size(total_bytes))}")
    print(f"  Total columns        : {BOLD(str(total_cols))}")
    print(f"  PII columns found    : {RED(BOLD(str(total_pii)))}")
    print()
    print(f"  Quality grades  : " + "  ".join(
        f"{BOLD(g)}: {c}" for g, c in sorted(grades.items())
    ))
    print(f"  Sensitivity dist: " + "  ".join(
        f"{SENSITIVITY_COLOURS.get(SensitivityLevel(s), DIM)(BOLD(s.upper()))}: {c}"
        for s, c in sorted(sens_counts.items(), key=lambda x: SENSITIVITY_RANK[SensitivityLevel(x[0])])
    ))

    print()
    print(f"  {GREEN('✔')} BigQuery write    : {len(all_assets)} rows → {BOLD('my-data-platform.data_catalog.assets')}")
    print(f"  {GREEN('✔')} Audit log         : {len(all_assets)} events → {BOLD('my-data-platform.data_catalog.audit_log')}")
    print(f"  {GREEN('✔')} DataHub lineage   : {total_cols} fields → {BOLD('DataHub GMS (SIMULATED)')}")
    print(f"  {GREEN('✔')} Kafka events      : {len(all_assets)} → {BOLD('enriched-metadata-events')}")

    print()
    print(BOLD("  ⚠  PII ALERT — Tables containing RESTRICTED columns:"))
    restricted = [a for a in all_assets if a.sensitivity_level == "restricted"]
    if restricted:
        for a in restricted:
            restricted_cols = [
                col["name"] for col in a.columns
                if col["sensitivity"] == "restricted"
            ]
            print(f"     {RED('▶')} {a.schema_name}.{a.table_name} → {RED(', '.join(restricted_cols))}")
    else:
        print(f"     {GREEN('None')}")

    print()
    print(BOLD(_hr("═")))
    print(f"  {GREEN(BOLD('Dry run complete.'))}  All data is simulated — no real connections were made.")
    print(BOLD(_hr("═")))
    print()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def run(verbose: bool = False, emit_json: bool = False):
    print_pipeline_header()

    all_assets: list[CatalogAsset] = []

    # ── Stage 1 ──────────────────────────────────────────────
    print_stage(1, "Teradata Schema Discovery  (connector-service)")
    total_tables = sum(len(v) for v in MOCK_TERADATA_SCHEMAS.values())
    print(f"  Connecting to PROD-TERA-01 … {GREEN('OK (mock)')}")
    print(f"  Running DBC.DatabasesV query … found {BOLD(str(len(MOCK_TERADATA_SCHEMAS)))} schemas")
    print(f"  Running DBC.TablesV  query  … found {BOLD(str(total_tables))} tables")
    print(f"  Running DBC.ColumnsV query  … profiling columns via TABLESAMPLE 5%")

    for schema_name, tables in MOCK_TERADATA_SCHEMAS.items():
        print(f"\n    Schema {BOLD(schema_name)}:")
        for table in tables:
            total_cols = len(table.columns)
            print(f"      {GREEN('✔')} {table.table_name:<35} {_rows(table.row_count):>8} rows  {_size(table.size_bytes):>10}  {total_cols} cols")

    # ── Stages 2-5 per table ─────────────────────────────────
    print_stage(2, "Metadata Enrichment + Quality Scoring  (metadata-service)")
    print_stage(3, "PII Classification  (classification-service)")
    print_stage(4, "Business Term Assignment  (term-service)")
    print_stage(5, "Catalog Asset Assembly  (catalog-service)")

    for schema_name, tables in MOCK_TERADATA_SCHEMAS.items():
        for table in tables:
            quality        = compute_quality_score(table)
            classification = classify_table(table)
            term_assigns   = {col.name: suggest_terms(col.name) for col in table.columns}
            asset          = build_catalog_asset(table, quality, classification, term_assigns)

            all_assets.append(asset)
            print_table_result(asset, classification, term_assigns, verbose)

    # ── Stage 6 — BigQuery write ─────────────────────────────
    print_stage(6, "BigQuery Write  (catalog-service → GBQ)")
    for asset in all_assets:
        bq_result = simulate_bq_write(asset)
        audit_evt = simulate_audit_event(asset)
        print(f"  {GREEN('→')} {asset.schema_name}.{asset.table_name:<30}  partition={bq_result['partition']}  audit_id={audit_evt['event_id'][:8]}…")

    # ── Stage 7 — DataHub lineage ────────────────────────────
    print_stage(7, "DataHub Lineage Emit  (lineage-service)")
    for asset in all_assets:
        dh = simulate_datahub_emit(asset)
        print(f"  {GREEN('→')} {dh['entityUrn'][:60]}  ({dh['fields_emitted']} fields)")

    # ── Summary ───────────────────────────────────────────────
    print_summary(all_assets)

    if emit_json:
        out = [asdict(a) for a in all_assets]
        print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Catalog Teradata dry-run simulator")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-column breakdown for every table")
    parser.add_argument("--json",    "-j", action="store_true", help="Dump final catalog assets as JSON to stdout")
    args = parser.parse_args()
    run(verbose=args.verbose, emit_json=args.json)
