"""
Data Lineage Service — DataHub Integration
Tracks data lineage across the entire data platform.
Pushes lineage metadata to DataHub via its REST Emitter API.
Supports: table-to-table lineage, column-level lineage, pipeline tracking.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

log = structlog.get_logger(__name__)


class Settings(BaseSettings):
    datahub_gms_url: str = "http://datahub-gms:8080"
    datahub_token: str = ""
    kafka_bootstrap_servers: str = "kafka:9092"
    catalog_service_url: str = "http://catalog-service:8005"
    service_name: str = "lineage-service"
    # POC mode: set DATAHUB_ENABLED=false to skip DataHub HTTP calls
    datahub_enabled: bool = True

    class Config:
        env_file = ".env"


settings = Settings()

LINEAGE_EVENTS = Counter("lineage_events_total", "Lineage events emitted to DataHub", ["status"])


# --------------------------------------------------------------------------- #
#  DataHub REST Emitter                                                         #
# --------------------------------------------------------------------------- #

class DataHubEmitter:
    """
    Emits metadata change proposals (MCPs) to DataHub GMS REST endpoint.
    Supports dataset lineage, schema metadata, and data process lineage.
    """

    def __init__(self, gms_url: str, token: str | None = None):
        self.gms_url = gms_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        }

    def _make_dataset_urn(self, platform: str, name: str, env: str = "PROD") -> str:
        """Generate a DataHub dataset URN."""
        return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"

    def _make_datajob_urn(self, flow: str, job: str) -> str:
        return f"urn:li:dataJob:(urn:li:dataFlow:(orchestrator,{flow},PROD),{job})"

    async def emit_dataset_lineage(
        self,
        source_fqn: str,
        target_fqn: str,
        source_platform: str,
        target_platform: str,
        column_mapping: list[dict] | None = None,
    ) -> bool:
        """Emit a dataset-level lineage edge between source and target."""
        source_urn = self._make_dataset_urn(source_platform, source_fqn)
        target_urn = self._make_dataset_urn(target_platform, target_fqn)

        mcp = {
            "entityType": "dataset",
            "entityUrn": target_urn,
            "changeType": "UPSERT",
            "aspectName": "upstreamLineage",
            "aspect": {
                "__type": "UpstreamLineage",
                "upstreams": [
                    {
                        "auditStamp": {
                            "time": int(time.time() * 1000),
                            "actor": "urn:li:corpuser:datajobs",
                        },
                        "dataset": source_urn,
                        "type": "TRANSFORMED",
                    }
                ],
                **({"fineGrainedLineages": column_mapping} if column_mapping else {}),
            },
        }

        return await self._emit_mcp(mcp)

    async def emit_schema_metadata(
        self, platform: str, dataset_name: str, columns: list[dict]
    ) -> bool:
        """Emit schema metadata for a dataset to DataHub."""
        dataset_urn = self._make_dataset_urn(platform, dataset_name)

        schema_fields = []
        for col in columns:
            schema_fields.append({
                "fieldPath": col["name"],
                "nativeDataType": col.get("data_type", "VARCHAR"),
                "type": {
                    "type": {
                        "__type": "StringType" if "VARCHAR" in col.get("data_type", "") else "NumberType"
                    }
                },
                "description": col.get("description", ""),
                "nullable": col.get("is_nullable", True),
                "tags": {
                    "tags": [
                        {"tag": f"urn:li:tag:{col['pii_classification']}"}
                    ] if col.get("pii_classification") else []
                },
            })

        mcp = {
            "entityType": "dataset",
            "entityUrn": dataset_urn,
            "changeType": "UPSERT",
            "aspectName": "schemaMetadata",
            "aspect": {
                "__type": "SchemaMetadata",
                "schemaName": dataset_name,
                "platform": f"urn:li:dataPlatform:{platform}",
                "version": int(time.time()),
                "hash": "",
                "platformSchema": {
                    "__type": "TableSchema",
                    "schema": json.dumps({"columns": [c["name"] for c in columns]}),
                },
                "fields": schema_fields,
            },
        }

        return await self._emit_mcp(mcp)

    async def emit_dataset_properties(
        self, platform: str, dataset_name: str, asset: dict
    ) -> bool:
        """Emit dataset properties (description, tags, owners) to DataHub."""
        dataset_urn = self._make_dataset_urn(platform, dataset_name)

        mcp = {
            "entityType": "dataset",
            "entityUrn": dataset_urn,
            "changeType": "UPSERT",
            "aspectName": "datasetProperties",
            "aspect": {
                "__type": "DatasetProperties",
                "description": asset.get("description", ""),
                "customProperties": {
                    "domain": asset.get("domain", ""),
                    "sensitivity_level": asset.get("sensitivity_level", "INTERNAL"),
                    "data_owner": asset.get("data_owner", ""),
                    "quality_grade": asset.get("quality_grade", ""),
                },
                "tags": list(asset.get("tags", {}).keys()),
            },
        }

        return await self._emit_mcp(mcp)

    async def emit_data_process_lineage(
        self,
        pipeline_id: str,
        job_name: str,
        input_datasets: list[str],
        output_datasets: list[str],
        platform: str = "teradata",
    ) -> bool:
        """Track ETL pipeline lineage in DataHub."""
        job_urn = self._make_datajob_urn(pipeline_id, job_name)

        input_urns = [self._make_dataset_urn(platform, d) for d in input_datasets]
        output_urns = [self._make_dataset_urn(platform, d) for d in output_datasets]

        mcp = {
            "entityType": "dataJob",
            "entityUrn": job_urn,
            "changeType": "UPSERT",
            "aspectName": "dataJobInputOutput",
            "aspect": {
                "__type": "DataJobInputOutput",
                "inputDatasets": input_urns,
                "outputDatasets": output_urns,
                "inputDatajobs": [],
            },
        }

        return await self._emit_mcp(mcp)

    async def _emit_mcp(self, mcp: dict) -> bool:
        """POST a Metadata Change Proposal to DataHub GMS.
        When DATAHUB_ENABLED=false (POC mode) the call is skipped and
        the MCP is logged locally instead."""
        if not settings.datahub_enabled:
            log.info(
                "datahub_emit_skipped_poc_mode",
                entity_urn=mcp.get("entityUrn", "unknown"),
                aspect=mcp.get("aspectName", "unknown"),
            )
            LINEAGE_EVENTS.labels(status="poc_skipped").inc()
            return True
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.gms_url}/aspects?action=ingestProposal",
                    json={"proposal": mcp},
                    headers=self.headers,
                )
                success = resp.status_code in (200, 201)
                LINEAGE_EVENTS.labels(status="success" if success else "failure").inc()
                if not success:
                    log.warning("datahub_emit_failed", status=resp.status_code, body=resp.text[:200])
                return success
        except Exception as exc:
            LINEAGE_EVENTS.labels(status="error").inc()
            log.error("datahub_emit_error", error=str(exc))
            return False


# --------------------------------------------------------------------------- #
#  Data models                                                                 #
# --------------------------------------------------------------------------- #

class LineageEdge(BaseModel):
    lineage_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_fqn: str
    target_fqn: str
    source_platform: str = "teradata"
    target_platform: str = "bigquery"
    relationship: str = "TRANSFORMED"
    transformation_sql: str | None = None
    pipeline_id: str | None = None
    column_mappings: list[dict] = Field(default_factory=list)
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineLineageRequest(BaseModel):
    pipeline_id: str
    job_name: str
    input_datasets: list[str]
    output_datasets: list[str]
    platform: str = "teradata"


class EmitSchemaRequest(BaseModel):
    platform: str
    dataset_name: str
    columns: list[dict]
    asset_properties: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Lineage store (in-memory; replace with BigQuery in production)              #
# --------------------------------------------------------------------------- #

lineage_store: list[LineageEdge] = []
emitter: DataHubEmitter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global emitter
    emitter = DataHubEmitter(settings.datahub_gms_url, settings.datahub_token or None)
    log.info("lineage_service_started", datahub_url=settings.datahub_gms_url)
    yield
    log.info("lineage_service_stopped")


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                 #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Data Catalog — Lineage Service",
    version="1.0.0",
    description="DataHub integration for full data lineage tracking",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/lineage/edge", status_code=201)
async def create_lineage_edge(edge: LineageEdge):
    """Record a lineage edge and emit it to DataHub."""
    lineage_store.append(edge)

    if emitter:
        success = await emitter.emit_dataset_lineage(
            edge.source_fqn,
            edge.target_fqn,
            edge.source_platform,
            edge.target_platform,
            edge.column_mappings or None,
        )
        if not success:
            log.warning("datahub_lineage_emit_failed", edge_id=edge.lineage_id)

    log.info("lineage_edge_created", source=edge.source_fqn, target=edge.target_fqn)
    return edge.model_dump()


@app.post("/lineage/pipeline")
async def emit_pipeline_lineage(req: PipelineLineageRequest):
    """Track an ETL pipeline's lineage in DataHub."""
    if not emitter:
        raise HTTPException(503, "Emitter not initialized")

    success = await emitter.emit_data_process_lineage(
        req.pipeline_id,
        req.job_name,
        req.input_datasets,
        req.output_datasets,
        req.platform,
    )
    return {"success": success, "pipeline_id": req.pipeline_id, "job_name": req.job_name}


