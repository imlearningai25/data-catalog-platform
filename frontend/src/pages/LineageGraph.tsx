/**
 * Lineage Graph — Interactive data flow explorer.
 * Features: asset picker, relationship-typed edges, click-to-detail nodes,
 * focus highlighting, full-network view, impact summary panel.
 */

import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import ReactFlow, {
  Background, Controls, MiniMap,
  Node, Edge, Handle, Position,
  NodeTypes, EdgeTypes,
  useNodesState, useEdgesState,
  BaseEdge, EdgeLabelRenderer, getBezierPath,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { GitBranch, Database, ChevronDown, ArrowUpRight, ArrowDownRight, Layers, ExternalLink } from 'lucide-react';
import { lineageApi, catalogApi } from '../services/api';

// ── Constants ────────────────────────────────────────────────────────────────

const PLATFORM_COLOR: Record<string, { bg: string; text: string }> = {
  postgresql: { bg: '#16a34a', text: '#fff' },
  mysql:      { bg: '#2563eb', text: '#fff' },
  bigquery:   { bg: '#0891b2', text: '#fff' },
  mssql:      { bg: '#7c3aed', text: '#fff' },
  teradata:   { bg: '#b45309', text: '#fff' },
};

const SENSITIVITY_RING: Record<string, string> = {
  PUBLIC:       '#22c55e',
  INTERNAL:     '#3b82f6',
  CONFIDENTIAL: '#f59e0b',
  RESTRICTED:   '#ef4444',
};

const REL_STYLE: Record<string, { stroke: string; label: string; dash?: string }> = {
  TRANSFORMED: { stroke: '#6366f1', label: 'transforms' },
  JOINED:      { stroke: '#10b981', label: 'joins',      dash: '6 3' },
  DERIVED:     { stroke: '#f59e0b', label: 'derives',    dash: '3 3' },
  REFERENCED:  { stroke: '#8b5cf6', label: 'references', dash: '8 4' },
};

// ── Custom node ───────────────────────────────────────────────────────────────

interface NodeData {
  fqn: string;
  label: string;
  schema: string;
  platform: string;
  sensitivity: string;
  domain?: string;
  focused: boolean;
  isCurrent: boolean;
}

function DatasetNode({ data }: { data: NodeData }) {
  const navigate = useNavigate();
  const plt = PLATFORM_COLOR[data.platform] ?? { bg: '#6b7280', text: '#fff' };
  const ring = SENSITIVITY_RING[data.sensitivity] ?? '#e5e7eb';
  const opacity = data.focused ? 1 : 0.45;

  return (
    <div
      style={{
        opacity,
        borderColor: ring,
        boxShadow: data.isCurrent
          ? `0 0 0 3px ${ring}55, 0 4px 20px ${ring}33`
          : data.focused ? '0 4px 12px rgba(0,0,0,0.12)' : 'none',
        transition: 'opacity 0.2s, box-shadow 0.2s',
      }}
      className="bg-white rounded-2xl border-2 min-w-52 max-w-64 overflow-hidden select-none"
    >
      <Handle type="target" position={Position.Left}
        style={{ background: ring, width: 10, height: 10, border: '2px solid white' }} />

      {/* Platform header */}
      <div className="px-3 pt-2.5 pb-2 flex items-center gap-2"
        style={{ background: `${plt.bg}18` }}>
        <span className="text-xs font-bold px-2 py-0.5 rounded-full"
          style={{ background: plt.bg, color: plt.text }}>
          {data.platform}
        </span>
        <span className="text-xs text-gray-400 truncate">{data.schema}</span>
      </div>

      {/* Table name */}
      <div className="px-3 py-2.5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-gray-900 text-sm leading-tight">{data.label}</p>
            {data.domain && (
              <p className="text-xs text-gray-400 mt-0.5 capitalize">{data.domain}</p>
            )}
          </div>
          <button
            onClick={() => navigate(`/catalog/${encodeURIComponent(data.fqn)}`)}
            className="flex-shrink-0 p-1 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
            title="Open asset detail"
          >
            <ExternalLink size={13} />
          </button>
        </div>
        {/* Sensitivity pill */}
        <span className="mt-2 inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium"
          style={{ background: `${ring}18`, color: ring, border: `1px solid ${ring}44` }}>
          {data.sensitivity}
        </span>
      </div>

      <Handle type="source" position={Position.Right}
        style={{ background: ring, width: 10, height: 10, border: '2px solid white' }} />
    </div>
  );
}

// ── Custom edge with animated dash + label ─────────────────────────────────

function RelEdge({ id, sourceX, sourceY, targetX, targetY, data }: any) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition: Position.Right,
    targetX, targetY, targetPosition: Position.Left,
  });
  const style = REL_STYLE[data?.relationship] ?? REL_STYLE.TRANSFORMED;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: style.stroke,
          strokeWidth: 2,
          strokeDasharray: style.dash ?? 'none',
          animation: !style.dash ? 'dashdraw 0.6s linear infinite' : undefined,
        }}
        markerEnd={`url(#arrow-${data?.relationship ?? 'TRANSFORMED'})`}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'none',
            color: style.stroke,
            borderColor: `${style.stroke}44`,
          }}
          className="text-xs font-medium px-2 py-0.5 rounded-full bg-white border shadow-sm"
        >
          {style.label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes: NodeTypes = { dataset: DatasetNode };
const edgeTypes: EdgeTypes  = { rel: RelEdge };

// ── Layout (left-to-right DAG) ────────────────────────────────────────────────

function layoutDag(nodes: Node[], edges: Edge[]): Node[] {
  const inDegree = new Map<string, number>();
  const adj      = new Map<string, string[]>();

  nodes.forEach(n => { adj.set(n.id, []); inDegree.set(n.id, 0); });
  edges.forEach(e => {
    adj.get(e.source)?.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  });

  const level = new Map<string, number>();
  const queue = nodes.filter(n => (inDegree.get(n.id) ?? 0) === 0).map(n => n.id);
  queue.forEach(id => level.set(id, 0));

  while (queue.length) {
    const id = queue.shift()!;
    adj.get(id)?.forEach(next => {
      level.set(next, Math.max(level.get(next) ?? 0, (level.get(id) ?? 0) + 1));
      queue.push(next);
    });
  }

  const colCount = new Map<number, number>();
  return nodes.map(n => {
    const col = level.get(n.id) ?? 0;
    const row = colCount.get(col) ?? 0;
    colCount.set(col, row + 1);
    return { ...n, position: { x: col * 340, y: row * 175 + 40 } };
  });
}

// ── Build ReactFlow graph from lineage edges ──────────────────────────────────

function buildGraph(rawEdges: any[], currentFqn: string, focusedId: string | null) {
  // Deduplicate edges by source+target+relationship (keep first occurrence)
  const seen = new Set<string>();
  const edges = rawEdges.filter(e => {
    const key = `${e.source_fqn}|${e.target_fqn}|${e.relationship}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const nodeMap = new Map<string, Node>();

  const addNode = (fqn: string, platform: string) => {
    if (nodeMap.has(fqn)) return;
    const parts = fqn.split('.');
    const isCurrent = fqn === currentFqn;
    const focused = !focusedId || focusedId === fqn ||
      edges.some(e => (e.source_fqn === focusedId && e.target_fqn === fqn) ||
                      (e.target_fqn === focusedId && e.source_fqn === fqn));

    nodeMap.set(fqn, {
      id: fqn,
      type: 'dataset',
      position: { x: 0, y: 0 },
      data: {
        fqn,
        label:     parts[parts.length - 1],
        schema:    parts.slice(0, -1).join('.'),
        platform:  platform,
        sensitivity: 'INTERNAL',
        isCurrent,
        focused,
      },
    });
  };

  edges.forEach(e => {
    addNode(e.source_fqn, e.source_platform);
    addNode(e.target_fqn, e.target_platform);
  });

  const flowEdges: Edge[] = edges.map(e => ({
    id: e.lineage_id,
    source: e.source_fqn,
    target: e.target_fqn,
    type: 'rel',
    data: { relationship: e.relationship, sql: e.transformation_sql },
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { strokeWidth: 2 },
  }));

  const laid = layoutDag(Array.from(nodeMap.values()), flowEdges);
  return { nodes: laid, edges: flowEdges };
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function LineageGraph() {
  const [selectedFqn, setSelectedFqn] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [focusedId, setFocusedId]       = useState<string | null>(null);

  // Load all catalog assets for the picker
  const { data: catalogData } = useQuery({
    queryKey: ['catalog', 'assets', 'lineage-picker'],
    queryFn: () => catalogApi.searchAssets({ limit: 100 }),
  });

  // Full network (no FQN filter) so we can show "All" view
  const { data: allLineage } = useQuery({
    queryKey: ['lineage', 'all'],
    queryFn: () => lineageApi.getLineage(undefined as any, 'both', 5),
  });

  const { data: focusLineage, isLoading } = useQuery({
    queryKey: ['lineage', selectedFqn],
    queryFn: () => lineageApi.getLineage(selectedFqn, 'both', 3),
    enabled: !!selectedFqn,
  });

  const activeEdges = selectedFqn
    ? (focusLineage?.edges ?? [])
    : (allLineage?.edges ?? []);

  const { nodes: builtNodes, edges: builtEdges } = useMemo(
    () => buildGraph(activeEdges, selectedFqn, focusedId),
    [activeEdges, selectedFqn, focusedId]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => { setNodes(builtNodes); }, [builtNodes]);
  useEffect(() => { setEdges(builtEdges); }, [builtEdges]);

  const upstreamCount   = activeEdges.filter(e => e.target_fqn === selectedFqn).length;
  const downstreamCount = activeEdges.filter(e => e.source_fqn === selectedFqn).length;

  const assets = catalogData?.assets ?? [];

  return (
    <div className="flex flex-col gap-4" style={{ height: 'calc(100vh - 120px)' }}>

      {/* Header + controls */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Data Lineage</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Explore data flow across {allLineage?.edges?.length ?? 0} recorded edges
          </p>
        </div>

        {/* Asset picker */}
        <div className="relative min-w-80">
          <button
            onClick={() => setDropdownOpen(o => !o)}
            className="w-full flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-left hover:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-400 shadow-sm"
          >
            <Database size={15} className="text-indigo-500 flex-shrink-0" />
            <span className="flex-1 truncate text-gray-700">
              {selectedFqn
                ? assets.find(a => a.fqn === selectedFqn)?.table_name ?? selectedFqn.split('.').pop()
                : 'Show full network'}
            </span>
            <ChevronDown size={15} className={`text-gray-400 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
              <button
                className="w-full text-left px-4 py-2.5 text-sm text-indigo-600 font-medium hover:bg-indigo-50 border-b border-gray-100 flex items-center gap-2"
                onClick={() => { setSelectedFqn(''); setDropdownOpen(false); setFocusedId(null); }}
              >
                <Layers size={14} /> Show full network
              </button>
              {assets.map(a => (
                <button
                  key={a.fqn}
                  onClick={() => { setSelectedFqn(a.fqn); setDropdownOpen(false); setFocusedId(null); }}
                  className={`w-full text-left px-4 py-2.5 hover:bg-gray-50 flex items-start gap-3 ${selectedFqn === a.fqn ? 'bg-indigo-50' : ''}`}
                >
                  <Database size={13} className="text-gray-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <div className="text-sm font-medium text-gray-800">{a.table_name}</div>
                    <div className="text-xs text-gray-400 truncate">{a.fqn}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main canvas + side panel */}
      <div className="flex gap-4 flex-1 min-h-0">

        {/* ReactFlow canvas */}
        <div className="flex-1 bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm relative">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 z-10">
              <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {nodes.length === 0 && !isLoading && (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-3">
              <GitBranch size={48} className="opacity-20" />
              <p className="font-medium">No lineage data found</p>
              <p className="text-sm">Select an asset above or run the seed script</p>
            </div>
          )}

          {/* Arrow marker defs */}
          <svg style={{ position: 'absolute', width: 0, height: 0 }}>
            <defs>
              {Object.entries(REL_STYLE).map(([key, s]) => (
                <marker key={key} id={`arrow-${key}`} markerWidth="8" markerHeight="8"
                  refX="6" refY="3" orient="auto">
                  <path d="M0,0 L0,6 L8,3 z" fill={s.stroke} />
                </marker>
              ))}
            </defs>
          </svg>

          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onNodeClick={(_, node) => setFocusedId(id => id === node.id ? null : node.id)}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            minZoom={0.3}
            maxZoom={2}
            attributionPosition="bottom-left"
          >
            <Background gap={20} size={1} color="#e5e7eb" />
            <Controls showInteractive={false} className="rounded-xl overflow-hidden shadow-sm" />
            <MiniMap
              nodeColor={n => SENSITIVITY_RING[(n.data as NodeData)?.sensitivity] ?? '#94a3b8'}
              className="rounded-xl overflow-hidden shadow-sm border border-gray-200"
              style={{ background: '#f9fafb' }}
            />
          </ReactFlow>
        </div>

        {/* Side panel */}
        <div className="w-64 flex flex-col gap-3">
          {/* Stats */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Graph Stats</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Total edges</span>
                <span className="text-sm font-bold text-indigo-600">{activeEdges.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Unique assets</span>
                <span className="text-sm font-bold text-indigo-600">{nodes.length}</span>
              </div>
              {selectedFqn && (
                <>
                  <hr className="border-gray-100" />
                  <div className="flex items-center gap-2">
                    <ArrowUpRight size={14} className="text-blue-500" />
                    <span className="text-sm text-gray-600">Upstream</span>
                    <span className="ml-auto text-sm font-bold text-blue-600">{upstreamCount}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ArrowDownRight size={14} className="text-amber-500" />
                    <span className="text-sm text-gray-600">Downstream</span>
                    <span className="ml-auto text-sm font-bold text-amber-600">{downstreamCount}</span>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Legend */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Relationships</h3>
            <div className="space-y-2">
              {Object.entries(REL_STYLE).map(([key, s]) => (
                <div key={key} className="flex items-center gap-2.5">
                  <svg width="28" height="8">
                    <line x1="0" y1="4" x2="24" y2="4"
                      stroke={s.stroke} strokeWidth="2"
                      strokeDasharray={s.dash ?? 'none'} />
                    <polygon points="24,1 28,4 24,7" fill={s.stroke} />
                  </svg>
                  <span className="text-xs text-gray-600 capitalize">{s.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Sensitivity legend */}
          <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Sensitivity</h3>
            <div className="space-y-2">
              {Object.entries(SENSITIVITY_RING).map(([level, color]) => (
                <div key={level} className="flex items-center gap-2.5">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: color }} />
                  <span className="text-xs text-gray-600 capitalize">{level.toLowerCase()}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Hint */}
          <p className="text-xs text-gray-400 px-1 leading-relaxed">
            Click a node to highlight its connections.
            Click <ExternalLink size={10} className="inline" /> on a node to open asset detail.
          </p>
        </div>
      </div>
    </div>
  );
}
