// ============================================================
// Type definitions for the Data Catalog Frontend
// ============================================================

export type SensitivityLevel = 'PUBLIC' | 'INTERNAL' | 'CONFIDENTIAL' | 'RESTRICTED';
export type QualityGrade = 'A' | 'B' | 'C' | 'D' | 'F';
export type UserRole = 'viewer' | 'data_analyst' | 'data_steward' | 'admin';
export type PIIClassification = 'PII' | 'SENSITIVE' | 'INTERNAL' | 'PUBLIC';
export type SourceType = 'teradata' | 'mssql' | 'bigquery' | 'postgresql' | 'mysql' | 'snowflake';

export interface DataQualityScore {
  completeness: number;
  uniqueness: number;
  validity: number;
  consistency: number;
  overall: number;
  grade: QualityGrade;
}

export interface Column {
  column_id: string;
  column_name: string;
  data_type: string;
  description?: string;
  is_nullable: boolean;
  pii_classification?: PIIClassification;
  pii_category?: string;
  sensitivity_level: SensitivityLevel;
  suggested_terms: string[];
  quality_score?: number;
  quality_grade?: QualityGrade;
  null_count?: number;
  distinct_count?: number;
  min_value?: string;
  max_value?: string;
  avg_value?: number;
  sample_values?: string[];
  fqn: string;
}

export interface Asset {
  asset_id: string;
  fqn: string;
  source_id?: string;
  source_type: SourceType;
  database_name: string;
  schema_name: string;
  table_name: string;
  description?: string;
  domain?: string;
  data_owner?: string;
  data_steward?: string;
  sensitivity_level: SensitivityLevel;
  row_count?: number;
  size_bytes?: number;
  quality_score?: number;
  quality_grade?: QualityGrade;
  quality_completeness?: number;
  quality_uniqueness?: number;
  quality_validity?: number;
  quality_consistency?: number;
  tags: Record<string, string>;
  suggested_terms: string[];
  ingested_at: string;
  updated_at: string;
  columns?: Column[];
}

export interface GlossaryTerm {
  term_id: string;
  name: string;
  definition: string;
  domain?: string;
  synonyms: string[];
  abbreviations: string[];
  related_terms: string[];
  owner?: string;
  steward?: string;
  status: 'DRAFT' | 'ACTIVE' | 'DEPRECATED';
  examples: string[];
  created_at: string;
  updated_at: string;
  tags: Record<string, string>;
}

export interface LineageEdge {
  lineage_id: string;
  source_fqn: string;
  target_fqn: string;
  source_platform: string;
  target_platform: string;
  relationship: string;
  transformation_sql?: string;
  pipeline_id?: string;
  created_at: string;
  created_by: string;
}

export interface DataSource {
  source_id: string;
  source_type: SourceType;
  host: string;
  database: string;
  is_active?: boolean;
}

export interface User {
  user_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  department?: string;
  last_login?: string;
  is_active: boolean;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  role: UserRole | null;
}

export interface AuditEvent {
  audit_id: string;
  timestamp: string;
  event_type: string;
  user_email?: string;
  user_role?: string;
  resource_fqn?: string;
  resource_type?: string;
  action?: string;
  outcome: 'SUCCESS' | 'FAILURE' | 'DENIED';
  source_ip?: string;
}

export interface SearchFilters {
  query?: string;
  domain?: string;
  sensitivity?: SensitivityLevel;
  source_type?: SourceType;
  quality_grade?: QualityGrade;
}

export interface PaginatedResponse<T> {
  total: number;
  items: T[];
}

export interface CatalogStats {
  total_assets: number;
  total_pii_assets: number;
  avg_quality_score: number;
  assets_by_domain: Record<string, number>;
  assets_by_sensitivity: Record<SensitivityLevel, number>;
  assets_by_source: Record<SourceType, number>;
}
