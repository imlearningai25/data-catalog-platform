import { useState, useEffect, useRef } from 'react';
import { Code2, ExternalLink, CheckCircle, XCircle, Loader2 } from 'lucide-react';

// ── Service registry ──────────────────────────────────────────────────────────

const SERVICES = [
  {
    id: 'catalog',
    label: 'Catalog Service',
    description: 'Asset registry — search, browse, and manage data assets',
    specUrl: '/api-docs/catalog.json',
    port: 8005,
    color: 'indigo',
  },
  {
    id: 'auth',
    label: 'Auth Service',
    description: 'Authentication, JWT issuance, RBAC, and user management',
    specUrl: '/api-docs/auth.json',
    port: 8006,
    color: 'violet',
  },
  {
    id: 'lineage',
    label: 'Lineage Service',
    description: 'Data lineage edges, impact analysis, DataHub integration',
    specUrl: '/api-docs/lineage.json',
    port: 8008,
    color: 'green',
  },
  {
    id: 'connector',
    label: 'Connector Service',
    description: 'Register data sources and trigger schema hydration jobs',
    specUrl: '/api-docs/connector.json',
    port: 8001,
    color: 'amber',
  },
  {
    id: 'classification',
    label: 'Classification Service',
    description: 'PII detection and sensitivity classification engine',
    specUrl: '/api-docs/classification.json',
    port: 8003,
    color: 'red',
  },
  {
    id: 'terms',
    label: 'Term Service',
    description: 'Business glossary — create, approve, and link terms to assets',
    specUrl: '/api-docs/terms.json',
    port: 8004,
    color: 'cyan',
  },
  {
    id: 'audit',
    label: 'Audit Service',
    description: 'Immutable event log for compliance and access tracking',
    specUrl: '/api-docs/audit.json',
    port: 8007,
    color: 'orange',
  },
  {
    id: 'metadata',
    label: 'Metadata Service',
    description: 'Schema enrichment, quality scoring, and metadata storage',
    specUrl: '/api-docs/metadata.json',
    port: 8002,
    color: 'pink',
  },
];

const COLOR_CLASS: Record<string, { ring: string; badge: string; dot: string }> = {
  indigo: { ring: 'ring-indigo-500',  badge: 'bg-indigo-100 text-indigo-700',  dot: 'bg-indigo-500'  },
  violet: { ring: 'ring-violet-500',  badge: 'bg-violet-100 text-violet-700',  dot: 'bg-violet-500'  },
  green:  { ring: 'ring-green-500',   badge: 'bg-green-100 text-green-700',    dot: 'bg-green-500'   },
  amber:  { ring: 'ring-amber-500',   badge: 'bg-amber-100 text-amber-700',    dot: 'bg-amber-500'   },
  red:    { ring: 'ring-red-500',     badge: 'bg-red-100 text-red-700',        dot: 'bg-red-500'     },
  cyan:   { ring: 'ring-cyan-500',    badge: 'bg-cyan-100 text-cyan-700',      dot: 'bg-cyan-500'    },
  orange: { ring: 'ring-orange-500',  badge: 'bg-orange-100 text-orange-700',  dot: 'bg-orange-500'  },
  pink:   { ring: 'ring-pink-500',    badge: 'bg-pink-100 text-pink-700',      dot: 'bg-pink-500'    },
};

// ── Swagger UI loader (CDN — no npm install needed) ───────────────────────────

const SWAGGER_CSS = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css';
const SWAGGER_JS  = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js';

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src = src; s.async = true;
    s.onload = () => resolve();
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