@app.post("/lineage/schema")
async def emit_schema_to_datahub(req: EmitSchemaRequest):
    """Push schema metadata to DataHub for a dataset."""
    if not emitter:
        raise HTTPException(503, "Emitter not initialized")

    schema_ok = await emitter.emit_schema_metadata(req.platform, req.dataset_name, req.columns)
    props_ok = await emitter.emit_dataset_properties(req.platform, req.dataset_name, req.asset_properties)
    return {"schema_emitted": schema_ok, "properties_emitted": props_ok}


@app.get("/lineage")
async def get_lineage(
    fqn: str | None = None,
    direction: str = "both",  # upstream | downstream | both
    depth: int = 3,
):
    """Get lineage graph for an asset."""
    if not fqn:
        return {"edges": [e.model_dump() for e in lineage_store]}

    # Traverse the graph
    edges: list[dict] = []

    if direction in ("upstream", "both"):
        upstream = [e for e in lineage_store if e.target_fqn == fqn]
        edges.extend([e.model_dump() for e in upstream])

    if direction in ("downstream", "both"):
        downstream = [e for e in lineage_store if e.source_fqn == fqn]
        edges.extend([e.model_dump() for e in downstream])

    return {
        "fqn": fqn,
        "direction": direction,
        "depth": depth,
        "edge_count": len(edges),
        "edges": edges,
    }


@app.get("/lineage/impact/{asset_fqn:path}")
async def get_impact_analysis(asset_fqn: str):
    """
    Perform downstream impact analysis for an asset.
    Returns all assets that would be affected if this asset changes.
    """
    impacted: set[str] = set()
    queue = [asset_fqn]

    while queue:
        current = queue.pop()
        downstream = [e.target_fqn for e in lineage_store if e.source_fqn == current]
        for d in downstream:
            if d not in impacted:
                impacted.add(d)
                queue.append(d)

    return {
        "source_asset": asset_fqn,
        "impacted_count": len(impacted),
        "impacted_assets": sorted(impacted),
    }
