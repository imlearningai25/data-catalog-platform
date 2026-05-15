import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Search, Pencil, Trash2, X } from 'lucide-react';
import { termsApi } from '../services/api';
import { useAuthStore } from '../store/authStore';
import type { GlossaryTerm } from '../types';

type TermForm = { name: string; definition: string; domain: string; synonyms: string; status: string };

const BLANK: TermForm = { name: '', definition: '', domain: '', synonyms: '', status: 'ACTIVE' };

const STATUS_CLASSES: Record<string, string> = {
  ACTIVE: 'bg-green-100 text-green-700',
  DRAFT:  'bg-amber-100 text-amber-700',
};

export default function Glossary() {
  const [search, setSearch] = useState('');
  const [domain, setDomain] = useState('');
  // editing === null  → modal closed
  // editing === 'new' → create modal
  // editing === term  → edit modal for that term
  const [editing, setEditing] = useState<null | 'new' | GlossaryTerm>(null);
  const [form, setForm] = useState<TermForm>(BLANK);
  const [confirmDelete, setConfirmDelete] = useState<GlossaryTerm | null>(null);
  const { role } = useAuthStore();
  const qc = useQueryClient();
  const canEdit = role === 'data_steward' || role === 'admin';

  const { data } = useQuery({
    queryKey: ['terms', search, domain],
    queryFn: () => termsApi.listTerms({ q: search || undefined, domain: domain || undefined }),
  });

  function openCreate() {
    setForm(BLANK);
    setEditing('new');
  }

  function openEdit(term: GlossaryTerm) {
    setForm({
      name: term.name,
      definition: term.definition,
      domain: term.domain ?? '',
      synonyms: term.synonyms.join(', '),
      status: term.status,
    });
    setEditing(term);
  }

  function closeModal() {
    setEditing(null);
    setForm(BLANK);
  }

  const createMutation = useMutation({
    mutationFn: () => termsApi.createTerm({
      name: form.name,
      definition: form.definition,
      domain: form.domain || undefined,
      synonyms: form.synonyms ? form.synonyms.split(',').map(s => s.trim()) : [],
      status: 'ACTIVE',
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['terms'] }); closeModal(); },
  });

  const deleteMutation = useMutation({
    mutationFn: (termId: string) => termsApi.deleteTerm(termId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['terms'] }); setConfirmDelete(null); },
  });

  const updateMutation = useMutation({
    mutationFn: (termId: string) => termsApi.updateTerm(termId, {
      name: form.name,
      definition: form.definition,
      domain: form.domain || undefined,
      synonyms: form.synonyms ? form.synonyms.split(',').map(s => s.trim()) : [],
      status: form.status as GlossaryTerm['status'],
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['terms'] }); closeModal(); },
  });

  const isNew = editing === 'new';
  const editingTerm = editing && editing !== 'new' ? editing : null;
  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Business Glossary</h1>
          <p className="text-gray-500 text-sm mt-1">{data?.total ?? 0} terms defined across the enterprise</p>
        </div>
        {canEdit && (
          <button onClick={openCreate} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">
            <Plus size={16} /> New Term
          </button>
        )}
      </div>

      {/* Search + filter */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search terms..." className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        </div>
        <select value={domain} onChange={e => setDomain(e.target.value)} className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400">
          <option value="">All Domains</option>
          {['finance', 'hr', 'customer', 'product', 'operations', 'security', 'compliance', 'data_governance'].map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* Create / Edit modal */}
      {editing !== null && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-900">{isNew ? 'Create Business Term' : 'Edit Term'}</h2>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <div className="space-y-3">
              <input
                value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="Term name *"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <textarea
                value={form.definition}
                onChange={e => setForm(p => ({ ...p, definition: e.target.value }))}
                placeholder="Definition *"
                rows={3}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
              />
              <div className="flex gap-3">
                <input
                  value={form.domain}
                  onChange={e => setForm(p => ({ ...p, domain: e.target.value }))}
                  placeholder="Domain (e.g. finance)"
                  className="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
                {!isNew && (
                  <select
                    value={form.status}
                    onChange={e => setForm(p => ({ ...p, status: e.target.value }))}
                    className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="DRAFT">DRAFT</option>
                    <option value="DEPRECATED">DEPRECATED</option>
                  </select>
                )}
              </div>
              <input
                value={form.synonyms}
                onChange={e => setForm(p => ({ ...p, synonyms: e.target.value }))}
                placeholder="Synonyms (comma-separated)"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => isNew ? createMutation.mutate() : updateMutation.mutate((editingTerm as GlossaryTerm).term_id)}
                disabled={!form.name || !form.definition || isPending}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {isPending ? 'Saving…' : isNew ? 'Create Term' : 'Save Changes'}
              </button>
              <button onClick={closeModal} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <Trash2 size={18} className="text-red-600" />
              </div>
              <h2 className="text-base font-bold text-gray-900">Delete term?</h2>
            </div>
            <p className="text-sm text-gray-500 mb-5">
              <span className="font-medium text-gray-800">"{confirmDelete.name}"</span> will be permanently removed. This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => deleteMutation.mutate(confirmDelete.term_id)}
                disabled={deleteMutation.isPending}
                className="flex-1 bg-red-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
              <button onClick={() => setConfirmDelete(null)} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Terms grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {data?.terms.map(term => (
          <div key={term.term_id} className="group bg-white border border-gray-200 rounded-xl p-5 hover:border-indigo-200 transition-colors">
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-semibold text-gray-900">{term.name}</h3>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_CLASSES[term.status] ?? 'bg-gray-100 text-gray-500'}`}>
                  {term.status}
                </span>
                {canEdit && (
                  <>
                    <button
                      onClick={() => openEdit(term)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-indigo-600"
                      title="Edit term"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={() => setConfirmDelete(term)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
                      title="Delete term"
                    >
                      <Trash2 size={13} />
                    </button>
                  </>
                )}
              </div>
            </div>
            <p className="text-sm text-gray-500 line-clamp-2 mb-3">{term.definition}</p>
            <div className="flex flex-wrap gap-1.5">
              {term.domain && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{term.domain}</span>
              )}
              {term.synonyms.slice(0, 2).map(s => (
                <span key={s} className="text-xs bg-indigo-50 text-indigo-600 border border-indigo-100 px-2 py-0.5 rounded-full">{s}</span>
              ))}
              {term.synonyms.length > 2 && (
                <span className="text-xs text-gray-400">+{term.synonyms.length - 2} more</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
