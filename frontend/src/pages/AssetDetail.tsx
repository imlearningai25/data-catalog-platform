/**
 * Asset Detail — Full metadata view for a catalog asset.
 * Shows schema, columns (with PII flags), quality scores, lineage, and terms.
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft, Shield, Database, BarChart2, BookOpen,
  GitBranch, Tag, AlertTriangle, CheckCircle, Edit3, Save
} from 'lucide-react';
import { catalogApi, lineageApi } from '../services/api';
import { useAuthStore } from '../store/authStore';
import type { Column, SensitivityLevel } from '../types';

const SENSITIVITY_CONFIG: Record<SensitivityLevel, { color: string; bg: string; border: string }> = {
  PUBLIC:       { color: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-200' },
  INTERNAL:     { color: 'text-blue-700',   bg: 'bg-blue-50',   border: 'border-blue-200' },
  CONFIDENTIAL: { color: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-200' },
  RESTRICTED:   { color: 'text-red-700',    bg: 'bg-red-50',    border: 'border-red-200' },
};

const GRADE_BG: Record<string, string> = {
  A: 'bg-green-500', B: 'bg-lime-500', C: 'bg-amber-500', D: 'bg-orange-500', F: 'bg-red-500',
};

function QualityBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? 'bg-green-500' : pct >= 70 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-600 mb-1">
        <span>{label}</span><span className="font-medium">{pct}%</span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div className={`h-2 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ColumnRow({ col, rowCount }: { col: Column; rowCount?: number }) {
  const { role } = useAuthStore();
  const sens = SENSITIVITY_CONFIG[col.sensitivity_level] ?? SENSITIVITY_CONFIG.INTERNAL;
  const canSeePii = role === 'admin' || role === 'data_steward';
  const nullPct = (col.null_count != null && rowCount)
    ? Math.round((col.null_count / rowCount) * 100)
    : null;

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3">
        <div>
          <span className="font-mono text-sm text-gray-800">{col.column_name}</span>
          {col.sample_values && col.sample_values.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {col.sample_values.slice(0, 3).map((v, i) => (
                <span key={i} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-mono truncate max-w-24">
                  {v}
                </span>
              ))}
            </div>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
          {col.data_type}
        </span>
      </td>
      <td className="px-4 py-3 max-w-48">
        <span className="text-xs text-gray-500 line-clamp-2">{col.description || '—'}</span>
      </td>
      <td className="px-4 py-3">
        <div className="space-y-0.5 text-xs text-gray-500 font-mono">
          {nullPct !== null && (
            <div title="Null %">{nullPct}% null</div>
          )}
          {col.distinct_count != null && (
            <div title="Distinct values">{col.distinct_count.toLocaleString()} distinct</div>
          )}
          {col.min_value != null && (
            <div title="Min / Max" className="truncate max-w-28">
              {col.min_value} – {col.max_value}
            </div>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        {col.pii_classification && canSeePii ? (
          <div className="flex flex-col gap-1">
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${sens.bg} ${sens.color} ${sens.border}`}>
              {col.pii_classification}
            </span>
            {col.pii_category && (
              <span className="text-xs text-gray-400">{col.pii_category}</span>
            )}
          </div>
        ) : col.pii_classification ? (
          <span className="text-xs text-gray-400">🔒 Restricted</span>
        ) : (
          <span className="text-xs text-gray-300">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {col.quality_grade ? (
          <span className={`text-white text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center ${GRADE_BG[col.quality_grade]}`}>
            {col.quality_grade}
          </span>
        ) : '—'}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {col.suggested_terms.slice(0, 3).map(t => (
            <span key={t} className="text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full border border-indigo-100">
              {t}
            </span>
          ))}
        </div>
      </td>
    </tr>
  );
}

export default function AssetDetail() {
  const { fqn } = useParams<{ fqn: string }>();
  const navigate = useNavigate();
  const { role } = useAuthStore();
  const decodedFqn = decodeURIComponent(fqn ?? '');

  const [activeTab, setActiveTab] = useState<'columns' | 'quality' | 'lineage' | 'terms'>('columns');

  const { data: asset, isLoading } = useQuery({
    queryKey: ['asset', decodedFqn],
    queryFn: () => catalogApi.getAsset(decodedFqn),
    enabled: !!decodedFqn,
  });

  const { data: lineageData } = useQuery({
    queryKey: ['lineage', decodedFqn],
    queryFn: () => lineageApi.getLineage(decodedFqn, 'both', 2),
    enabled: !!decodedFqn && activeTab === 'lineage',
  });

  const sens = SENSITIVITY_CONFIG[asset?.sensitivity_level as SensitivityLevel] ?? SENSITIVITY_CONFIG.INTERNAL;

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!asset) return (
    <div className="text-center py-16 text-gray-400">Asset not found</div>
  );

  const tabs = [
    { id: 'columns', label: `Columns (${asset.columns?.length ?? 0})`, icon: Database },
    { id: 'quality', label: 'Quality', icon: BarChart2 },
    { id: 'lineage', label: 'Lineage', icon: GitBranch },
    { id: 'terms', label: 'Business Terms', icon: BookOpen },
  ] as const;

  return (
    <div className="space-y-5">
      {/* Back + header */}
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 mb-4 transition-colors"
        >
          <ArrowLeft size={16} /> Back to Catalog
        </button>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-gray-400 font-mono">{asset.source_type} · {asset.schema_name}</span>
              </div>
              <h1 className="text-2xl font-bold text-gray-900">{asset.table_name}</h1>
              <p className="text-gray-500 text-sm mt-1 max-w-2xl">{asset.description || 'No description.'}</p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className={`text-sm font-medium px-3 py-1.5 rounded-full border ${sens.bg} ${sens.color} ${sens.border}`}>
                <Shield size={13} className="inline mr-1.5" />
                {asset.sensitivity_level}
              </span>
              {asset.quality_grade && (
                <span className={`text-white text-sm font-bold px-3 py-1.5 rounded-full ${GRADE_BG[asset.quality_grade]}`}>
                  Quality: {asset.quality_grade} ({Math.round((asset.quality_score ?? 0) * 100)}%)
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5 pt-5 border-t border-gray-100">
            {[
              { label: 'Domain', value: asset.domain ?? 'Unclassified' },
              { label: 'Data Owner', value: asset.data_owner ?? 'Unassigned' },
              { label: 'Data Steward', value: asset.data_steward ?? 'Unassigned' },
              { label: 'Row Count', value: asset.row_count?.toLocaleString() ?? 'Unknown' },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-xs text-gray-400 mb-0.5">{label}</div>
                <div className="text-sm font-medium text-gray-800">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === id ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            <Icon size={15} />{label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'columns' && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Column / Samples', 'Type', 'Description', 'Profile', 'Classification', 'Quality', 'Terms'].map(h => (
                  <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {asset.columns?.map(col => (
                <ColumnRow key={col.fqn} col={col} rowCount={asset.row_count} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'quality' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="font-semibold text-gray-800 mb-1">Quality Dimensions</h3>
            {asset.quality_completeness == null ? (
              <p className="text-xs text-gray-400 mb-4">Run a hydration job to compute quality scores.</p>
            ) : (
              <p className="text-xs text-gray-400 mb-4">Table-level averages across all columns.</p>
            )}
            <div className="space-y-4">
              <QualityBar value={asset.quality_completeness ?? 0} label="Completeness" />
              <QualityBar value={asset.quality_uniqueness ?? 0} label="Uniqueness" />
              <QualityBar value={asset.quality_validity ?? 0} label="Validity" />
              <QualityBar value={asset.quality_consistency ?? 0} label="Consistency" />
            </div>
          </div>
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Column Health Summary</h3>
            <div className="space-y-3">
              {['A', 'B', 'C', 'D', 'F'].map(grade => {
                const count = asset.columns?.filter(c => c.quality_grade === grade).length ?? 0;
                return (
                  <div key={grade} className="flex items-center gap-3">
                    <span className={`text-white text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center ${GRADE_BG[grade]}`}>{grade}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${GRADE_BG[grade]} opacity-70`}
                        style={{ width: `${(count / (asset.columns?.length || 1)) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-8 text-right">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'lineage' && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Data Lineage ({lineageData?.edge_count ?? 0} edges)</h3>
          {lineageData?.edges?.length === 0 && (
            <div className="text-center py-8 text-gray-400">No lineage recorded for this asset.</div>
          )}
          <div className="space-y-3">
            {lineageData?.edges?.map((edge: any) => (
              <div key={edge.lineage_id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg text-sm">
                <span className="font-mono text-xs text-gray-600 truncate max-w-xs">{edge.source_fqn}</span>
                <ArrowLeft size={14} className="text-indigo-400 flex-shrink-0 rotate-180" />
                <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full">{edge.relationship}</span>
                <span className="font-mono text-xs text-gray-600 truncate max-w-xs">{edge.target_fqn}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'terms' && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <h3 className="font-semibold text-gray-800 mb-4">Suggested Business Terms</h3>
          <div className="flex flex-wrap gap-2">
            {asset.suggested_terms.map(term => (
              <span key={term} className="bg-indigo-50 text-indigo-700 border border-indigo-200 text-sm px-3 py-1.5 rounded-full font-medium">
                <Tag size={12} className="inline mr-1.5" />{term}
              </span>
            ))}
            {asset.suggested_terms.length === 0 && (
              <p className="text-gray-400 text-sm">No terms suggested yet.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
