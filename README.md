# Enterprise Data Catalog Platform

A production-grade, cloud-native data catalog platform built with microservices, Zero Trust security, and full data lineage tracking.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES LAYER                                │
│   [Teradata]   [MS SQL Server]   [BigQuery]   [PostgreSQL]   [Snowflake] │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ Schema Hydration / Metadata Extraction
┌────────────────────────────▼────────────────────────────────────────────┐
│                     CONNECTOR SERVICE                                    │
│         Schema Discovery → Column Profiling → Statistics                │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ Raw Metadata Events (Kafka)
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐  ┌─────────────────┐  ┌────────────────────┐
│   METADATA    │  │ CLASSIFICATION  │  │  TERM ASSIGNMENT   │
│   SERVICE     │  │    SERVICE      │  │     SERVICE        │
│ Enrich·Stats  │  │ PII·Sensitivity │  │ Business Glossary  │
└───────┬───────┘  └────────┬────────┘  └─────────┬──────────┘
        └──────────────────►│◄───────────────────┘
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                       CATALOG SERVICE                                  │
│           Asset Registry · Search · Versioning · Relationships         │
│                    ──── BigQuery Storage ────                          │
└─────────────────┬─────────────────────────┬──────────────────────────┘
                  │                         │
        ┌─────────▼──────┐       ┌──────────▼──────────┐
        │ LINEAGE SERVICE│       │   AUDIT SERVICE      │
        │   (DataHub)    │       │   (BigQuery logs)    │
        └────────────────┘       └─────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────────────┐
│                        API GATEWAY                                    │
│           Rate Limiting · Auth Enforcement · Load Balancing            │
└─────────────────┬────────────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────────────┐
│                    ZERO TRUST AUTH SERVICE                             │
│    JWT (15min TTL) · OPA Policy Engine · mTLS · SPIFFE/SPIRE          │
└─────────────────┬────────────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────────────┐
│                      REACT FRONTEND                                   │
│  Catalog Browser · Lineage Graph · Classification Dashboard · Admin   │
└──────────────────────────────────────────────────────────────────────┘

              KUBERNETES LAYER (GKE / EKS / AKS)
              ├── Horizontal Pod Autoscaling (HPA)
              ├── Network Policies (Zero Trust Mesh)
              └── Istio Service Mesh (mTLS)

              MONITORING LAYER
              ├── Prometheus (metrics scraping)
              ├── Grafana (dashboards + alerting)
              └── 99.99% SLA → AlertManager → PagerDuty
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + TypeScript + TailwindCSS + React Flow (lineage) |
| API Gateway | FastAPI + Nginx |
| Backend Services | Python 3.11 + FastAPI + Pydantic v2 |
| Storage | Google BigQuery (catalog + audit) + Redis (cache) |
| Message Queue | Apache Kafka |
| Data Lineage | DataHub (LinkedIn OSS) |
| Auth | JWT + OPA (Open Policy Agent) + SPIFFE/SPIRE |
| Orchestration | Kubernetes 1.28 + Helm 3 + Istio |
| Monitoring | Prometheus + Grafana + AlertManager |
| CI/CD | GitHub Actions + ArgoCD |

## Microservices

| Service | Port | Responsibility |
|---|---|---|
| `connector-service` | 8001 | Source connectivity, schema hydration |
| `metadata-service` | 8002 | Metadata enrichment, quality scoring |
| `classification-service` | 8003 | PII/sensitivity classification |
| `term-service` | 8004 | Business glossary, term assignment |
| `catalog-service` | 8005 | Core catalog CRUD, BigQuery storage |
| `auth-service` | 8006 | Zero Trust RBAC, JWT, OPA |
| `audit-service` | 8007 | Immutable audit log (BigQuery) |
| `lineage-service` | 8008 | DataHub lineage integration |
| `api-gateway` | 8000 | Routing, rate limiting, auth enforcement |

## Quick Start

```bash
# Clone and start local environment
git clone <repo>
cd data-catalog-platform

# Start all services
docker-compose up -d

# Deploy to Kubernetes
kubectl apply -k kubernetes/base/
helm upgrade --install data-catalog helm/data-catalog/ \
  --namespace data-catalog \
  --values helm/data-catalog/values.yaml
```

## Security

- **Zero Trust**: Every request verified regardless of origin
- **mTLS**: All inter-service communication encrypted
- **RBAC**: Roles: `admin`, `data_steward`, `data_analyst`, `viewer`
- **OPA**: Policy-as-code with GitOps workflow
- **Audit**: Every read/write logged immutably to BigQuery

## Compliance

- GDPR / CCPA via PII classification and right-to-erasure workflow
- SOC 2 Type II via comprehensive audit logging
- HIPAA via sensitivity classification and access controls


## Troubleshooting
- Remove Volume
docker volume rm data-catalog-platform_kafka-data data-catalog-platform_zookeeper-data
