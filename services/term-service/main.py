"""
Term Assignment Service — Business Glossary
Manages the enterprise business glossary: term definitions,
synonyms, abbreviations, and assignment to catalog assets.
Provides fuzzy matching for automatic term suggestions.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
import httpx
import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    service_name: str = "term-service"
    audit_service_url: str = "http://audit-service:8007"

    class Config:
        env_file = ".env"


settings = Settings()

# --------------------------------------------------------------------------- #
#  Audit helper                                                               #
# --------------------------------------------------------------------------- #

_audit_tasks: set = set()


def _audit(event_type: str, **kwargs) -> None:
    """Fire-and-forget audit event — strong task reference prevents GC."""
    async def _post() -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{settings.audit_service_url}/audit/events",
                    json={"event_type": event_type, "service": "term-service", **kwargs},
                )
        except Exception as exc:
            log.warning("audit_post_failed", event_type=event_type, error=str(exc))
    task = asyncio.ensure_future(_post())
    _audit_tasks.add(task)
    task.add_done_callback(_audit_tasks.discard)


# --------------------------------------------------------------------------- #
#  Data models                                                                 #
# --------------------------------------------------------------------------- #

class GlossaryTerm(BaseModel):
    term_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    definition: str
    domain: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    abbreviations: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)   # term_ids
    owner: str | None = None
    steward: str | None = None
    status: str = "ACTIVE"   # DRAFT | ACTIVE | DEPRECATED
    examples: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: dict[str, str] = Field(default_factory=dict)


class TermAssignment(BaseModel):
    assignment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    term_id: str
    asset_fqn: str                     # fully qualified name of the catalog asset
    asset_type: str = "COLUMN"         # TABLE | COLUMN | SCHEMA
    confidence: float = 1.0            # 0.0–1.0; 1.0 = manually assigned
    assigned_by: str = "system"
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SuggestTermsRequest(BaseModel):
    column_name: str
    data_type: str
    table_name: str | None = None
    description: str | None = None


class AssignTermRequest(BaseModel):
    term_id: str
    asset_fqn: str
    asset_type: str = "COLUMN"
    confidence: float = 1.0
    assigned_by: str = "user"


# --------------------------------------------------------------------------- #
#  In-memory store (replace with BigQuery in production)                       #
# --------------------------------------------------------------------------- #

# Seed with common enterprise terms
_SEED_TERMS = [
    GlossaryTerm(name="Customer", definition="An individual or organization that purchases or uses company products/services.", domain="customer", synonyms=["Client", "Consumer", "Buyer", "Account"], abbreviations=["CUST"]),
    GlossaryTerm(name="Product SKU", definition="Stock Keeping Unit — unique identifier for a product variant.", domain="product", synonyms=["Item Code", "Product Code", "Part Number"], abbreviations=["SKU"]),
    GlossaryTerm(name="Fiscal Year", definition="The 12-month accounting period used for financial reporting.", domain="finance", synonyms=["Financial Year", "Tax Year"], abbreviations=["FY"]),
    GlossaryTerm(name="Revenue", definition="Total income generated from sales of goods or services before deductions.", domain="finance", synonyms=["Gross Revenue", "Top Line", "Turnover"]),
    GlossaryTerm(name="Net Income", definition="Profit remaining after all expenses, taxes, and costs are deducted.", domain="finance", synonyms=["Net Profit", "Bottom Line", "Net Earnings"]),
    GlossaryTerm(name="Employee ID", definition="Unique identifier assigned to each employee in the HR system.", domain="hr", synonyms=["Staff ID", "Worker ID", "Personnel Number"], abbreviations=["EMP_ID", "EID"]),
    GlossaryTerm(name="Order ID", definition="Unique identifier for a sales or purchase order.", domain="operations", synonyms=["Order Number", "PO Number"], abbreviations=["ORD_ID"]),
    GlossaryTerm(name="Transaction Date", definition="The date on which a financial transaction occurred.", domain="finance", synonyms=["Transaction Timestamp", "Event Date", "Posting Date"]),
    GlossaryTerm(name="Cost Center", definition="Organizational unit that incurs costs and is responsible for budget control.", domain="finance", synonyms=["Budget Center", "Cost Unit"], abbreviations=["CC", "COST_CTR"]),
    GlossaryTerm(name="PII", definition="Personally Identifiable Information — data that could identify a specific individual.", domain="security", synonyms=["Personal Data", "Personal Information"], abbreviations=["PII"]),
    GlossaryTerm(name="SLA", definition="Service Level Agreement — commitment defining expected service standards and response times.", domain="operations", synonyms=["Service Agreement"], abbreviations=["SLA"]),
    GlossaryTerm(name="KYC", definition="Know Your Customer — process of verifying the identity of clients.", domain="compliance", synonyms=["Customer Verification", "Customer Due Diligence"], abbreviations=["KYC", "CDD"]),
    GlossaryTerm(name="GDPR", definition="General Data Protection Regulation — EU law on data protection and privacy.", domain="compliance", synonyms=["Data Protection Regulation"], abbreviations=["GDPR"]),
    GlossaryTerm(name="Data Lineage", definition="The history and lifecycle of data showing its origins, movements, and transformations.", domain="data_governance", synonyms=["Data Provenance", "Data History"]),
    GlossaryTerm(name="Master Data", definition="Core business data that is shared and reused across the enterprise.", domain="data_governance", synonyms=["Reference Data", "Golden Record"]),
]

terms_store: dict[str, GlossaryTerm] = {t.term_id: t for t in _SEED_TERMS}
assignments_store: list[TermAssignment] = []


# --------------------------------------------------------------------------- #
#  Term suggestion engine                                                      #
# --------------------------------------------------------------------------- #

def _tokenize(text: str) -> set[str]:
    """Split CamelCase and snake_case into tokens, lowercase."""
    # Split on underscores, hyphens, and CamelCase boundaries
    text = re.sub(r"([A-Z][a-z])", r" \1", text)
    return {t.lower() for t in re.split(r"[_\-\s]+", text) if len(t) > 2}


def suggest_terms_for_column(col_name: str, data_type: str, table_name: str | None = None) -> list[dict]:
    """
    Find best-matching glossary terms for a column using token overlap.
    Returns top 5 suggestions with confidence scores.
    """
    query_tokens = _tokenize(col_name)
    if table_name:
        query_tokens |= _tokenize(table_name)

    matches: list[tuple[float, GlossaryTerm]] = []

    for term in terms_store.values():
        if term.status != "ACTIVE":
            continue

        # Build term tokens from name + synonyms + abbreviations
        term_tokens = _tokenize(term.name)
        for syn in term.synonyms:
            term_tokens |= _tokenize(syn)
        for abbr in term.abbreviations:
            term_tokens.add(abbr.lower())

        if not term_tokens:
            continue

        # Jaccard similarity
        intersection = len(query_tokens & term_tokens)
        union = len(query_tokens | term_tokens)
        score = intersection / union if union > 0 else 0.0

        # Boost exact name match
        if col_name.lower() == term.name.lower():
            score = 1.0
        elif any(col_name.lower() == s.lower() for s in term.synonyms):
            score = min(score + 0.3, 1.0)

        if score > 0.1:
            matches.append((score, term))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [
        {"term_id": t.term_id, "name": t.name, "definition": t.definition, "confidence": round(score, 3)}
        for score, t in matches[:5]
    ]


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Term Service",
    version="1.0.0",
    description="Business glossary and term assignment management",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Terms CRUD ---

@app.get("/terms")
async def list_terms(
    domain: str | None = None,
    status: str | None = None,
    q: str | None = Query(None, description="Search query"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
):
    terms = list(terms_store.values())
    if domain:
        terms = [t for t in terms if t.domain == domain]
    if status:
        terms = [t for t in terms if t.status == status]
    if q:
        q_lower = q.lower()
        terms = [
            t for t in terms
            if q_lower in t.name.lower()
            or q_lower in t.definition.lower()
            or any(q_lower in s.lower() for s in t.synonyms)
        ]
    return {"total": len(terms), "terms": [t.model_dump() for t in terms[offset: offset + limit]]}


@app.post("/terms", status_code=201)
async def create_term(term: GlossaryTerm):
    terms_store[term.term_id] = term
    log.info("term_created", term_id=term.term_id, name=term.name)
    _audit("TERM_CREATED", resource_id=term.term_id, details={"name": term.name, "domain": term.domain})
    return term.model_dump()


@app.get("/terms/{term_id}")
async def get_term(term_id: str):
    if term_id not in terms_store:
        raise HTTPException(404, f"Term {term_id} not found")
    return terms_store[term_id].model_dump()


@app.put("/terms/{term_id}")
async def update_term(term_id: str, updates: dict):
    if term_id not in terms_store:
        raise HTTPException(404, f"Term {term_id} not found")
    term = terms_store[term_id]
    for key, value in updates.items():
        if hasattr(term, key):
            setattr(term, key, value)
    term.updated_at = datetime.now(timezone.utc)
    log.info("term_updated", term_id=term_id)
    _audit("TERM_UPDATED", resource_id=term_id, details={"name": term.name, "updated_fields": list(updates.keys())})
    return term.model_dump()


@app.delete("/terms/{term_id}")
async def deprecate_term(term_id: str):
    if term_id not in terms_store:
        raise HTTPException(404, f"Term {term_id} not found")
    terms_store[term_id].status = "DEPRECATED"
    return {"message": f"Term {term_id} deprecated"}


# --- Term assignment ---

@app.post("/terms/suggest")
async def suggest_terms(req: SuggestTermsRequest):
    suggestions = suggest_terms_for_column(req.column_name, req.data_type, req.table_name)
    return {"column_name": req.column_name, "terms": [s["name"] for s in suggestions], "suggestions": suggestions}


@app.post("/assignments", status_code=201)
async def assign_term(req: AssignTermRequest):
    if req.term_id not in terms_store:
        raise HTTPException(404, f"Term {req.term_id} not found")
    assignment = TermAssignment(
        term_id=req.term_id,
        asset_fqn=req.asset_fqn,
        asset_type=req.asset_type,
        confidence=req.confidence,
        assigned_by=req.assigned_by,
    )
    assignments_store.append(assignment)
    log.info("term_assigned", term_id=req.term_id, asset=req.asset_fqn)
    _audit("TERM_ASSIGNED", resource_id=req.term_id, details={"asset_fqn": req.asset_fqn, "asset_type": req.asset_type, "assigned_by": req.assigned_by})
    return assignment.model_dump()


@app.get("/assignments")
async def list_assignments(asset_fqn: str | None = None, term_id: str | None = None):
    results = assignments_store
    if asset_fqn:
        results = [a for a in results if a.asset_fqn == asset_fqn]
    if term_id:
        results = [a for a in results if a.term_id == term_id]
    return {"total": len(results), "assignments": [a.model_dump() for a in results]}
