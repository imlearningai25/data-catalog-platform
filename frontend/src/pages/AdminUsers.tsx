import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  UserPlus, Shield, CheckCircle, XCircle, Pencil, Trash2, X,
  Search, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { authApi } from '../services/api';
import type { User } from '../types';

const ROLES = ['viewer', 'data_analyst', 'data_steward', 'admin'] as const;

const ROLE_CONFIG: Record<string, { color: string; bg: string }> = {
  admin:        { color: 'text-red-700',    bg: 'bg-red-50 border-red-200' },
  data_steward: { color: 'text-amber-700',  bg: 'bg-amber-50 border-amber-200' },
  data_analyst: { color: 'text-blue-700',   bg: 'bg-blue-50 border-blue-200' },
  viewer:       { color: 'text-gray-700',   bg: 'bg-gray-50 border-gray-200' },
};

const PAGE_SIZE = 10;

type CreateForm = { email: string; full_name: string; role: string; department: string; password: string };
type EditForm   = { full_name: string; role: string; department: string; is_active: boolean };

const BLANK_CREATE: CreateForm = { email: '', full_name: '', role: 'viewer', department: '', password: '' };

function formatLogin(ts: string | null | undefined) {
  if (!ts) return 'Never';
  const d = new Date(ts);
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60_000) return 'Just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return d.toLocaleDateString();
}

