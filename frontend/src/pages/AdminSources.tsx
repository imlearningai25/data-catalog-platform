import { useState } from 'react';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import {
  Database, Plus, Play, RefreshCw, CheckCircle, XCircle,
  Clock, AlertCircle, X, Loader2, Zap, Trash2, Settings2, Pencil, BarChart2,
} from 'lucide-react';
import { connectorApi } from '../services/api';

// ── Field & source-type definitions ──────────────────────────────────────────

interface FieldDef {
  key: string;
  label: string;
  type: 'text' | 'password' | 'number';
  placeholder?: string;
  required?: boolean;
  hint?: string;
  col?: 'full' | 'half';   // layout hint; default 'half'
}

type Params = Record<string, string | number>;

interface SourceTypeDef {
  value: string;
  label: string;
  badge: string;      // tailwind classes for the table badge
  ring: string;       // selection ring class
  fields: FieldDef[];
  defaults: Params;
  toPayload: (p: Params) => {
    host: string; port: number; database: string;
    username: string; password: string; extra_params: Record<string, any>;
  };
}

const SQL_PAYLOAD = (p: Params) => ({
  host:         String(p.host ?? ''),
  port:         Number(p.port ?? 0),
  database:     String(p.database ?? ''),
  username:     String(p.username ?? ''),
  password:     String(p.password ?? ''),
  extra_params: {},
});

