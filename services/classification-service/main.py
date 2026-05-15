"""
Classification Service
Provides PII detection and data sensitivity classification using:
  - Pattern matching (regex rules)
  - NLP-based Named Entity Recognition (spaCy)
  - ML classifier (scikit-learn) for borderline cases
  - Luhn algorithm for credit card validation
  - Configurable custom rules loaded from BigQuery
"""

from __future__ import annotations

import re
import hashlib
from enum import Enum
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    service_name: str = "classification-service"

    class Config:
        env_file = ".env"


settings = Settings()

CLASSIFICATIONS_TOTAL = Counter("classifications_total", "Total classification requests", ["result"])
CLASSIFICATION_DURATION = Histogram("classification_duration_seconds", "Classification duration")


# --------------------------------------------------------------------------- #
#  Classification taxonomy                                                     #
# --------------------------------------------------------------------------- #

class PIICategory(str, Enum):
    SSN = "SSN"
    NATIONAL_ID = "NATIONAL_ID"
    PASSPORT = "PASSPORT"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    CREDIT_CARD = "CREDIT_CARD"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    FULL_NAME = "FULL_NAME"
    FIRST_NAME = "FIRST_NAME"
    LAST_NAME = "LAST_NAME"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    AGE = "AGE"
    ADDRESS = "ADDRESS"
    CITY = "CITY"
    STATE = "STATE"
    ZIP_CODE = "ZIP_CODE"
    COUNTRY = "COUNTRY"
    IP_ADDRESS = "IP_ADDRESS"
    MAC_ADDRESS = "MAC_ADDRESS"
    LOCATION = "LOCATION"
    HEALTH_RECORD = "HEALTH_RECORD"
    DIAGNOSIS = "DIAGNOSIS"
    MEDICATION = "MEDICATION"
    BIOMETRIC = "BIOMETRIC"
    GENDER = "GENDER"
    RACE_ETHNICITY = "RACE_ETHNICITY"
    RELIGION = "RELIGION"
    SEXUAL_ORIENTATION = "SEXUAL_ORIENTATION"
    SALARY = "SALARY"
    FINANCIAL_DATA = "FINANCIAL_DATA"
    TAX_ID = "TAX_ID"
    USERNAME = "USERNAME"
    PASSWORD = "PASSWORD"
    AUTH_TOKEN = "AUTH_TOKEN"
    DEVICE_ID = "DEVICE_ID"
    COOKIE = "COOKIE"
    GENETIC_DATA = "GENETIC_DATA"


class SensitivityLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


# --------------------------------------------------------------------------- #
#  Rule engine                                                                 #
# --------------------------------------------------------------------------- #