export default function AdminUsers() {
  const qc = useQueryClient();

  // filters / pagination
  const [search, setSearch]       = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage]           = useState(1);

  // modals
  const [showCreate, setShowCreate]     = useState(false);
  const [createForm, setCreateForm]     = useState<CreateForm>(BLANK_CREATE);
  const [editingUser, setEditingUser]   = useState<User | null>(null);
  const [editForm, setEditForm]         = useState<EditForm>({ full_name: '', role: '', department: '', is_active: true });
  const [confirmDelete, setConfirmDelete] = useState<User | null>(null);

  const queryParams = {
    q:         search || undefined,
    role:      roleFilter || undefined,
    is_active: statusFilter === '' ? undefined : statusFilter === 'active',
    page,
    page_size: PAGE_SIZE,
  };

  const { data } = useQuery({
    queryKey: ['users', queryParams],
    queryFn:  () => authApi.listUsers(queryParams),
  });

  const users      = data?.users ?? [];
  const total      = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function resetPage() { setPage(1); }

  // ── mutations ────────────────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () => authApi.createUser(createForm as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setShowCreate(false);
      setCreateForm(BLANK_CREATE);
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => authApi.updateUser(editingUser!.user_id, {
      full_name:  editForm.full_name,
      role:       editForm.role,
      department: editForm.department || undefined,
      is_active:  editForm.is_active,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setEditingUser(null); },
  });

  const deleteMutation = useMutation({
    mutationFn: () => authApi.deleteUser(confirmDelete!.user_id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setConfirmDelete(null); },
  });

  // ── helpers ──────────────────────────────────────────────────────────────────

  function openEdit(u: User) {
    setEditForm({ full_name: u.full_name, role: u.role, department: u.department ?? '', is_active: u.is_active });
    setEditingUser(u);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
          <p className="text-gray-500 text-sm mt-1">{total} user{total !== 1 ? 's' : ''} · Zero Trust RBAC</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
        >
          <UserPlus size={16} /> Add User
        </button>
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); resetPage(); }}
            placeholder="Search by name or email…"
            className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
        <select
          value={roleFilter}
          onChange={e => { setRoleFilter(e.target.value); resetPage(); }}
          className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <option value="">All Roles</option>
          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); resetPage(); }}
          className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <option value="">All Status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      {/* ── Create modal ─────────────────────────────────────────────────────── */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-900">Create User</h2>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <div className="space-y-3">
              {(['email', 'full_name', 'department'] as const).map(f => (
                <input
                  key={f}
                  value={createForm[f]}
                  onChange={e => setCreateForm(p => ({ ...p, [f]: e.target.value }))}
                  placeholder={f.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              ))}
              <input
                type="password"
                value={createForm.password}
                onChange={e => setCreateForm(p => ({ ...p, password: e.target.value }))}
                placeholder="Password"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <select
                value={createForm.role}
                onChange={e => setCreateForm(p => ({ ...p, role: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => createMutation.mutate()}
                disabled={!createForm.email || !createForm.full_name || !createForm.password || createMutation.isPending}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating…' : 'Create'}
              </button>
              <button onClick={() => setShowCreate(false)} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit modal ───────────────────────────────────────────────────────── */}
      {editingUser && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-bold text-gray-900">Edit User</h2>
              <button onClick={() => setEditingUser(null)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <p className="text-xs text-gray-400 mb-4">{editingUser.email}</p>
            <div className="space-y-3">
              <input
                value={editForm.full_name}
                onChange={e => setEditForm(p => ({ ...p, full_name: e.target.value }))}
                placeholder="Full name"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                value={editForm.department}
                onChange={e => setEditForm(p => ({ ...p, department: e.target.value }))}
                placeholder="Department"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <select
                value={editForm.role}
                onChange={e => setEditForm(p => ({ ...p, role: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              {/* Status toggle */}
              <label className="flex items-center gap-3 px-4 py-2.5 border border-gray-200 rounded-lg cursor-pointer select-none">
                <div
                  onClick={() => setEditForm(p => ({ ...p, is_active: !p.is_active }))}
                  className={`relative w-9 h-5 rounded-full transition-colors ${editForm.is_active ? 'bg-green-500' : 'bg-gray-300'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${editForm.is_active ? 'translate-x-4' : ''}`} />
                </div>
                <span className="text-sm text-gray-700">{editForm.is_active ? 'Active' : 'Inactive'}</span>
              </label>
            </div>
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => updateMutation.mutate()}
                disabled={!editForm.full_name || updateMutation.isPending}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
              </button>
              <button onClick={() => setEditingUser(null)} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete confirmation ──────────────────────────────────────────────── */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <Trash2 size={18} className="text-red-600" />
              </div>
              <h2 className="text-base font-bold text-gray-900">Delete user?</h2>
            </div>
            <p className="text-sm text-gray-500 mb-5">
              <span className="font-medium text-gray-800">{confirmDelete.full_name}</span> ({confirmDelete.email}) will be permanently removed.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="flex-1 bg-red-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
              <button onClick={() => setConfirmDelete(null)} className="flex-1 border border-gray-200 py-2.5 rounded-lg text-sm font-medium hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              {['User', 'Role', 'Department', 'Last Login', 'Status', ''].map(h => (
                <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-gray-400">No users found</td></tr>
            )}
            {users.map((user: User) => {
              const rc = ROLE_CONFIG[user.role] ?? ROLE_CONFIG.viewer;
              return (
                <tr key={user.user_id} className="border-b border-gray-50 hover:bg-gray-50 group">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center text-xs font-bold text-indigo-600 flex-shrink-0">
                        {user.full_name?.[0]?.toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-gray-800">{user.full_name}</div>
                        <div className="text-xs text-gray-400">{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${rc.bg} ${rc.color}`}>
                      <Shield size={11} className="inline mr-1" />{user.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">{user.department ?? '—'}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">{formatLogin((user as any).last_login)}</td>
                  <td className="px-4 py-3">
                    {user.is_active
                      ? <span className="flex items-center gap-1 text-green-600 text-xs"><CheckCircle size={13} />Active</span>
                      : <span className="flex items-center gap-1 text-gray-400 text-xs"><XCircle size={13} />Inactive</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => openEdit(user)}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-indigo-600"
                        title="Edit user"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => setConfirmDelete(user)}
                        className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
                        title="Delete user"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50">
            <span className="text-xs text-gray-500">
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-40 text-gray-500"
              >
                <ChevronLeft size={15} />
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                .reduce<(number | '…')[]>((acc, p, idx, arr) => {
                  if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push('…');
                  acc.push(p);
                  return acc;
                }, [])
                .map((p, i) =>
                  p === '…'
                    ? <span key={`e${i}`} className="px-1 text-gray-400 text-xs">…</span>
                    : <button
                        key={p}
                        onClick={() => setPage(p as number)}
                        className={`w-7 h-7 rounded text-xs font-medium ${page === p ? 'bg-indigo-600 text-white' : 'hover:bg-gray-200 text-gray-600'}`}
                      >{p}</button>
                )}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-40 text-gray-500"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