const SOURCE_TYPES: SourceTypeDef[] = [
  {
    value: 'postgresql', label: 'PostgreSQL',
    badge: 'bg-green-100 text-green-700', ring: 'ring-green-500',
    defaults: { host: '', port: 5432, database: '', username: '', password: '' },
    fields: [
      { key: 'host',     label: 'Host',     type: 'text',   placeholder: 'db.example.com', required: true },
      { key: 'port',     label: 'Port',     type: 'number', placeholder: '5432', col: 'half' },
      { key: 'database', label: 'Database', type: 'text',   placeholder: 'my_database',    required: true },
      { key: 'username', label: 'Username', type: 'text',   placeholder: 'readonly_user',  required: true, col: 'half' },
      { key: 'password', label: 'Password', type: 'password', col: 'half' },
    ],
    toPayload: SQL_PAYLOAD,
  },
  {
    value: 'mysql', label: 'MySQL',
    badge: 'bg-blue-100 text-blue-700', ring: 'ring-blue-500',
    defaults: { host: '', port: 3306, database: '', username: '', password: '' },
    fields: [
      { key: 'host',     label: 'Host',     type: 'text',   placeholder: 'db.example.com', required: true },
      { key: 'port',     label: 'Port',     type: 'number', placeholder: '3306', col: 'half' },
      { key: 'database', label: 'Database', type: 'text',   placeholder: 'my_database',    required: true },
      { key: 'username', label: 'Username', type: 'text',   placeholder: 'readonly_user',  required: true, col: 'half' },
      { key: 'password', label: 'Password', type: 'password', col: 'half' },
    ],
    toPayload: SQL_PAYLOAD,
  },
  {
    value: 'mssql', label: 'SQL Server',
    badge: 'bg-purple-100 text-purple-700', ring: 'ring-purple-500',
    defaults: { host: '', port: 1433, database: '', username: '', password: '' },
    fields: [
      { key: 'host',     label: 'Host',              type: 'text',   placeholder: 'sqlserver.example.com', required: true },
      { key: 'port',     label: 'Port',              type: 'number', placeholder: '1433', col: 'half' },
      { key: 'database', label: 'Database',          type: 'text',   placeholder: 'AdventureWorks',        required: true },
      { key: 'username', label: 'Username',          type: 'text',   placeholder: 'sa',                    required: true, col: 'half' },
      { key: 'password', label: 'Password',          type: 'password', col: 'half' },
    ],
    toPayload: SQL_PAYLOAD,
  },
  {
    value: 'oracle', label: 'Oracle',
    badge: 'bg-red-100 text-red-700', ring: 'ring-red-500',
    defaults: { host: '', port: 1521, service_name: '', username: '', password: '' },
    fields: [
      { key: 'host',         label: 'Host',         type: 'text',   placeholder: 'oracle.example.com', required: true },
      { key: 'port',         label: 'Port',         type: 'number', placeholder: '1521', col: 'half' },
      { key: 'service_name', label: 'Service Name', type: 'text',   placeholder: 'ORCL',               required: true, hint: 'Oracle service name (e.g. ORCL, XE)' },
      { key: 'username',     label: 'Username',     type: 'text',   placeholder: 'readonly',            required: true, col: 'half' },
      { key: 'password',     label: 'Password',     type: 'password', col: 'half' },
    ],
    toPayload: (p) => ({ ...SQL_PAYLOAD(p), database: String(p.service_name ?? ''), extra_params: {} }),
  },
  {
    value: 'teradata', label: 'Teradata',
    badge: 'bg-amber-100 text-amber-700', ring: 'ring-amber-500',
    defaults: { host: '', port: 1025, database: '', username: '', password: '' },
    fields: [
      { key: 'host',     label: 'Host',     type: 'text',   placeholder: 'tdserver.example.com', required: true },
      { key: 'port',     label: 'Port',     type: 'number', placeholder: '1025', col: 'half' },
      { key: 'database', label: 'Database', type: 'text',   placeholder: 'my_database',          required: true },
      { key: 'username', label: 'Username', type: 'text',   placeholder: 'tduser',               required: true, col: 'half' },
      { key: 'password', label: 'Password', type: 'password', col: 'half' },
    ],
    toPayload: SQL_PAYLOAD,
  },
  {
    value: 'snowflake', label: 'Snowflake',
    badge: 'bg-sky-100 text-sky-700', ring: 'ring-sky-500',
    defaults: { account: '', warehouse: '', database: '', db_schema: 'PUBLIC', username: '', password: '' },
    fields: [
      { key: 'account',   label: 'Account Identifier', type: 'text', placeholder: 'xy12345.us-east-1', required: true, hint: 'Found in your Snowflake URL before .snowflakecomputing.com', col: 'full' },
      { key: 'warehouse', label: 'Warehouse',           type: 'text', placeholder: 'COMPUTE_WH',        required: true },
      { key: 'database',  label: 'Database',            type: 'text', placeholder: 'MY_DB',             required: true },
      { key: 'db_schema', label: 'Schema',              type: 'text', placeholder: 'PUBLIC' },
      { key: 'username',  label: 'Username',            type: 'text', placeholder: 'jane.doe@corp.com', required: true },
      { key: 'password',  label: 'Password',            type: 'password', required: true },
    ],
    toPayload: (p) => ({
      host:         `${p.account}.snowflakecomputing.com`,
      port:         443,
      database:     String(p.database ?? ''),
      username:     String(p.username ?? ''),
      password:     String(p.password ?? ''),
      extra_params: { warehouse: p.warehouse, schema: p.db_schema || 'PUBLIC' },
    }),
  },
  {
    value: 'bigquery', label: 'BigQuery',
    badge: 'bg-cyan-100 text-cyan-700', ring: 'ring-cyan-500',
    defaults: { project_id: '', dataset: '', key_path: '' },
    fields: [
      { key: 'project_id', label: 'GCP Project ID',          type: 'text', placeholder: 'my-gcp-project', required: true },
      { key: 'dataset',    label: 'Dataset',                  type: 'text', placeholder: 'data_warehouse',  required: true },
      { key: 'key_path',   label: 'Service Account Key Path', type: 'text', placeholder: '/secrets/gcp-key.json', col: 'full', hint: 'Mount the JSON key file into the connector container' },
    ],
    toPayload: (p) => ({
      host:         String(p.project_id ?? ''),
      port:         443,
      database:     String(p.dataset ?? ''),
      username:     'service_account',
      password:     '',
      extra_params: { credentials_path: p.key_path },
    }),
  },
  {
    value: 'sqlite', label: 'SQLite (POC)',
    badge: 'bg-gray-100 text-gray-600', ring: 'ring-gray-400',
    defaults: { file_path: '/poc-data/catalog.db', db_schema: 'main' },
    fields: [
      { key: 'file_path',  label: 'File path (inside container)', type: 'text', placeholder: '/poc-data/catalog.db', required: true, col: 'full' },
      { key: 'db_schema',  label: 'Schema',                       type: 'text', placeholder: 'main' },
    ],
    toPayload: (p) => ({
      host:         String(p.file_path ?? ''),
      port:         0,
      database:     String(p.db_schema || 'main'),
      username:     '',
      password:     '',
      extra_params: {},
    }),
  },
];

const TYPE_BADGE: Record<string, string> = Object.fromEntries(
  SOURCE_TYPES.map(t => [t.value, t.badge])
);