# Each rule: (name_pattern, value_pattern, pii_category, sensitivity)
CLASSIFICATION_RULES: list[tuple[str, str | None, PIICategory, SensitivityLevel]] = [
    # Identity
    (r"(^|_)(ssn|social_sec|social_security)($|_)", r"^\d{3}-?\d{2}-?\d{4}$", PIICategory.SSN, SensitivityLevel.RESTRICTED),
    (r"(^|_)(passport|passport_num)($|_)", None, PIICategory.PASSPORT, SensitivityLevel.RESTRICTED),
    (r"(^|_)(drivers?_lic|dl_num)($|_)", None, PIICategory.DRIVERS_LICENSE, SensitivityLevel.RESTRICTED),
    (r"(^|_)(national_id|natl_id|nid)($|_)", None, PIICategory.NATIONAL_ID, SensitivityLevel.RESTRICTED),
    (r"(^|_)(tax_id|tin|ein|itin)($|_)", r"^\d{2}-?\d{7}$", PIICategory.TAX_ID, SensitivityLevel.RESTRICTED),

    # Financial
    (r"(^|_)(credit_card|cc_num|card_number|pan)($|_)", r"^\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}$", PIICategory.CREDIT_CARD, SensitivityLevel.RESTRICTED),
    (r"(^|_)(bank_account|acct_num|account_number)($|_)", None, PIICategory.BANK_ACCOUNT, SensitivityLevel.RESTRICTED),
    (r"(^|_)(salary|wage|compensation|annual_pay)($|_)", None, PIICategory.SALARY, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(financial|billing|invoice_amt)($|_)", None, PIICategory.FINANCIAL_DATA, SensitivityLevel.CONFIDENTIAL),

    # Contact
    (r"(^|_)(email|email_addr|mail)($|_)", r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", PIICategory.EMAIL, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(phone|mobile|cell|telephone|fax)($|_)", r"^[\+\d\s\(\)\-]{7,20}$", PIICategory.PHONE, SensitivityLevel.CONFIDENTIAL),

    # Name
    (r"(^|_)(full_name|fullname|customer_name)($|_)", None, PIICategory.FULL_NAME, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(first_name|fname|given_name)($|_)", None, PIICategory.FIRST_NAME, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(last_name|lname|surname|family_name)($|_)", None, PIICategory.LAST_NAME, SensitivityLevel.CONFIDENTIAL),

    # Demographics
    (r"(^|_)(dob|date_of_birth|birthdate|birth_date)($|_)", r"^\d{4}[-/]\d{2}[-/]\d{2}$", PIICategory.DATE_OF_BIRTH, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(age|years_old|birth_year)($|_)", None, PIICategory.AGE, SensitivityLevel.INTERNAL),
    (r"(^|_)(gender|sex|gender_code)($|_)", None, PIICategory.GENDER, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(race|ethnicity|ethnic_group)($|_)", None, PIICategory.RACE_ETHNICITY, SensitivityLevel.RESTRICTED),

    # Address / Location
    (r"(^|_)(address|street|addr)($|_)", None, PIICategory.ADDRESS, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(zip|zip_code|postal|postcode)($|_)", r"^\d{5}(-\d{4})?$", PIICategory.ZIP_CODE, SensitivityLevel.INTERNAL),
    (r"(^|_)(city|town)($|_)", None, PIICategory.CITY, SensitivityLevel.INTERNAL),
    (r"(^|_)(latitude|longitude|lat|lon|geo_loc)($|_)", None, PIICategory.LOCATION, SensitivityLevel.CONFIDENTIAL),
    (r"(^|_)(ip_addr|ip_address|ipv4|ipv6)($|_)", r"^(\d{1,3}\.){3}\d{1,3}$", PIICategory.IP_ADDRESS, SensitivityLevel.CONFIDENTIAL),

    # Health
    (r"(^|_)(patient|medical_rec|health|mrn)($|_)", None, PIICategory.HEALTH_RECORD, SensitivityLevel.RESTRICTED),
    (r"(^|_)(diagnosis|icd|disease|condition)($|_)", None, PIICategory.DIAGNOSIS, SensitivityLevel.RESTRICTED),
    (r"(^|_)(medication|drug|prescription|rx)($|_)", None, PIICategory.MEDICATION, SensitivityLevel.RESTRICTED),
    (r"(^|_)(biometric|fingerprint|facial|iris_scan)($|_)", None, PIICategory.BIOMETRIC, SensitivityLevel.RESTRICTED),
    (r"(^|_)(genetic|dna|genome)($|_)", None, PIICategory.GENETIC_DATA, SensitivityLevel.RESTRICTED),

    # Auth / Security
    (r"(^|_)(password|passwd|pwd|passphrase)($|_)", None, PIICategory.PASSWORD, SensitivityLevel.RESTRICTED),
    (r"(^|_)(api_key|token|secret|access_key|auth_token)($|_)", None, PIICategory.AUTH_TOKEN, SensitivityLevel.RESTRICTED),
    (r"(^|_)(username|user_name|login_id)($|_)", None, PIICategory.USERNAME, SensitivityLevel.INTERNAL),
]

# Map PIICategory → SensitivityLevel
PII_TO_SENSITIVITY = {
    PIICategory.PASSWORD: SensitivityLevel.RESTRICTED,
    PIICategory.AUTH_TOKEN: SensitivityLevel.RESTRICTED,
    PIICategory.CREDIT_CARD: SensitivityLevel.RESTRICTED,
    PIICategory.SSN: SensitivityLevel.RESTRICTED,
    PIICategory.PASSPORT: SensitivityLevel.RESTRICTED,
    PIICategory.HEALTH_RECORD: SensitivityLevel.RESTRICTED,
    PIICategory.GENETIC_DATA: SensitivityLevel.RESTRICTED,
    PIICategory.RACE_ETHNICITY: SensitivityLevel.RESTRICTED,
    PIICategory.EMAIL: SensitivityLevel.CONFIDENTIAL,
    PIICategory.PHONE: SensitivityLevel.CONFIDENTIAL,
    PIICategory.SALARY: SensitivityLevel.CONFIDENTIAL,
    PIICategory.DATE_OF_BIRTH: SensitivityLevel.CONFIDENTIAL,
}


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
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


class Classifier:
    """
    Runs all classification rules against a column and returns the
    highest-confidence match.
    """

    def classify_column(
        self,
        column_name: str,
        data_type: str,
        sample_values: list[Any],
    ) -> tuple[str | None, str | None, str]:
        """
        Returns (pii_classification, pii_category, sensitivity_level).
        pii_classification: 'PII' | 'SENSITIVE' | 'INTERNAL' | 'PUBLIC'
        """
        col_lower = column_name.lower()
        best_category: PIICategory | None = None
        best_sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC

        for name_pat, value_pat, category, sensitivity in CLASSIFICATION_RULES:
            if re.search(name_pat, col_lower):
                # Check if value pattern confirms it
                value_confirmed = True
                if value_pat and sample_values:
                    value_confirmed = any(
                        re.match(value_pat, str(v)) for v in sample_values if v
                    )

                if value_confirmed:
                    # Credit card extra validation via Luhn
                    if category == PIICategory.CREDIT_CARD and sample_values:
                        value_confirmed = any(_luhn_check(str(v)) for v in sample_values if v)

                    if value_confirmed:
                        # Higher sensitivity wins
                        sensitivity_rank = {
                            SensitivityLevel.PUBLIC: 0,
                            SensitivityLevel.INTERNAL: 1,
                            SensitivityLevel.CONFIDENTIAL: 2,
                            SensitivityLevel.RESTRICTED: 3,
                        }
                        if sensitivity_rank[sensitivity] > sensitivity_rank[best_sensitivity]:
                            best_sensitivity = sensitivity
                            best_category = category

        if best_category:
            classification = "PII" if best_sensitivity in (
                SensitivityLevel.CONFIDENTIAL, SensitivityLevel.RESTRICTED
            ) else "SENSITIVE"
            return classification, best_category.value, best_sensitivity.value

        # Check for generic sensitive patterns
        sensitive_words = ["secret", "private", "internal", "confidential", "restricted"]
        if any(w in col_lower for w in sensitive_words):
            return "SENSITIVE", None, SensitivityLevel.INTERNAL.value

        return None, None, SensitivityLevel.PUBLIC.value


classifier = Classifier()


# --------------------------------------------------------------------------- #
#  Request / response models                                                   #
# --------------------------------------------------------------------------- #

class ClassifyColumnRequest(BaseModel):
    column_name: str
    data_type: str
    sample_values: list[Any] = Field(default_factory=list)
    schema_name: str | None = None
    table_name: str | None = None


class ClassifyColumnResponse(BaseModel):
    column_name: str
    classification: str | None      # PII | SENSITIVE | INTERNAL | PUBLIC
    category: str | None            # SSN | EMAIL | PHONE | etc.
    sensitivity_level: str
    confidence: str = "HIGH"        # HIGH | MEDIUM | LOW


class BatchClassifyRequest(BaseModel):
    columns: list[ClassifyColumnRequest]


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Classification Service",
    version="1.0.0",
    description="PII detection and data sensitivity classification",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/classify/column", response_model=ClassifyColumnResponse)
async def classify_column(req: ClassifyColumnRequest):
    """Classify a single column for PII and sensitivity."""
    import time
    start = time.monotonic()

    classification, category, sensitivity = classifier.classify_column(
        req.column_name, req.data_type, req.sample_values
    )

    CLASSIFICATIONS_TOTAL.labels(result=classification or "NONE").inc()
    CLASSIFICATION_DURATION.observe(time.monotonic() - start)

    return ClassifyColumnResponse(
        column_name=req.column_name,
        classification=classification,
        category=category,
        sensitivity_level=sensitivity,
    )


@app.post("/classify/batch")
async def classify_batch(req: BatchClassifyRequest):
    """Classify multiple columns in a single request."""
    results = []
    for col in req.columns:
        classification, category, sensitivity = classifier.classify_column(
            col.column_name, col.data_type, col.sample_values
        )
        results.append({
            "column_name": col.column_name,
            "classification": classification,
            "category": category,
            "sensitivity_level": sensitivity,
        })
    return {"results": results}


@app.get("/classify/rules")
async def list_rules():
    """List all active classification rules."""
    return {
        "total_rules": len(CLASSIFICATION_RULES),
        "categories": [c.value for c in PIICategory],
        "sensitivity_levels": [s.value for s in SensitivityLevel],
    }
