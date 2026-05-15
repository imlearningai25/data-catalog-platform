/**
 * Dashboard — Catalog health, quality overview, PII coverage.
 */

import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, Legend
} from 'recharts';
import { Database, Shield, AlertTriangle, CheckCircle, TrendingUp, Layers } from 'lucide-react';

const QUALITY_COLORS: Record<string, string> = {
  A: '#22c55e', B: '#84cc16', C: '#f59e0b', D: '#f97316', F: '#ef4444',
};

const SENSITIVITY_COLORS: Record<string, string> = {
  PUBLIC: '#22c55e', INTERNAL: '#3b82f6', CONFIDENTIAL: '#f59e0b', RESTRICTED: '#ef4444',
};

// Mock data (replace with real API calls)
const MOCK_STATS = {
  total_assets: 1284,
  total_pii_assets: 247,
  avg_quality_score: 0.78,
  by_quality_grade: [
    { grade: 'A', count: 423 },
    { grade: 'B', count: 387 },
    { grade: 'C', count: 289 },
    { grade: 'D', count: 142 },
    { grade: 'F', count: 43 },
  ],
  by_sensitivity: [
    { level: 'PUBLIC', count: 312 },
    { level: 'INTERNAL', count: 648 },
    { level: 'CONFIDENTIAL', count: 278 },
    { level: 'RESTRICTED', count: 46 },
  ],
  by_source: [
    { source: 'Teradata', count: 687 },
    { source: 'MSSQL', count: 421 },
    { source: 'BigQuery', count: 176 },
  ],
  by_domain: [
    { domain: 'Finance', count: 389 },
    { domain: 'Customer', count: 287 },
    { domain: 'HR', count: 198 },
    { domain: 'Operations', count: 246 },
    { domain: 'Security', count: 164 },
  ],
  quality_trend: [
    { month: 'Jan', score: 0.71 },
    { month: 'Feb', score: 0.73 },
    { month: 'Mar', score: 0.74 },
    { month: 'Apr', score: 0.76 },
    { month: 'May', score: 0.78 },
  ],
};

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: string | number; sub?: string; color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <div className="text-2xl font-bold text-gray-900">{value}</div>
        <div className="text-sm font-medium text-gray-600">{label}</div>
        {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const stats = MOCK_STATS;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platform Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Data catalog health, quality, and compliance overview</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Database}     label="Total Assets"       value={stats.total_assets.toLocaleString()} color="bg-indigo-500" />
        <StatCard icon={Shield}       label="PII Assets"         value={stats.total_pii_assets} sub="Require governance" color="bg-red-500" />
        <StatCard icon={TrendingUp}   label="Avg Quality Score"  value={`${Math.round(stats.avg_quality_score * 100)}%`} sub="Platform-wide" color="bg-green-500" />
        <StatCard icon={Layers}       label="Data Sources"       value={stats.by_source.length} sub="Connected" color="bg-blue-500" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Quality grade distribution */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Quality Grade Distribution</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stats.by_quality_grade} barSize={40}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="grade" tick={{ fontSize: 13 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" name="Assets" radius={[4, 4, 0, 0]}>
                {stats.by_quality_grade.map((entry) => (
                  <Cell key={entry.grade} fill={QUALITY_COLORS[entry.grade]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Sensitivity level pie */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Sensitivity Level Breakdown</h2>
          <div className="flex items-center gap-6">
            <ResponsiveContainer width="55%" height={220}>
              <PieChart>
                <Pie
                  data={stats.by_sensitivity}
                  dataKey="count"
                  nameKey="level"
                  cx="50%" cy="50%"
                  outerRadius={90}
                  innerRadius={50}
                >
                  {stats.by_sensitivity.map((entry) => (
                    <Cell key={entry.level} fill={SENSITIVITY_COLORS[entry.level]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-col gap-2">
              {stats.by_sensitivity.map(({ level, count }) => (
                <div key={level} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: SENSITIVITY_COLORS[level] }} />
                  <span className="text-sm text-gray-600">{level}</span>
                  <span className="ml-auto text-sm font-semibold text-gray-800">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quality trend */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Quality Score Trend</h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={stats.quality_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis domain={[0.6, 1.0]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: number) => `${Math.round(v * 100)}%`} />
              <Line type="monotone" dataKey="score" stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1', r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Assets by domain */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold text-gray-800 mb-4">Assets by Domain</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={stats.by_domain} layout="vertical" barSize={22}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis dataKey="domain" type="category" tick={{ fontSize: 12 }} width={80} />
              <Tooltip />
              <Bar dataKey="count" name="Assets" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