const JOB_STATUS: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  queued:    { icon: <Clock size={13} />,                                    color: 'text-amber-500 bg-amber-50',  label: 'Queued'    },
  running:   { icon: <Loader2 size={13} className="animate-spin" />,         color: 'text-blue-500 bg-blue-50',   label: 'Running'   },
  completed: { icon: <CheckCircle size={13} />,                              color: 'text-green-600 bg-green-50', label: 'Completed' },
  failed:    { icon: <XCircle size={13} />,                                  color: 'text-red-600 bg-red-50',     label: 'Failed'    },
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function elapsed(ts: number) {
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function inputClass(full = false) {
  return `${full ? 'col-span-2' : ''} w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400`;
}

// ── KV-pair editor (Custom source) ───────────────────────────────────────────

interface KVPair { key: string; value: string }

function KVEditor({ pairs, onChange }: { pairs: KVPair[]; onChange: (p: KVPair[]) => void }) {
  const set = (i: number, field: 'key' | 'value', v: string) => {
    const next = pairs.map((p, j) => j === i ? { ...p, [field]: v } : p);
    onChange(next);
  };
  const add    = () => onChange([...pairs, { key: '', value: '' }]);
  const remove = (i: number) => onChange(pairs.filter((_, j) => j !== i));

  return (
    <div className="space-y-2">
      {pairs.map((p, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            value={p.key}
            onChange={e => set(i, 'key', e.target.value)}
            placeholder="param_name"
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <input
            value={p.value}
            onChange={e => set(i, 'value', e.target.value)}
            placeholder="value"
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <button type="button" onClick={() => remove(i)} className="p-1.5 rounded hover:bg-red-50 text-gray-300 hover:text-red-500">
            <Trash2 size={13} />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1 pt-0.5"
      >
        <Plus size={12} /> Add parameter
      </button>
    </div>
  );
}

// ── Register slide-over panel ─────────────────────────────────────────────────

function RegisterPanel({ onClose, onRegistered }: {
  onClose: () => void;
  onRegistered: (sourceId: string) => void;
}) {
  const [selectedType, setSelectedType] = useState<string>('postgresql');
  const [isCustom, setIsCustom]         = useState(false);
  const [params, setParams]             = useState<Params>({ ...SOURCE_TYPES[0].defaults });

  // Custom-only state
  const [customTypeName, setCustomTypeName] = useState('');
  const [customDesc, setCustomDesc]         = useState('');
  const [kvPairs, setKvPairs]               = useState<KVPair[]>([{ key: '', value: '' }]);

  // Shared filters + profiling
  const [schemaFilter, setSchemaFilter]       = useState('');
  const [tableFilter, setTableFilter]         = useState('');
  const [enableProfiling, setEnableProfiling] = useState(true);
  const [profilePct, setProfilePct]           = useState(10);

  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting]       = useState(false);

  const qc = useQueryClient();

  const typeDef = SOURCE_TYPES.find(t => t.value === selectedType) ?? SOURCE_TYPES[0];

  function selectType(value: string) {
    const def = SOURCE_TYPES.find(t => t.value === value);
    if (!def) return;
    setSelectedType(value);
    setIsCustom(false);
    setParams({ ...def.defaults });
    setTestResult(null);
  }

  function selectCustom() {
    setIsCustom(true);
    setTestResult(null);
  }

  const setParam = (key: string, value: string | number) => {
    setParams(p => ({ ...p, [key]: value }));
    setTestResult(null);
  };

  function buildApiPayload() {
    if (isCustom) {
      const extra = Object.fromEntries(
        kvPairs.filter(p => p.key).map(p => [p.key, p.value])
      );
      return {
        source_type: customTypeName || 'custom',
        host: extra.host ?? '',
        port: Number(extra.port ?? 0),
        database: extra.database ?? '',
        username: extra.username ?? '',
        password: extra.password ?? '',
        extra_params: extra,
      };
    }
    const { host, port, database, username, password, extra_params } = typeDef.toPayload(params);
    return {
      source_type: selectedType,
      host, port, database, username, password, extra_params,
    };
  }

  const registerMut = useMutation({
    mutationFn: () => connectorApi.registerSource({
      ...buildApiPayload(),
      schema_filter: schemaFilter ? schemaFilter.split(',').map(s => s.trim()) : [],
      table_filter:  tableFilter  ? tableFilter.split(',').map(s => s.trim())  : [],
      enable_profiling: enableProfiling,
      profile_sample_pct: profilePct,
    } as any),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['sources'] });
      onRegistered(data.source_id);
    },
  });

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const { source_type, host, port, database, username, password, extra_params } = buildApiPayload();
    try {
      const res = await connectorApi.testConnection({ source_type, host, port, database, username, password, extra_params } as any);
      setTestResult(res as any);
    } catch {
      setTestResult({ success: false, message: 'Request failed — check service connectivity' });
    } finally {
      setTesting(false);
    }
  };

  // Determine if form is submittable
  const canTest = isCustom
    ? !!customTypeName
    : typeDef.fields.filter(f => f.required).every(f => !!params[f.key]);
  const canSubmit = canTest && !registerMut.isPending;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      <div className="relative w-full max-w-lg bg-white shadow-2xl flex flex-col overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Register Data Source</h2>
            <p className="text-xs text-gray-500 mt-0.5">Connect a database and ingest its schema</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 text-gray-400">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 px-6 py-5 space-y-6">

          {/* ── Source type grid ── */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Source type</label>
            <div className="grid grid-cols-3 gap-2">
              {SOURCE_TYPES.map(t => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => selectType(t.value)}
                  className={`px-3 py-2 rounded-lg border text-sm text-left transition-all ${
                    !isCustom && selectedType === t.value
                      ? `border-transparent ring-2 ${t.ring} bg-white shadow-sm font-medium text-gray-900`
                      : 'border-gray-200 hover:border-gray-300 text-gray-600 hover:text-gray-800'
                  }`}
                >
                  <span className={`inline-block text-xs font-semibold px-1.5 py-0.5 rounded mb-1 ${t.badge}`}>
                    {t.label}
                  </span>
                </button>
              ))}

              {/* Custom button */}
              <button
                type="button"
                onClick={selectCustom}
                className={`px-3 py-2 rounded-lg border-2 border-dashed text-sm text-left transition-all ${
                  isCustom
                    ? 'border-indigo-400 bg-indigo-50 text-indigo-700 shadow-sm'
                    : 'border-gray-300 hover:border-indigo-300 text-gray-400 hover:text-indigo-600'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <Settings2 size={13} />
                  <span className="text-xs font-semibold">Custom</span>
                </div>
                <p className="text-xs mt-0.5 leading-tight opacity-70">Bring your own connector</p>
              </button>
            </div>
          </div>

          {/* ── Dynamic connection fields ── */}
          {!isCustom && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Connection</p>
              <div className="grid grid-cols-2 gap-3">
                {typeDef.fields.map(f => (
                  <div key={f.key} className={f.col === 'full' ? 'col-span-2' : ''}>
                    <label className="block text-xs text-gray-600 mb-1">
                      {f.label}{f.required && <span className="text-red-400 ml-0.5">*</span>}
                    </label>
                    <input
                      type={f.type === 'number' ? 'number' : f.type}
                      value={params[f.key] ?? ''}
                      onChange={e => setParam(f.key, f.type === 'number' ? +e.target.value : e.target.value)}
                      placeholder={f.placeholder}
                      required={f.required}
                      className={inputClass(f.col === 'full')}
                    />
                    {f.hint && <p className="text-xs text-gray-400 mt-0.5">{f.hint}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Custom source fields ── */}
          {isCustom && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
                <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
                <span>Custom sources require a matching connector implementation in the backend. Use this to document or prototype a new integration.</span>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Source Identity</p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Source Type Name <span className="text-red-400">*</span></label>
                    <input
                      value={customTypeName}
                      onChange={e => setCustomTypeName(e.target.value)}
                      placeholder="e.g. mongodb, redis, s3-parquet"
                      className={inputClass(true)}
                    />
                    <p className="text-xs text-gray-400 mt-0.5">Must match the connector key registered in the backend</p>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Description</label>
                    <input
                      value={customDesc}
                      onChange={e => setCustomDesc(e.target.value)}
                      placeholder="What data does this source contain?"
                      className={inputClass(true)}
                    />
                  </div>
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Connection Parameters
                </p>
                <KVEditor pairs={kvPairs} onChange={setKvPairs} />
              </div>
            </div>
          )}

          {/* ── Filters ── */}
          {!isCustom && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                Filters <span className="normal-case font-normal text-gray-400">(optional)</span>
              </p>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Schema filter <span className="text-gray-400">comma-separated</span></label>
                  <input value={schemaFilter} onChange={e => setSchemaFilter(e.target.value)}
                    placeholder="public, analytics"
                    className={inputClass(true)} />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Table filter <span className="text-gray-400">comma-separated</span></label>
                  <input value={tableFilter} onChange={e => setTableFilter(e.target.value)}
                    placeholder="orders, customers"
                    className={inputClass(true)} />
                </div>
              </div>
            </div>
          )}

          {/* ── Profiling ── */}
          {!isCustom && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Profiling</p>
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input type="checkbox" checked={enableProfiling}
                  onChange={e => setEnableProfiling(e.target.checked)}
                  className="w-4 h-4 rounded accent-indigo-600" />
                <span className="text-sm text-gray-700">Enable column profiling</span>
              </label>
              {enableProfiling && (
                <div className="mt-3">
                  <label className="block text-xs text-gray-600 mb-1">
                    Sample percentage — <span className="font-semibold text-indigo-600">{profilePct}%</span>
                  </label>
                  <input type="range" min="1" max="100" value={profilePct}
                    onChange={e => setProfilePct(+e.target.value)}
                    className="w-full accent-indigo-600" />
                  <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                    <span>1% (faster)</span><span>100% (accurate)</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Feedback ── */}
          {testResult && (
            <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
              testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
            }`}>
              {testResult.success
                ? <CheckCircle size={15} className="flex-shrink-0 mt-0.5" />
                : <XCircle size={15} className="flex-shrink-0 mt-0.5" />}
              {testResult.message}
            </div>
          )}
          {registerMut.isError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-700 text-sm">
              <AlertCircle size={15} /> Registration failed — check service logs
            </div>
          )}
        </div>

        {/* ── Sticky footer ── */}
        <div className="sticky bottom-0 bg-white border-t border-gray-200 px-6 py-4 flex gap-3">
          {!isCustom && (
            <button
              type="button"
              onClick={handleTest}
              disabled={!canTest || testing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {testing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              Test
            </button>
          )}
          <button
            type="button"
            onClick={() => registerMut.mutate()}
            disabled={!canSubmit}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {registerMut.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Registering…</>
              : <><Plus size={14} /> Register source</>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit slide-over panel ─────────────────────────────────────────────────────

function EditPanel({ source, onClose }: { source: any; onClose: () => void }) {
  const qc = useQueryClient();
  const typeDef = SOURCE_TYPES.find(t => t.value === source.source_type);

  // Reverse-map the stored host/port/database/extra_params back to UI field keys
  function deriveParams(): Params {
    if (!typeDef) return {};
    const base: Params = {
      host:     source.host     ?? '',
      port:     source.port     ?? 0,
      database: source.database ?? '',
      username: source.username ?? '',
      password: '',                     // never pre-fill password
    };
    const extra = source.extra_params ?? {};

    // Snowflake: account is encoded into host as account.snowflakecomputing.com
    if (source.source_type === 'snowflake') {
      return {
        account:   String(source.host ?? '').replace('.snowflakecomputing.com', ''),
        warehouse: extra.warehouse ?? '',
        database:  source.database ?? '',
        db_schema: extra.schema ?? 'PUBLIC',
        username:  source.username ?? '',
        password:  '',
      };
    }
    // BigQuery: project_id stored in host, dataset in database, key_path in extra
    if (source.source_type === 'bigquery') {
      return { project_id: source.host ?? '', dataset: source.database ?? '', key_path: extra.credentials_path ?? '' };
    }
    // SQLite: file_path in host, schema in database
    if (source.source_type === 'sqlite') {
      return { file_path: source.host ?? '', db_schema: source.database ?? 'main' };
    }
    // Oracle: service_name stored in database
    if (source.source_type === 'oracle') {
      return { ...base, service_name: source.database ?? '' };
    }
    return base;
  }

  const [params, setParams]               = useState<Params>(deriveParams);
  const [schemaFilter, setSchemaFilter]   = useState((source.schema_filter ?? []).join(', '));
  const [tableFilter, setTableFilter]     = useState((source.table_filter  ?? []).join(', '));
  const [enableProfiling, setEnableProfiling] = useState(source.enable_profiling ?? true);
  const [profilePct, setProfilePct]       = useState(source.profile_sample_pct ?? 10);
  const [testResult, setTestResult]       = useState<{ success: boolean; message: string } | null>(null);
  const [testing, setTesting]             = useState(false);

  const setParam = (key: string, value: string | number) => {
    setParams(p => ({ ...p, [key]: value }));
    setTestResult(null);
  };

  const updateMut = useMutation({
    mutationFn: () => {
      const { host, port, database, username, password, extra_params } = typeDef!.toPayload(params);
      return connectorApi.updateSource(source.source_id, {
        host, port, database, username,
        ...(password ? { password } : {}),  // omit if blank → keep existing
        extra_params,
        schema_filter: schemaFilter ? schemaFilter.split(',').map((s: string) => s.trim()) : [],
        table_filter:  tableFilter  ? tableFilter.split(',').map((s: string) => s.trim())  : [],
        enable_profiling: enableProfiling,
        profile_sample_pct: profilePct,
      });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sources'] }); onClose(); },
  });

  const handleTest = async () => {
    if (!typeDef) return;
    setTesting(true); setTestResult(null);
    const { host, port, database, username, password, extra_params } = typeDef.toPayload(params);
    try {
      const res = await connectorApi.testConnection({
        source_type: source.source_type, host, port, database, username, password, extra_params,
      } as any);
      setTestResult(res as any);
    } catch {
      setTestResult({ success: false, message: 'Request failed — check service connectivity' });
    } finally { setTesting(false); }
  };

  const canTest   = typeDef?.fields.filter(f => f.required).every(f => !!params[f.key]) ?? false;
  const canSubmit = canTest && !updateMut.isPending;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-white shadow-2xl flex flex-col overflow-y-auto">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Edit Data Source</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${typeDef?.badge ?? 'bg-gray-100 text-gray-600'}`}>
                {source.source_type}
              </span>
              <span className="text-xs text-gray-400 font-mono">{source.source_id.slice(0, 8)}…</span>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 text-gray-400">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 px-6 py-5 space-y-6">

          {/* Connection fields (source type locked) */}
          {typeDef && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Connection</p>
              <div className="grid grid-cols-2 gap-3">
                {typeDef.fields.map(f => (
                  <div key={f.key} className={f.col === 'full' ? 'col-span-2' : ''}>
                    <label className="block text-xs text-gray-600 mb-1">
                      {f.label}
                      {f.required && <span className="text-red-400 ml-0.5">*</span>}
                      {f.type === 'password' && <span className="text-gray-400 ml-1">(leave blank to keep current)</span>}
                    </label>
                    <input
                      type={f.type === 'number' ? 'number' : f.type}
                      value={params[f.key] ?? ''}
                      onChange={e => setParam(f.key, f.type === 'number' ? +e.target.value : e.target.value)}
                      placeholder={f.placeholder}
                      className={inputClass(f.col === 'full')}
                    />
                    {f.hint && <p className="text-xs text-gray-400 mt-0.5">{f.hint}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Filters */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Filters <span className="normal-case font-normal text-gray-400">(optional)</span>
            </p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Schema filter <span className="text-gray-400">comma-separated</span></label>
                <input value={schemaFilter} onChange={e => setSchemaFilter(e.target.value)}
                  placeholder="public, analytics" className={inputClass(true)} />
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Table filter <span className="text-gray-400">comma-separated</span></label>
                <input value={tableFilter} onChange={e => setTableFilter(e.target.value)}
                  placeholder="orders, customers" className={inputClass(true)} />
              </div>
            </div>
          </div>

          {/* Profiling */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Profiling</p>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={enableProfiling}
                onChange={e => setEnableProfiling(e.target.checked)}
                className="w-4 h-4 rounded accent-indigo-600" />
              <span className="text-sm text-gray-700">Enable column profiling</span>
            </label>
            {enableProfiling && (
              <div className="mt-3">
                <label className="block text-xs text-gray-600 mb-1">
                  Sample percentage — <span className="font-semibold text-indigo-600">{profilePct}%</span>
                </label>
                <input type="range" min="1" max="100" value={profilePct}
                  onChange={e => setProfilePct(+e.target.value)}
                  className="w-full accent-indigo-600" />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>1% (faster)</span><span>100% (accurate)</span>
                </div>
              </div>
            )}
          </div>

          {/* Feedback */}
          {testResult && (
            <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
              testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
            }`}>
              {testResult.success
                ? <CheckCircle size={15} className="flex-shrink-0 mt-0.5" />
                : <XCircle size={15} className="flex-shrink-0 mt-0.5" />}
              {testResult.message}
            </div>
          )}
          {updateMut.isError && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-700 text-sm">
              <AlertCircle size={15} /> Update failed — check service logs
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-white border-t border-gray-200 px-6 py-4 flex gap-3">
          <button
            type="button"
            onClick={handleTest}
            disabled={!canTest || testing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {testing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            Test
          </button>
          <button
            type="button"
            onClick={() => updateMut.mutate()}
            disabled={!canSubmit}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {updateMut.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
              : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminSources() {
  const [showRegister, setShowRegister]   = useState(false);
  const [editingSource, setEditingSource] = useState<any | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<any | null>(null);
  const [lastRegistered, setLastRegistered] = useState<string | null>(null);
  const [hydratingId, setHydratingId]     = useState<string | null>(null);
  const qc = useQueryClient();

  const deleteMut = useMutation({
    mutationFn: (sourceId: string) => connectorApi.deleteSource(sourceId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sources'] }); setConfirmDelete(null); },
  });

  const { data: sources = [], isLoading: loadingSources } = useQuery({
    queryKey: ['sources'],
    queryFn: connectorApi.listSources,
    refetchInterval: 15_000,
  });

  const { data: jobs = [], isLoading: loadingJobs, isFetching: fetchingJobs } = useQuery({
    queryKey: ['jobs'],
    queryFn: connectorApi.listJobs,
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const hydrateMut = useMutation({
    mutationFn: (sourceId: string) => connectorApi.triggerHydration(sourceId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); setHydratingId(null); },
    onError:   () => setHydratingId(null),
  });

  const handleRegistered = (sourceId: string) => {
    setLastRegistered(sourceId);
    setShowRegister(false);
    qc.invalidateQueries({ queryKey: ['sources'] });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Data Sources</h1>
          <p className="text-gray-500 text-sm mt-0.5">Register databases and trigger schema hydration</p>
        </div>
        <button
          onClick={() => setShowRegister(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 shadow-sm"
        >
          <Plus size={16} /> Register source
        </button>
      </div>

      {/* Success banner */}
      {lastRegistered && (
        <div className="flex items-center justify-between p-4 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} />
            <span>Source registered — <code className="font-mono text-xs bg-green-100 px-1.5 py-0.5 rounded">{lastRegistered}</code></span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setHydratingId(lastRegistered); hydrateMut.mutate(lastRegistered); setLastRegistered(null); }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700"
            >
              <Play size={12} /> Run hydration now
            </button>
            <button onClick={() => setLastRegistered(null)} className="text-green-500 hover:text-green-700"><X size={14} /></button>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <Trash2 size={18} className="text-red-600" />
              </div>
              <h2 className="text-base font-bold text-gray-900">Delete source?</h2>
            </div>
            <p className="text-sm text-gray-500 mb-1">
              <span className={`text-xs font-semibold px-1.5 py-0.5 rounded mr-1 ${TYPE_BADGE[confirmDelete.source_type] ?? 'bg-gray-100 text-gray-600'}`}>
                {confirmDelete.source_type}
              </span>
              <span className="font-medium text-gray-800">{confirmDelete.host}</span>
              {' / '}{confirmDelete.database}
            </p>
            <p className="text-xs text-gray-400 mb-5">All associated hydration jobs will also be removed.</p>
            <div className="flex gap-3">
              <button
                onClick={() => deleteMut.mutate(confirmDelete.source_id)}
                disabled={deleteMut.isPending}
                className="flex-1 bg-red-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMut.isPending ? 'Deleting…' : 'Delete'}
              </button>
              <button onClick={() => setConfirmDelete(null)} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Sources table */}
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Registered Sources</h2>
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{(sources as any[]).length}</span>
        </div>

        {loadingSources && (
          <div className="flex items-center justify-center py-12 text-gray-400 gap-2">
            <Loader2 size={20} className="animate-spin" /> Loading…
          </div>
        )}

        {!loadingSources && (sources as any[]).length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
            <Database size={40} className="opacity-20" />
            <p className="font-medium">No sources registered yet</p>
            <p className="text-sm">Click "Register source" to connect your first database</p>
          </div>
        )}

        {(sources as any[]).length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
              <tr>
                <th className="text-left px-6 py-3">Type</th>
                <th className="text-left px-6 py-3">Host / Path</th>
                <th className="text-left px-6 py-3">Database</th>
                <th className="text-left px-6 py-3">Source ID</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(sources as any[]).map((s) => (
                <tr key={s.source_id} className="hover:bg-gray-50 group">
                  <td className="px-6 py-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${TYPE_BADGE[s.source_type] ?? 'bg-gray-100 text-gray-600'}`}>
                      {s.source_type}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-gray-700 font-mono text-xs">{s.host}</td>
                  <td className="px-6 py-3 text-gray-700">{s.database}</td>
                  <td className="px-6 py-3 font-mono text-xs text-gray-400">{s.source_id.slice(0, 8)}…</td>
                  <td className="px-6 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      {/* Edit + Delete — appear on row hover */}
                      <button
                        onClick={() => setEditingSource(s)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-indigo-600"
                        title="Edit source"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(s)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
                        title="Delete source"
                      >
                        <Trash2 size={13} />
                      </button>
                      <button
                        onClick={() => { setHydratingId(s.source_id); hydrateMut.mutate(s.source_id); }}
                        disabled={hydratingId === s.source_id}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-indigo-200 text-indigo-600 text-xs font-medium hover:bg-indigo-50 disabled:opacity-50"
                      >
                        {hydratingId === s.source_id ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                        Hydrate
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Jobs table */}
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Hydration Jobs</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{(jobs as any[]).length}</span>
            <button onClick={() => qc.invalidateQueries({ queryKey: ['jobs'] })} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400" title="Refresh">
              <RefreshCw size={13} className={fetchingJobs ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {loadingJobs && !fetchingJobs && (
          <div className="flex items-center justify-center py-8 text-gray-400 gap-2">
            <Loader2 size={18} className="animate-spin" />
          </div>
        )}

        {!loadingJobs && !fetchingJobs && (jobs as any[]).length === 0 && (
          <div className="py-12 text-center text-gray-400 text-sm">
            No hydration jobs yet. Click <strong>Hydrate</strong> on a registered source.
          </div>
        )}

        {(jobs as any[]).length > 0 && (
          <div className="divide-y divide-gray-100">
            {[...(jobs as any[])].reverse().slice(0, 30).map((j) => {
              const st = JOB_STATUS[j.status] ?? JOB_STATUS.queued;
              return (
                <div key={j.job_id} className="px-6 py-4 hover:bg-gray-50">
                  <div className="flex items-center gap-4">
                    {/* Status badge */}
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full flex-shrink-0 ${st.color}`}>
                      {st.icon} {st.label}
                    </span>

                    {/* Source + time */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 text-xs text-gray-400">
                        <span className="font-mono">job {j.job_id?.slice(0, 8)}…</span>
                        <span>·</span>
                        <span className="font-mono">src {j.source_id?.slice(0, 8)}…</span>
                        <span>·</span>
                        <span>{j.started_at ? elapsed(j.started_at) : '—'}</span>
                        {j.duration_secs != null && (
                          <><span>·</span><span>{j.duration_secs}s</span></>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Completed detail */}
                  {j.status === 'completed' && (
                    <div className="mt-3 ml-1 flex flex-wrap gap-3">
                      <div className="flex items-center gap-1.5 bg-green-50 border border-green-200 rounded-lg px-3 py-1.5">
                        <Database size={13} className="text-green-600" />
                        <span className="text-xs font-semibold text-green-700">{j.schemas_discovered ?? 0}</span>
                        <span className="text-xs text-green-600">schemas</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5">
                        <Database size={13} className="text-indigo-600" />
                        <span className="text-xs font-semibold text-indigo-700">{j.tables_discovered ?? 0}</span>
                        <span className="text-xs text-indigo-600">tables</span>
                      </div>
                      <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5">
                        <BarChart2 size={13} className="text-blue-600" />
                        <span className="text-xs font-semibold text-blue-700">{j.columns_discovered ?? 0}</span>
                        <span className="text-xs text-blue-600">columns</span>
                      </div>
                      {j.completed_at && (
                        <div className="flex items-center gap-1.5 text-xs text-gray-400 ml-auto">
                          <CheckCircle size={12} className="text-green-500" />
                          Completed {elapsed(j.completed_at)}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Failed detail */}
                  {j.status === 'failed' && j.error && (
                    <div className="mt-2 ml-1 p-2.5 bg-red-50 border border-red-200 rounded-lg">
                      <p className="text-xs text-red-600 font-mono break-all">{j.error}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showRegister && (
        <RegisterPanel
          onClose={() => setShowRegister(false)}
          onRegistered={handleRegistered}
        />
      )}

      {editingSource && (
        <EditPanel
          source={editingSource}
          onClose={() => setEditingSource(null)}
        />
      )}
    </div>
  );
}
