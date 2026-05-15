import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Shield, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { auditApi } from '../services/api';

const OUTCOME_CONFIG = {
  SUCCESS: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50' },
  FAILURE: { icon: XCircle,     color: 'text-red-600',   bg: 'bg-red-50' },
  DENIED:  { icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50' },
};

export default function AuditLog() {
  const [userFilter, setUserFilter] = useState('');
  const [eventType, setEventType] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['audit', userFilter, eventType],
    queryFn: () => auditApi.queryEvents({ user_email: userFilter || undefined, event_type: eventType || undefined, limit: 200 }),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
        <p className="text-gray-500 text-sm mt-1">Immutable audit trail — all platform events stored in BigQuery</p>
      </div>

      <div className="flex gap-3">
        <input value={userFilter} onChange={e => setUserFilter(e.target.value)} placeholder="Filter by user email..." className="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <select value={eventType} onChange={e => setEventType(e.target.value)} className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
          <option value="">All Events</option>
          {['LOGIN', 'LOGIN_FAILED', 'LOGOUT', 'ASSET_READ', 'ASSET_WRITE', 'PII_ACCESS', 'ACCESS_DENIED', 'USER_CREATED', 'USER_UPDATED', 'USER_DELETED', 'USER_ROLE_CHANGED', 'TERM_CREATED', 'TERM_UPDATED', 'HYDRATION_COMPLETED'].map(e => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>{['Timestamp', 'Event', 'User', 'Resource', 'Outcome', 'IP'].map(h => (
              <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b border-gray-50"><td colSpan={6} className="px-4 py-3"><div className="h-4 bg-gray-100 rounded animate-pulse" /></td></tr>
            ))}
            {data?.events.map((evt: any) => {
              const conf = OUTCOME_CONFIG[evt.outcome as keyof typeof OUTCOME_CONFIG] ?? OUTCOME_CONFIG.SUCCESS;
              const Icon = conf.icon;
              return (
                <tr key={evt.audit_id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3 text-xs text-gray-400 font-mono whitespace-nowrap">
                    {new Date(evt.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
                      {evt.event_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-600">{evt.user_email ?? '—'}</td>
                  <td className="px-4 py-3 text-xs font-mono text-gray-500 max-w-48 truncate" title={evt.resource_fqn}>{evt.resource_fqn ?? evt.resource_type ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`flex items-center gap-1.5 text-xs font-medium ${conf.color}`}>
                      <Icon size={13} />{evt.outcome}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400 font-mono">{evt.source_ip ?? '—'}</td>
                </tr>
              );
            })}
            {!isLoading && data?.events.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-400 text-sm">No audit events found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
