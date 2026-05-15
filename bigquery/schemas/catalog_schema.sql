-- ============================================================
-- BigQuery Schema — Data Catalog Platform
-- All tables are partitioned for cost efficiency.
-- ============================================================

-- Dataset creation (run once)
CREATE SCHEMA IF NOT EXISTS `data_catalog`
OPTIONS (
  description = "Data Catalog Platform storage",
  location = "US"
);

-- ============================================================
-- ASSETS TABLE — Core catalog asset registry
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_catalog.assets` (
  asset_id         STRING    NOT NULL,
  fqn              STRING    NOT NULL,   -- e.g. teradata://schema.table
  source_id        STRING,
  source_type      STRING,               -- teradata | mssql | bigquery
  database_name    STRING,
  schema_name      STRING,
  table_name       STRING,
  description      STRING,
  domain           STRING,               -- finance | hr | customer | operations
  data_owner       STRING,
  data_steward     STRING,
  sensitivity_level STRING,              -- PUBLIC | INTERNAL | CONFIDENTIAL | RESTRICTED
  row_count        INT64,
  size_bytes       INT64,
  quality_score    FLOAT64,              -- 0.0 – 1.0
  quality_grade    STRING,               -- A | B | C | D | F
  tags             JSON,
  suggested_terms  ARRAY<STRING>,
  is_active        BOOL    DEFAULT TRUE,
  run_id           STRING,
  ingested_at      TIMESTAMP,
  updated_at       TIMESTAMP
)
PARTITION BY DATE(ingested_at)
CLUSTER BY source_type, domain, sensitivity_level
OPTIONS (
  partition_expiration_days = 3650,      -- 10 year retention
  description = "Data catalog asset registry"
);

-- ============================================================
-- COLUMNS TABLE — Column-level metadata
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_catalog.columns` (
  column_id           STRING    NOT NULL,
  asset_id            STRING    NOT NULL,
  fqn                 STRING    NOT NULL,   -- e.g. teradata://schema.table.column
  asset_fqn           STRING,
  column_name         STRING,
  data_type           STRING,
  description         STRING,
  is_nullable         BOOL,
  pii_classification  STRING,              -- PII | SENSITIVE | INTERNAL | PUBLIC
  pii_category        STRING,              -- SSN | EMAIL | PHONE | NAME | etc.
  sensitivity_level   STRING,
  suggested_terms     ARRAY<STRING>,
  quality_score       FLOAT64,
  quality_grade       STRING,
  null_count          INT64,
  distinct_count      INT64,
  min_value           STRING,
  max_value           STRING,
  avg_value           FLOAT64,
  sample_values       ARRAY<STRING>,
  ingested_at         TIMESTAMP
)
PARTITION BY DATE(ingested_at)
CLUSTER BY asset_fqn, pii_classification
OPTIONS (
  description = "Column-level metadata for all catalog assets"
);

-- ============================================================
-- AUDIT LOG TABLE — Immutable audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_catalog.audit_log` (
  audit_id       STRING    NOT NULL,
  timestamp      TIMESTAMP NOT NULL,
  event_type     STRING    NOT NULL,     -- READ | WRITE | DELETE | LOGIN | etc.
  user_id        STRING,
  user_email     STRING,
  user_role      STRING,
  source_ip      STRING,
  service        STRING,
  resource_type  STRING,               -- ASSET | COLUMN | TERM | USER | SOURCE
  resource_id    STRING,
  resource_fqn   STRING,
  action         STRING,
  outcome        STRING,               -- SUCCESS | FAILURE | DENIED
  request_id     STRING,
  session_id     STRING,
  changes        JSON,                 -- before/after for write events
  metadata       JSON
)
PARTITION BY DATE(timestamp)
CLUSTER BY event_type, user_id, outcome
OPTIONS (
  partition_expiration_days = 2555,    -- 7 year retention for compliance
  description = "Immutable audit log for all catalog operations"
);

-- ============================================================
-- DATA LINEAGE TABLE — Asset-to-asset relationships
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_catalog.lineage` (
  lineage_id      STRING    NOT NULL,
  source_fqn      STRING    NOT NULL,
  target_fqn      STRING    NOT NULL,
  relationship    STRING,              -- DERIVED_FROM | COPY_OF | JOINS_WITH | etc.
  transformation  STRING,             -- SQL / ETL job description
  pipeline_id     STRING,
  run_id          STRING,
  created_at      TIMESTAMP,
  created_by      STRING,
  is_active       BOOL DEFAULT TRUE
)
PARTITION BY DATE(created_at)
CLUSTER BY source_fqn, target_fqn
OPTIONS (
  description = "Data lineage graph for all catalog assets"
);

-- ============================================================
-- TERM ASSIGNMENTS TABLE — Glossary term ↔ asset mapping
-- ============================================================
CREATE TABLE IF NOT EXISTS `data_catalog.term_assignments` (
  assignment_id  STRING    NOT NULL,
  term_id        STRING    NOT NULL,
  term_name      STRING,
  asset_fqn      STRING    NOT NULL,
  asset_type     STRING,              -- TABLE | COLUMN | SCHEMA
  confidence     FLOAT64,            -- 0.0–1.0
  assigned_by    STRING,
  assigned_at    TIMESTAMP,
  is_active      BOOL DEFAULT TRUE
)
PARTITION BY DATE(assigned_at)
CLUSTER BY term_id, asset_fqn
OPTIONS (
  description = "Business glossary term assignments to catalog assets"
);

-- ============================================================
-- USEFUL VIEWS
-- ============================================================

-- PII Dashboard view
CREATE OR REPLACE VIEW `data_catalog.v_pii_assets` AS
SELECT
  a.fqn            AS asset_fqn,
  a.schema_name,
  a.table_name,
  a.source_type,
  a.sensitivity_level AS table_sensitivity,
  c.column_name,
  c.pii_classification,
  c.pii_category,
  c.sensitivity_level AS column_sensitivity,
  a.data_owner,
  a.data_steward
FROM `data_catalog.assets` a
JOIN `data_catalog.columns` c ON a.asset_id = c.asset_id
WHERE c.pii_classification IN ('PII', 'SENSITIVE')
  AND a.is_active = TRUE;

-- Data quality summary view
CREATE OR REPLACE VIEW `data_catalog.v_quality_summary` AS
SELECT
  source_type,
  domain,
  COUNT(*)                            AS total_assets,
  AVG(quality_score)                  AS avg_quality_score,
  COUNTIF(quality_grade = 'A')        AS grade_a_count,
  COUNTIF(quality_grade = 'B')        AS grade_b_count,
  COUNTIF(quality_grade = 'C')        AS grade_c_count,
  COUNTIF(quality_grade IN ('D','F')) AS grade_df_count
FROM `data_catalog.assets`
WHERE is_active = TRUE
GROUP BY source_type, domain
ORDER BY avg_quality_score DESC;

-- Recent audit activity
CREATE OR REPLACE VIEW `data_catalog.v_recent_audit` AS
SELECT *
FROM `data_catalog.audit_log`
WHERE DATE(timestamp) = CURRENT_DATE()
ORDER BY timestamp DESC;
