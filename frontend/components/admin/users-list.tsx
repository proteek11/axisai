'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn, getInitials } from '@/lib/utils';
import {
  Users, Loader2, ShieldCheck, Pencil, GraduationCap, Plus,
  X, Eye, EyeOff, AlertCircle, UserX, Check, Search,
  Upload, Download, CheckCircle2, Trash2,
} from 'lucide-react';
import { useRef } from 'react';

// ── Types ────────────────────────────────────────────────────────────────────

interface AxisUser {
  id: string;
  email: string;
  full_name: string | null;
  role: 'admin' | 'creator' | 'learner';
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

interface UsersResponse {
  users: AxisUser[];
  total: number;
}

type UserRole = 'admin' | 'creator' | 'learner';

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_META: Record<string, { label: string; icon: React.ElementType; color: string; bg: string; badge: string }> = {
  admin:   { label: 'Admin',   icon: ShieldCheck,  color: 'text-purple-600', bg: 'bg-purple-50', badge: 'border-purple-400 text-purple-600 bg-purple-50' },
  creator: { label: 'Creator', icon: Pencil,        color: 'text-blue-600',   bg: 'bg-blue-50',   badge: 'border-blue-400 text-blue-600 bg-blue-50' },
  learner: { label: 'Learner', icon: GraduationCap, color: 'text-green-600',  bg: 'bg-green-50',  badge: 'border-green-400 text-green-600 bg-green-50' },
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Create / Edit user modal ──────────────────────────────────────────────────

function UserModal({
  user,
  onClose,
  onSave,
  saving,
  error,
}: {
  user?: AxisUser;
  onClose: () => void;
  onSave: (data: Record<string, unknown>) => void;
  saving: boolean;
  error?: string;
}) {
  const isEdit = !!user;
  const [email, setEmail] = useState(user?.email ?? '');
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [role, setRole] = useState<UserRole>(user?.role ?? 'learner');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [isActive, setIsActive] = useState(user?.is_active ?? true);

  const handleSave = () => {
    const payload: Record<string, unknown> = { role, full_name: fullName || null };
    if (!isEdit) {
      payload.email = email;
      payload.password = password;
    } else {
      payload.is_active = isActive;
      if (email !== user?.email) payload.email = email;
      if (password) payload.password = password;
    }
    onSave(payload);
  };

  const valid = isEdit
    ? email.trim().length > 0
    : email.trim() && password.length >= 8;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold text-primary text-lg">
            {isEdit ? 'Edit User' : 'Create New User'}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="section-label mb-1.5">Email *</label>
            <input
              type="email"
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="user@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label className="section-label mb-1.5">Full Name</label>
            <input
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="Jane Smith"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>

          <div>
            <label className="section-label mb-1.5">Role *</label>
            <div className="grid grid-cols-3 gap-2">
              {(['learner', 'creator', 'admin'] as UserRole[]).map((r) => {
                const meta = ROLE_META[r];
                const Icon = meta.icon;
                return (
                  <button
                    key={r}
                    onClick={() => setRole(r)}
                    className={cn(
                      'flex flex-col items-center gap-1 py-2.5 rounded-[var(--radius)] border text-xs font-medium transition-colors',
                      role === r
                        ? 'border-primary bg-primary/5 text-primary'
                        : 'border-border hover:bg-muted text-muted-foreground'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="section-label mb-1.5">
              {isEdit ? 'New Password (leave blank to keep)' : 'Password *'}
            </label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                className="w-full border border-border rounded-[var(--radius)] px-3 py-2 pr-10 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder={isEdit ? '••••••••' : 'Min 8 characters'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {!isEdit && password && password.length < 8 && (
              <p className="text-xs text-red-500 mt-1">Password must be at least 8 characters</p>
            )}
          </div>

          {isEdit && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsActive((v) => !v)}
                className={cn(
                  'relative w-10 h-5 rounded-full transition-colors',
                  isActive ? 'bg-primary' : 'bg-muted-foreground/30'
                )}
              >
                <span className={cn(
                  'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform',
                  isActive ? 'translate-x-5' : 'translate-x-0'
                )} />
              </button>
              <span className="text-sm text-foreground">
                {isActive ? 'Active' : 'Inactive'}
              </span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-[var(--radius)] px-3 py-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 mt-6 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!valid || saving}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {isEdit ? 'Save Changes' : 'Create User'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const PAGE_SIZE = 10;

// ── CSV Template download helper ──────────────────────────────────────────────
const CSV_TEMPLATE = `email,full_name,role,password
alice@example.com,Alice Johnson,learner,SecurePass123
bob@example.com,Bob Smith,creator,SecurePass456
`;

function downloadCsvTemplate() {
  const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'axis_users_import_template.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// ── CSV Import Modal ──────────────────────────────────────────────────────────
interface ImportResult {
  created: number;
  skipped: number;
  errors: string[];
  created_users: string[];
}

function CsvImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Record<string, string>[]>([]);
  const [parseError, setParseError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [apiError, setApiError] = useState('');

  const handleFile = (f: File) => {
    setFile(f);
    setResult(null);
    setApiError('');
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? '';
      const lines = text.split(/\r?\n/).filter(Boolean);
      if (lines.length < 2) { setParseError('CSV must have a header row and at least one data row.'); setPreview([]); return; }
      const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
      if (!headers.includes('email')) { setParseError('CSV must have an "email" column.'); setPreview([]); return; }
      setParseError('');
      const rows = lines.slice(1, 6).map((line) => {
        const vals = line.split(',').map((v) => v.trim());
        return Object.fromEntries(headers.map((h, i) => [h, vals[i] ?? '']));
      });
      setPreview(rows);
    };
    reader.readAsText(f);
  };

  const handleImport = async () => {
    if (!file) return;
    setUploading(true);
    setApiError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/admin/users/bulk-import', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || 'Import failed');
      setResult(data as ImportResult);
      onImported();
    } catch (err: any) {
      setApiError(err.message || 'Import failed');
    } finally {
      setUploading(false);
    }
  };

  const PREVIEW_HEADERS = ['email', 'full_name', 'role', 'password'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-2xl mx-4 p-6 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-blue-50 flex items-center justify-center">
              <Upload className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <h2 className="font-bold text-primary text-lg">Import Users from CSV</h2>
              <p className="text-xs text-muted-foreground">Columns: email, full_name, role, password</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>

        {/* Template download */}
        <div className="flex items-center justify-between p-3 bg-muted/60 rounded-[var(--radius)] mb-4">
          <p className="text-sm text-muted-foreground">
            Need a template? Download the sample CSV to get started.
          </p>
          <button
            onClick={downloadCsvTemplate}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-border rounded-[var(--radius)] hover:bg-muted transition-colors text-muted-foreground"
          >
            <Download className="w-3.5 h-3.5" /> Download template
          </button>
        </div>

        {/* Drop zone */}
        {!result && (
          <>
            <div
              onClick={() => fileRef.current?.click()}
              onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
              onDragOver={(e) => e.preventDefault()}
              className="border-2 border-dashed border-border rounded-[var(--radius)] p-8 text-center cursor-pointer hover:bg-muted/40 transition-colors mb-4"
            >
              <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              {file ? (
                <p className="text-sm font-medium text-primary">{file.name}</p>
              ) : (
                <p className="text-sm text-muted-foreground">Click to upload or drag & drop a CSV file</p>
              )}
              <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
            </div>

            {parseError && (
              <div className="flex items-center gap-2 text-red-600 text-sm mb-4">
                <AlertCircle className="w-4 h-4" /> {parseError}
              </div>
            )}

            {/* Preview */}
            {preview.length > 0 && (
              <div className="mb-4">
                <p className="section-label mb-2">Preview (first {preview.length} rows)</p>
                <div className="overflow-x-auto rounded-[var(--radius)] border border-border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted/60">
                      <tr>
                        {PREVIEW_HEADERS.map((h) => (
                          <th key={h} className="px-3 py-2 text-left font-semibold uppercase tracking-wide text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((row, i) => (
                        <tr key={i} className="border-t border-border">
                          {PREVIEW_HEADERS.map((h) => (
                            <td key={h} className="px-3 py-2 text-foreground truncate max-w-[140px]">
                              {h === 'password' ? '••••••••' : (row[h] || '—')}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {apiError && (
              <div className="flex items-center gap-2 text-red-600 text-sm mb-4">
                <AlertCircle className="w-4 h-4" /> {apiError}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 justify-end">
              <button onClick={onClose} className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors">
                Cancel
              </button>
              <button
                onClick={handleImport}
                disabled={!file || !!parseError || uploading}
                className="flex items-center gap-2 px-5 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {uploading ? 'Importing…' : 'Import Users'}
              </button>
            </div>
          </>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="enterprise-card p-4 text-center">
                <p className="text-3xl font-bold text-green-600">{result.created}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1">Users Created</p>
              </div>
              <div className="enterprise-card p-4 text-center">
                <p className="text-3xl font-bold text-orange-600">{result.skipped}</p>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1">Skipped</p>
              </div>
            </div>

            {result.created_users.length > 0 && (
              <div className="bg-green-50 border border-green-200 rounded-[var(--radius)] p-3">
                <p className="text-xs font-semibold text-green-700 mb-1 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Created accounts
                </p>
                <ul className="text-xs text-green-700 space-y-0.5 max-h-32 overflow-y-auto">
                  {result.created_users.map((email) => <li key={email}>• {email}</li>)}
                </ul>
              </div>
            )}

            {result.errors.length > 0 && (
              <div className="bg-orange-50 border border-orange-200 rounded-[var(--radius)] p-3">
                <p className="text-xs font-semibold text-orange-700 mb-1 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> Warnings / Skipped
                </p>
                <ul className="text-xs text-orange-700 space-y-0.5 max-h-32 overflow-y-auto">
                  {result.errors.map((e, i) => <li key={i}>• {e}</li>)}
                </ul>
              </div>
            )}

            <div className="flex justify-end">
              <button
                onClick={onClose}
                className="px-5 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function UsersList() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [showCsvImport, setShowCsvImport] = useState(false);
  const [editUser, setEditUser] = useState<AxisUser | null>(null);
  const [deactivateUser, setDeactivateUser] = useState<AxisUser | null>(null);
  const [deleteUser, setDeleteUser] = useState<AxisUser | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [mutError, setMutError] = useState('');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery<UsersResponse>({
    queryKey: ['admin', 'users'],
    queryFn: async () => {
      const res = await fetch('/api/admin/users');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
    refetchInterval: 30_000,
  });

  const createMut = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const res = await fetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to create user');
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      setShowCreate(false);
      setMutError('');
    },
    onError: (e: Error) => setMutError(e.message),
  });

  const updateMut = useMutation({
    mutationFn: async ({ id, ...body }: { id: string } & Record<string, unknown>) => {
      const res = await fetch(`/api/admin/users/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to update user');
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      setEditUser(null);
      setMutError('');
    },
    onError: (e: Error) => setMutError(e.message),
  });

  const deactivateMut = useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/admin/users/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed');
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      setDeactivateUser(null);
    },
  });

  const purgeMut = useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/admin/users/${id}/purge`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to delete user');
      }
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      setDeleteUser(null);
      setDeleteConfirmText('');
    },
  });

  const allUsers = data?.users ?? [];
  const total = data?.total ?? 0;
  const byRole = {
    admin:   allUsers.filter((u) => u.role === 'admin').length,
    creator: allUsers.filter((u) => u.role === 'creator').length,
    learner: allUsers.filter((u) => u.role === 'learner').length,
  };
  const filtered = allUsers.filter((u) => {
    const matchRole = roleFilter === 'all' || u.role === roleFilter;
    const matchSearch = !search ||
      (u.full_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase());
    return matchRole && matchSearch;
  });
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const users = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const handleSearch = (v: string) => { setSearch(v); setPage(0); };
  const handleRoleFilter = (v: string) => { setRoleFilter(v); setPage(0); };

  return (
    <div>
      <Header
        subtitle="All platform users and their access levels"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCsvImport(true)}
              className="flex items-center gap-2 px-4 py-2 border border-border rounded-[var(--radius)] text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            >
              <Upload className="w-4 h-4" />
              Import CSV
            </button>
            <button
              onClick={() => { setMutError(''); setShowCreate(true); }}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              New User
            </button>
          </div>
        }
      />

      <div className="page-padding">
        {/* Role summary */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {Object.entries(ROLE_META).map(([role, meta]) => {
            const Icon = meta.icon;
            return (
              <div key={role} className="enterprise-card flex items-center gap-3">
                <div className={cn('w-9 h-9 rounded-full flex items-center justify-center', meta.bg)}>
                  <Icon className={cn('w-4 h-4', meta.color)} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">{byRole[role as keyof typeof byRole]}</p>
                  <p className="text-xs text-muted-foreground">{meta.label}s</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Search + filter row */}
        <div className="flex gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Search by name or email…"
              className="w-full pl-10 pr-4 py-2.5 rounded-[var(--radius)] border border-border bg-background
                text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <select
            value={roleFilter}
            onChange={(e) => handleRoleFilter(e.target.value)}
            className="px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background text-sm
              focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="all">All roles</option>
            <option value="admin">Admin</option>
            <option value="creator">Creator</option>
            <option value="learner">Learner</option>
          </select>
        </div>

        {/* Users table */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : users.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <Users className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">No users yet</p>
            <p className="text-sm text-muted-foreground mb-4">Create your first user to get started.</p>
            <button
              onClick={() => { setMutError(''); setShowCreate(true); }}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create First User
            </button>
          </div>
        ) : (
          <div className="enterprise-card overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  {['User', 'Role', 'Status', 'Last Login', 'Joined', ''].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground first:w-auto last:w-20">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((user) => {
                  const roleMeta = ROLE_META[user.role];
                  const Icon = roleMeta?.icon ?? Users;
                  return (
                    <tr key={user.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <span className="text-xs font-semibold text-primary">
                              {getInitials(user.full_name || user.email)}
                            </span>
                          </div>
                          <div className="min-w-0">
                            <p className="font-medium text-sm text-foreground truncate">
                              {user.full_name || '—'}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          'inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border capitalize',
                          roleMeta?.badge
                        )}>
                          <Icon className="w-3 h-3" />
                          {roleMeta?.label ?? user.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          'text-xs px-2.5 py-1 rounded-full border',
                          user.is_active
                            ? 'border-green-400 text-green-600 bg-green-50'
                            : 'border-border text-muted-foreground bg-muted'
                        )}>
                          {user.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {timeAgo(user.last_login_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(user.created_at).toLocaleDateString('en-US', {
                          year: 'numeric', month: 'short', day: 'numeric',
                        })}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 justify-end">
                          <button
                            onClick={() => { setMutError(''); setEditUser(user); }}
                            title="Edit user"
                            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-primary transition-colors"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          {user.is_active && (
                            <button
                              onClick={() => setDeactivateUser(user)}
                              title="Deactivate user"
                              className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-orange-500 transition-colors"
                            >
                              <UserX className="w-3.5 h-3.5" />
                            </button>
                          )}
                          <button
                            onClick={() => { setDeleteConfirmText(''); setDeleteUser(user); }}
                            title="Permanently delete user and all data"
                            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-red-700 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="px-4 py-3 border-t border-border">
              <p className="text-xs text-muted-foreground">{total} total user{total !== 1 ? 's' : ''}</p>
            </div>
          </div>
        )}

        {/* Pagination */}
        {!isLoading && totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length} users
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
              >Previous</button>
              <span className="text-sm text-muted-foreground">{page + 1} / {totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1.5 text-sm border border-border rounded-[var(--radius)] hover:bg-muted disabled:opacity-40 transition-colors"
              >Next</button>
            </div>
          </div>
        )}
      </div>

      {/* CSV Import modal */}
      {showCsvImport && (
        <CsvImportModal
          onClose={() => setShowCsvImport(false)}
          onImported={() => {
            qc.invalidateQueries({ queryKey: ['admin', 'users'] });
            setShowCsvImport(false);
          }}
        />
      )}

      {/* Create modal */}
      {showCreate && (
        <UserModal
          onClose={() => { setShowCreate(false); setMutError(''); }}
          onSave={(data) => createMut.mutate(data)}
          saving={createMut.isPending}
          error={mutError}
        />
      )}

      {/* Edit modal */}
      {editUser && (
        <UserModal
          user={editUser}
          onClose={() => { setEditUser(null); setMutError(''); }}
          onSave={(data) => updateMut.mutate({ id: editUser.id, ...data })}
          saving={updateMut.isPending}
          error={mutError}
        />
      )}

      {/* Deactivate confirmation */}
      {deactivateUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-sm p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                <AlertCircle className="w-4 h-4 text-red-600" />
              </div>
              <div>
                <h3 className="font-bold text-primary">Deactivate User</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Deactivating <strong>{deactivateUser.full_name || deactivateUser.email}</strong> will
                  prevent them from logging in. Their data will be preserved.
                </p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeactivateUser(null)}
                className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deactivateMut.mutate(deactivateUser.id)}
                disabled={deactivateMut.isPending}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-[var(--radius)] hover:bg-red-700 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {deactivateMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Deactivate
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Permanent Delete confirmation */}
      {deleteUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-background border border-red-200 rounded-[var(--radius)] shadow-xl w-full max-w-sm p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Trash2 className="w-4 h-4 text-red-700" />
              </div>
              <div>
                <h3 className="font-bold text-red-700">Delete User Permanently</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  This will permanently delete <strong>{deleteUser.full_name || deleteUser.email}</strong> and
                  all their data — spaces, content, chat history, quiz attempts, flashcard reviews,
                  team memberships, and access grants. <strong>This cannot be undone.</strong>
                </p>
              </div>
            </div>
            <div className="mb-4">
              <label className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Type <span className="font-mono text-red-700 select-all">DELETE</span> to confirm
              </label>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder="DELETE"
                className="w-full border border-red-300 rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-red-400/30 font-mono"
              />
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setDeleteUser(null); setDeleteConfirmText(''); }}
                className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => purgeMut.mutate(deleteUser.id)}
                disabled={deleteConfirmText !== 'DELETE' || purgeMut.isPending}
                className="px-4 py-2 text-sm bg-red-700 text-white rounded-[var(--radius)] hover:bg-red-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {purgeMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}