function loadLink(href: string): void {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const l = document.createElement('link');
  l.rel = 'stylesheet'; l.href = href;
  document.head.appendChild(l);
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ApiDocs() {
  const [selected, setSelected] = useState(SERVICES[0]);
  const [swaggerReady, setSwaggerReady] = useState(false);
  const [specOk, setSpecOk]     = useState<boolean | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const uiRef = useRef<any>(null);

  // Load Swagger UI from CDN once
  useEffect(() => {
    loadLink(SWAGGER_CSS);
    loadScript(SWAGGER_JS)
      .then(() => setSwaggerReady(true))
      .catch(() => console.error('Failed to load Swagger UI from CDN'));
  }, []);

  // Mount/update Swagger UI whenever the selected service or readiness changes
  useEffect(() => {
    if (!swaggerReady || !containerRef.current) return;

    setSpecOk(null);

    // Verify spec is reachable before mounting
    fetch(selected.specUrl)
      .then(r => { setSpecOk(r.ok); return r.ok ? r.json() : null; })
      .then(spec => {
        if (!spec || !containerRef.current) return;

        // Destroy previous instance
        if (uiRef.current?.unmount) uiRef.current.unmount();
        containerRef.current.innerHTML = '';

        uiRef.current = (window as any).SwaggerUIBundle({
          spec,
          domNode: containerRef.current,
          deepLinking: true,
          presets: [
            (window as any).SwaggerUIBundle.presets.apis,
            (window as any).SwaggerUIBundle.SwaggerUIStandalonePreset,
          ],
          layout: 'BaseLayout',
          defaultModelsExpandDepth: 1,
          defaultModelExpandDepth: 2,
          displayRequestDuration: true,
          filter: true,
          tryItOutEnabled: false,   // Requests go through the gateway which requires auth headers
        });
      })
      .catch(() => setSpecOk(false));
  }, [swaggerReady, selected]);

  return (
    <div className="flex flex-col gap-4" style={{ minHeight: 'calc(100vh - 120px)' }}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">API Documentation</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Interactive Swagger UI for all {SERVICES.length} microservices
          </p>
        </div>
        <a
          href={`http://localhost:${selected.port}/docs`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 hover:bg-gray-50 shadow-sm"
        >
          <ExternalLink size={14} /> Open native UI (port {selected.port})
        </a>
      </div>

      {/* Service picker */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {SERVICES.map(svc => {
          const c = COLOR_CLASS[svc.color];
          const isActive = svc.id === selected.id;
          return (
            <button
              key={svc.id}
              onClick={() => setSelected(svc)}
              className={`text-left p-3 rounded-xl border-2 transition-all ${
                isActive
                  ? `border-transparent ring-2 ${c.ring} bg-white shadow-md`
                  : 'border-gray-100 bg-white hover:border-gray-200 hover:shadow-sm'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${c.dot}`} />
                <span className="text-xs font-semibold text-gray-800 leading-tight">{svc.label}</span>
              </div>
              <p className="text-xs text-gray-400 leading-tight pl-4">{svc.description}</p>
              <div className="mt-2 pl-4">
                <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${c.badge}`}>
                  :{svc.port}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm">
        <span className="font-medium text-gray-700">{selected.label}</span>
        <span className="text-gray-300">·</span>
        <code className="text-xs text-gray-500 bg-gray-50 px-2 py-0.5 rounded font-mono">
          GET /api-docs/{selected.id}.json
        </code>
        <span className="ml-auto flex items-center gap-1.5">
          {specOk === null && <Loader2 size={13} className="animate-spin text-gray-400" />}
          {specOk === true  && <><CheckCircle size={13} className="text-green-500" /><span className="text-green-600 text-xs">Spec loaded</span></>}
          {specOk === false && <><XCircle size={13} className="text-red-500" /><span className="text-red-600 text-xs">Spec unavailable</span></>}
        </span>
      </div>

      {/* Swagger UI mount point */}
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden flex-1">
        {!swaggerReady && (
          <div className="flex items-center justify-center py-20 text-gray-400 gap-2">
            <Loader2 size={20} className="animate-spin" />
            <span>Loading Swagger UI…</span>
          </div>
        )}
        {swaggerReady && specOk === false && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400 gap-3">
            <Code2 size={40} className="opacity-20" />
            <p className="font-medium">Spec not reachable</p>
            <p className="text-sm">Make sure the service is running and the gateway is healthy</p>
          </div>
        )}
        {/* The Swagger UI library mounts itself here */}
        <div
          ref={containerRef}
          className="swagger-wrapper"
          style={{ display: swaggerReady && specOk !== false ? 'block' : 'none' }}
        />
      </div>

      {/* Swagger UI style overrides — tighten the default look */}
      <style>{`
        .swagger-wrapper .swagger-ui .topbar { display: none; }
        .swagger-wrapper .swagger-ui .info   { margin: 20px 0 10px; }
        .swagger-wrapper .swagger-ui .info .title { font-size: 1.4rem; }
        .swagger-wrapper .swagger-ui .scheme-container { background: #f9fafb; padding: 12px 20px; border-bottom: 1px solid #e5e7eb; }
        .swagger-wrapper .swagger-ui .opblock-tag { font-size: 0.95rem; }
        .swagger-wrapper .swagger-ui { font-family: inherit; }
        .swagger-wrapper .swagger-ui .opblock .opblock-summary-operation-id { display: none; }
      `}</style>
    </div>
  );
}
