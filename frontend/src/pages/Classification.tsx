import { useState } from 'react';
import { Shield, AlertTriangle, CheckCircle, Lock } from 'lucide-react';

const MOCK_PII = [
  { fqn: 'teradata://hr.employees.ssn', column: 'ssn', classification: 'PII', category: 'SSN', sensitivity: 'RESTRICTED', table: 'employees', schema: 'hr' },
  { fqn: 'teradata://crm.customers.email', column: 'email', classification: 'PII', category: 'EMAIL', sensitivity: 'CONFIDENTIAL', table: 'customers', schema: 'crm' },
  { fqn: 'mssql://payroll.salary.base_salary', column: 'base_salary', classification: 'SENSITIVE', category: null, sensitivity: 'CONFIDENTIAL', table: 'salary', schema: 'payroll' },
  { fqn: 'teradata://hr.employees.date_of_birth', column: 'date_of_birth', classification: 'PII', category: 'DATE_OF_BIRTH', sensitivity: 'CONFIDENTIAL', table: 'employees', schema: 'hr' },
  { fqn: 'bigquery://customers.profiles.credit_card_num', column: 'credit_card_num', classification: 'PII', category: 'CREDIT_CARD', sensitivity: 'RESTRICTED', table: 'profiles', schema: 'customers' },
];

const SENSITIVITY_CONFIG: Record<string, { color: string; bg: string }> = {
  PUBLIC:       { color: 'text-green-700',  bg: 'bg-green-50 border-green-200' },
  INTERNAL:     { color: 'text-blue-700',   bg: 'bg-blue-50 border-blue-200' },
  CONFIDENTIAL: { color: 'text-amber-700',  bg: 'bg-amber-50 border-amber-200' },
  RESTRICTED:   { color: 'text-red-700',    bg: 'bg-red-50 border-red-200' },
};

export default function Classification() {
  const [filter, setFilter] = useState('');

  const filtered = MOCK_PII.filter(item =>
    !filter || item.sensitivity === filter || item.classification === filter
  );

  const stats = {
    total: MOCK_PII.length,
    restricted: MOCK_PII.filter(p => p.sensitivity === 'RESTRICTED').length,
    confidential: MOCK_PII.filter(p => p.sensitivity === 'CONFIDENTIAL').length,
    pii: MOCK_PII.filter(p => p.classification === 'PII').length,
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Data Classification</h1>
        <p className="text-gray-500 text-sm mt-1">PII detection results and sensitivity classification across all assets</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total PII Columns', value: stats.total, icon: Shield, color: 'bg-indigo-500' },
          { label: 'PII', value: stats.pii, icon: Lock, color: 'bg-red-500' },
          { label: 'RESTRICTED', value: stats.restricted, icon: AlertTriangle, color: 'bg-red-600' },
          { label: 'CONFIDENTIAL', value: stats.confidential, icon: CheckCircle, color: 'bg-amber-500' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4">
            <div className={`p-2.5 rounded-lg ${color}`}><Icon size={18} className="text-white" /></div>
            <div>
              <div className="text-xl font-bold text-gray-900">{value}</div>
              <div className="text-xs text-gray-500">{label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        {['', 'RESTRICTED', 'CONFIDENTIAL', 'PII', 'SENSITIVE'].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${filter === f ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
            {f || 'All'}
          </button>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              {['Asset', 'Column', 'Classification', 'Category', 'Sensitivity'].map(h => (
                <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(item => {
              const sens = SENSITIVITY_CONFIG[item.sensitivity];
              return (
                <tr key={item.fqn} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-800">{item.table}</div>
                    <div className="text-xs text-gray-400 font-mono">{item.schema}</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-sm text-gray-700">{item.column}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-semibold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{item.classification}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-gray-500">{item.category ?? '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-1 rounded-full border ${sens.bg} ${sens.color}`}>
                      {item.sensitivity}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
