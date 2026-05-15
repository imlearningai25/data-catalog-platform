/**
 * Catalog Browse — Search and explore all catalog assets.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, Shield, Database, BarChart2, ChevronRight, AlertTriangle } from 'lucide-react';
import { catalogApi } from '../services/api';
import type { Asset, SensitivityLevel } from '../types';

const SENSITIVITY_CONFIG: Record<SensitivityLevel, { label: string; color: string; bg: string }> = {
  PUBLIC:       { label: 'Public',       color: 'text-green-700',  bg: 'bg-green-50 border-green-200' },
  INTERNAL:     { label: 'Internal',     color: 'text-blue-700',   bg: 'bg-blue-50 border-blue-200' },
  CONFIDENTIAL: { label: 'Confidential', color: 'text-amber-700',  bg: 'bg-amber-50 border-amber-200' },
  RESTRICTED:   { label: 'Restricted',   color: 'text-red-700',    bg: 'bg-red-50 border-red-200' },
};

const GRADE_COLOR: Record<string, string> = {
  A: 'bg-green-100 text-green-700', B: 'bg-lime-100 text-lime-700',
  C: 'bg-amber-100 text-amber-700', D: 'bg-orange-100 text-orange-700',
  F: 'bg-red-100 text-red-700',
};

function AssetCard({ asset }: { asset: Asset }) {
  const navigate = useNavigate();
  const sens = SENSITIVITY_CONFIG[asset.sensitivity_level] ?? SENSITIVITY_CONFIG.INTERNAL;

  return (
    <div
      onClick={() => navigate(`/catalog/${encodeURIComponent(asset.fqn)}`)}
      className="bg-white border border-gray-200 rounded-xl p-5 hover:border-indigo-300 hover:shadow-sm cursor-pointer transition-all group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Database size={15} className="text-indigo-500 flex-shrink-0" />
            <span className="text-xs text-gray-400 truncate">{asset.source_type} · {asset.schema_name}</span>
          </div>
          <h3 className="font-semibold text-gray-900 group-hover:text-indigo-600 transition-colors">
            {asset.table_name}
          </h3>
          <p className="text-sm text-gray-500 mt-1 line-clamp-2">{asset.description || 'No description available.'}</p>
        </div>
        <ChevronRight size={16} className="text-gray-300 group-hover:text-indigo-400 flex-shrink-0 mt-1" />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {/* Sensitivity badge */}
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full border ${sens.bg} ${sens.color}`}>
          <Shield size={11} />
          {sens.label}
        </span>

        {/* Quality grade */}
        {asset.quality_grade && (
          <span className={`text-xs font-bold px-2 py-1 rounded-full ${GRADE_COLOR[asset.quality_grade]}`}>
            Grade {asset.quality_grade}
          </span>
        )}

        {/* Domain */}
        {asset.domain && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full capitalize">
            {asset.domain}
          </span>
        )}

        {/* Row count */}
        {asset.row_count != null && (
          <span className="text-xs text-gray-400 ml-auto">
            {asset.row_count.toLocaleString()} rows
          </span>
        )}
      </div>
    </div>
  );
}

export default function CatalogBrowse() {
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [sensitivity, setSensitivity] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['catalog', 'assets', query, domain, sensitivity, sourceType, page],
    queryFn: () => catalogApi.searchAssets({
      q: query || undefined,
      domain: domain || undefined,
      sensitivity: sensitivity || undefined,
      source_type: sourceType || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    }),
    placeholderData: (prev) => prev,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Data Catalog</h1>
        <p className="text-gray-500 text-sm mt-1">
          Browse and search {data?.total?.toLocaleString() ?? '...'} assets across all connected sources
        </p>
      </div>

      {/* Search & filters */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-64">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(0); }}
              placeholder="Search tables, schemas, descriptions..."
              className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <select
            value={domain}
            onChange={(e) => { setDomain(e.target.value); setPage(0); }}
            className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="">All Domains</option>
            {['finance', 'customer', 'hr', 'operations', 'product', 'security'].map(d => (
              <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
            ))}
          </select>

          <select
            value={sensitivity}
            onChange={(e) => { setSensitivity(e.target.value); setPage(0); }}
            className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="">All Sensitivity</option>
            {['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <select
            value={sourceType}
            onChange={(e) => { setSourceType(e.target.value); setPage(0); }}
            className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="">All Sources</option>
            {['teradata', 'mssql', 'bigquery', 'postgresql'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Results */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white border border-gray-200 rounded-xl p-5 animate-pulse h-36" />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-xl p-4">
          <AlertTriangle size={18} />
          <span className="text-sm">Failed to load catalog assets. Check API Gateway connectivity.</span>
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {data.assets.map(asset => (
              <AssetCard key={asset.asset_id} asset={asset} />
            ))}
          </div>

          {data.assets.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <Database size={40} className="mx-auto mb-3 opacity-30" />
              <p>No assets found matching your filters.</p>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)} of {data.total.toLocaleString()}
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}
                  className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50"
                >
                  Previous
                </button>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}
                  className="px-4 py-2 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
