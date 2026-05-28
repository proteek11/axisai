'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Award, Plus, Loader2, Trash2, Download, Search, X,
  ChevronLeft, ChevronRight, CheckCircle2, Edit2, Upload,
  LayoutTemplate, ListChecks, Image as ImageIcon, Save, SendHorizonal, User,
} from 'lucide-react';
import { toast } from 'sonner';

// ── Types ──────────────────────────────────────────────────────────────────

interface CertTemplate {
  id: string;
  name: string;
  type_tag: string;
  layout_style: string;
  title_text: string;
  body_text: string | null;
  logo_path: string | null;
  signature_name: string | null;
  signature_title: string | null;
  is_active: boolean;
  created_at: string;
}

interface Certificate {
  certificate_id: string;
  space_id: string;
  space_title: string;
  learner_name: string;
  learner_email: string;
  issued_at: string;
}

const TYPE_TAGS = ['completion', 'participation', 'achievement', 'custom'];
const LAYOUT_STYLES = ['classic', 'modern', 'minimal', 'branded'];
const PAGE_SIZE = 50;

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}


// ── Issue Manual Certificate Modal ────────────────────────────────────────

function IssueManualCertModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [spaceSearch, setSpaceSearch] = useState('');
  const [userSearch, setUserSearch] = useState('');
  const [selectedSpaceId, setSelectedSpaceId] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('');

  const { data: spacesData, isLoading: spacesLoading } = useQuery<{ spaces: Array<{ id: string; title: string }> }>({
    queryKey: ['admin-spaces-list'],
    queryFn: async () => {
      const r = await fetch('/api/spaces');
      if (!r.ok) return { spaces: [] };
      return r.json();
    },
  });

  const { data: usersData, isLoading: usersLoading } = useQuery<{ users: Array<{ id: string; email: string; first_name: string; last_name: string }> }>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const r = await fetch('/api/admin/users');
      if (!r.ok) return { users: [] };
      return r.json();
    },
  });

  const filteredSpaces = (spacesData?.spaces ?? []).filter(s =>
    s.title.toLowerCase().includes(spaceSearch.toLowerCase())
  );
  const filteredUsers = (usersData?.users ?? []).filter(u => {
    const name = `${u.first_name ?? ''} ${u.last_name ?? ''} ${u.email}`.toLowerCase();
    return name.includes(userSearch.toLowerCase());
  });

  const issueMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch('/api/admin/certificates/issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ space_id: selectedSpaceId, user_id: selectedUserId }),
      });
      if (!r.ok) throw new Error((await r.json()).error || 'Failed');
      return r.json();
    },
    onSuccess: (data) => {
      toast.success(`Certificate issued to ${data.learner_name}`);
      queryClient.invalidateQueries({ queryKey: ['admin-issued-certs'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-lg mx-4 shadow-xl flex flex-col max-h-[90dvh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <SendHorizonal className="w-4 h-4 text-primary" />
            <p className="font-semibold text-sm">Issue Certificate Manually</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <p className="text-xs text-muted-foreground">
            Award a certificate to any learner for any space — bypasses completion requirements.
          </p>

          {/* Space picker */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Learning Space</label>
            <input
              value={spaceSearch}
              onChange={e => setSpaceSearch(e.target.value)}
              placeholder="Search space…"
              className="mt-2 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {spacesLoading ? (
              <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
            ) : (
              <div className="mt-2 space-y-1 max-h-36 overflow-y-auto border border-border rounded-[var(--radius)] divide-y divide-border">
                {filteredSpaces.slice(0, 10).map(s => (
                  <label key={s.id} className={`flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors ${selectedSpaceId === s.id ? 'bg-primary/5' : 'hover:bg-muted/50'}`}>
                    <input type="radio" name="space" value={s.id} checked={selectedSpaceId === s.id} onChange={() => setSelectedSpaceId(s.id)} className="accent-primary" />
                    <span className="text-sm truncate">{s.title}</span>
                  </label>
                ))}
                {filteredSpaces.length === 0 && <p className="text-xs text-muted-foreground p-3 text-center">No spaces found</p>}
              </div>
            )}
          </div>

          {/* User picker */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Learner</label>
            <input
              value={userSearch}
              onChange={e => setUserSearch(e.target.value)}
              placeholder="Name or email…"
              className="mt-2 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {usersLoading ? (
              <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
            ) : (
              <div className="mt-2 space-y-1 max-h-36 overflow-y-auto border border-border rounded-[var(--radius)] divide-y divide-border">
                {filteredUsers.slice(0, 15).map(u => (
                  <label key={u.id} className={`flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors ${selectedUserId === u.id ? 'bg-primary/5' : 'hover:bg-muted/50'}`}>
                    <input type="radio" name="learner" value={u.id} checked={selectedUserId === u.id} onChange={() => setSelectedUserId(u.id)} className="accent-primary" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{[u.first_name, u.last_name].filter(Boolean).join(' ') || u.email}</p>
                      <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                    </div>
                  </label>
                ))}
                {filteredUsers.length === 0 && <p className="text-xs text-muted-foreground p-3 text-center">No users found</p>}
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-2 px-5 py-4 border-t border-border justify-end">
          <button onClick={onClose} className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors">Cancel</button>
          <button
            onClick={() => issueMutation.mutate()}
            disabled={issueMutation.isPending || !selectedSpaceId || !selectedUserId}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            {issueMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Issue Certificate
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Template Form ─────────────────────────────────────────────────────────

function TemplateForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<CertTemplate>;
  onSave: (data: Partial<CertTemplate>) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    type_tag: initial?.type_tag ?? 'completion',
    layout_style: initial?.layout_style ?? 'classic',
    title_text: initial?.title_text ?? 'Certificate of Completion',
    body_text: initial?.body_text ?? 'This certifies that {{learner_name}} has successfully completed {{space_title}} on {{date}}.',
    signature_name: initial?.signature_name ?? '',
    signature_title: initial?.signature_title ?? '',
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Template Name *</label>
          <input
            value={form.name}
            onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
            placeholder="e.g. EDZLMS Completion Certificate"
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Certificate Type</label>
          <select
            value={form.type_tag}
            onChange={e => setForm(p => ({ ...p, type_tag: e.target.value }))}
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          >
            {TYPE_TAGS.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Layout Style</label>
          <select
            value={form.layout_style}
            onChange={e => setForm(p => ({ ...p, layout_style: e.target.value }))}
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          >
            {LAYOUT_STYLES.map(l => <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>)}
          </select>
        </div>
        <div className="col-span-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Certificate Title</label>
          <input
            value={form.title_text}
            onChange={e => setForm(p => ({ ...p, title_text: e.target.value }))}
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="col-span-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Body Text
            <span className="ml-2 normal-case font-normal text-muted-foreground/70">
              (use &#123;&#123;learner_name&#125;&#125;, &#123;&#123;space_title&#125;&#125;, &#123;&#123;date&#125;&#125;)
            </span>
          </label>
          <textarea
            rows={3}
            value={form.body_text}
            onChange={e => setForm(p => ({ ...p, body_text: e.target.value }))}
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Signatory Name</label>
          <input
            value={form.signature_name}
            onChange={e => setForm(p => ({ ...p, signature_name: e.target.value }))}
            placeholder="e.g. John Smith"
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Signatory Title</label>
          <input
            value={form.signature_title}
            onChange={e => setForm(p => ({ ...p, signature_title: e.target.value }))}
            placeholder="e.g. Director of Learning"
            className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      <div className="flex gap-2 justify-end pt-2">
        <button
          onClick={onCancel}
          className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => {
            if (!form.name.trim()) { toast.error('Template name is required'); return; }
            onSave(form);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Save className="w-4 h-4" />
          Save Template
        </button>
      </div>
    </div>
  );
}

// ── Templates Tab ─────────────────────────────────────────────────────────

function TemplatesTab() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<CertTemplate | null>(null);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);

  const { data: templates = [], isLoading } = useQuery<CertTemplate[]>({
    queryKey: ['cert-templates'],
    queryFn: async () => {
      const r = await fetch('/api/admin/certificate-templates');
      if (!r.ok) throw new Error('Failed to load templates');
      return r.json();
    },
  });

  const createMutation = useMutation({
    mutationFn: async (body: Partial<CertTemplate>) => {
      const r = await fetch('/api/admin/certificate-templates', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error((await r.json()).error || 'Failed');
      return r.json();
    },
    onSuccess: () => {
      toast.success('Template created');
      setShowCreate(false);
      queryClient.invalidateQueries({ queryKey: ['cert-templates'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, body }: { id: string; body: Partial<CertTemplate> }) => {
      const r = await fetch(`/api/admin/certificate-templates/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error((await r.json()).error || 'Failed');
      return r.json();
    },
    onSuccess: () => {
      toast.success('Template updated');
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ['cert-templates'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const r = await fetch(`/api/admin/certificate-templates/${id}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) throw new Error('Failed to delete');
    },
    onSuccess: () => {
      toast.success('Template deleted');
      queryClient.invalidateQueries({ queryKey: ['cert-templates'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const uploadLogo = async (templateId: string, file: File) => {
    setUploadingFor(templateId);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(`/api/admin/certificate-templates/${templateId}/logo`, { method: 'POST', body: fd });
      if (!r.ok) throw new Error('Upload failed');
      toast.success('Logo uploaded');
      queryClient.invalidateQueries({ queryKey: ['cert-templates'] });
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setUploadingFor(null);
    }
  };

  const LAYOUT_COLORS: Record<string, string> = {
    classic: 'bg-amber-50 text-amber-700 border-amber-200',
    modern: 'bg-blue-50 text-blue-700 border-blue-200',
    minimal: 'bg-gray-50 text-gray-600 border-gray-200',
    branded: 'bg-purple-50 text-purple-700 border-purple-200',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {templates.length} template{templates.length !== 1 ? 's' : ''} — creators can pick these when adding certificates to a learning space.
        </p>
        <button
          onClick={() => { setShowCreate(true); setEditing(null); }}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Template
        </button>
      </div>

      {/* Create form */}
      {showCreate && !editing && (
        <div className="border border-border rounded-[var(--radius)] p-5 bg-muted/30">
          <p className="text-sm font-semibold mb-4">New Certificate Template</p>
          <TemplateForm
            onSave={(data) => createMutation.mutate(data)}
            onCancel={() => setShowCreate(false)}
          />
        </div>
      )}

      {/* Template cards */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading templates…
        </div>
      ) : templates.length === 0 && !showCreate ? (
        <div className="text-center py-12 border border-dashed border-border rounded-[var(--radius)]">
          <LayoutTemplate className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm font-medium text-muted-foreground">No templates yet</p>
          <p className="text-xs text-muted-foreground/70 mt-1">Create your first certificate template above.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {templates.map(tmpl => (
            <div key={tmpl.id} className="border border-border rounded-[var(--radius)] bg-card">
              {editing?.id === tmpl.id ? (
                <div className="p-5">
                  <p className="text-sm font-semibold mb-4">Edit Template</p>
                  <TemplateForm
                    initial={editing}
                    onSave={(data) => updateMutation.mutate({ id: tmpl.id, body: data })}
                    onCancel={() => setEditing(null)}
                  />
                </div>
              ) : (
                <div className="p-4 flex items-start gap-4">
                  {/* Logo thumbnail */}
                  <div className="w-14 h-14 rounded-lg border border-border bg-muted flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {tmpl.logo_path ? (
                      <img src={tmpl.logo_path} alt="logo" className="w-full h-full object-contain p-1" />
                    ) : (
                      <ImageIcon className="w-5 h-5 text-muted-foreground/40" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-sm text-foreground">{tmpl.name}</p>
                      <span className={cn('text-[10px] px-2 py-0.5 rounded-full border font-medium uppercase tracking-wide', LAYOUT_COLORS[tmpl.layout_style] ?? 'bg-muted text-muted-foreground border-border')}>
                        {tmpl.layout_style}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-muted text-muted-foreground uppercase tracking-wide">
                        {tmpl.type_tag}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{tmpl.title_text}</p>
                    {tmpl.signature_name && (
                      <p className="text-xs text-muted-foreground/70 mt-0.5">
                        Signed by: {tmpl.signature_name}{tmpl.signature_title ? `, ${tmpl.signature_title}` : ''}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {/* Upload logo */}
                    <label className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer" title="Upload logo">
                      {uploadingFor === tmpl.id
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Upload className="w-4 h-4" />
                      }
                      <input
                        type="file" accept="image/*" className="hidden"
                        onChange={e => { const f = e.target.files?.[0]; if (f) uploadLogo(tmpl.id, f); e.target.value = ''; }}
                      />
                    </label>
                    <button
                      onClick={() => { setEditing(tmpl); setShowCreate(false); }}
                      className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      title="Edit"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(tmpl.id)}
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded-lg hover:bg-red-50 text-muted-foreground hover:text-red-600 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Issued Certificates Tab ───────────────────────────────────────────────

function IssuedTab() {
  const [showIssueModal, setShowIssueModal] = useState(false);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [confirmRevoke, setConfirmRevoke] = useState<Certificate | null>(null);

  const offset = page * PAGE_SIZE;
  const { data, isLoading } = useQuery<{ total: number; certificates: Certificate[] }>({
    queryKey: ['admin-certificates', page, search],
    queryFn: async () => {
      const p = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (search) p.set('search', search);
      const r = await fetch(`/api/admin/certificates?${p}`);
      if (!r.ok) throw new Error('Failed to load');
      return r.json();
    },
    placeholderData: (prev) => prev,
  });

  const revokeMutation = useMutation({
    mutationFn: async (certId: string) => {
      const r = await fetch(`/api/admin/certificates/${certId}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) throw new Error('Failed to revoke');
    },
    onSuccess: () => {
      toast.success('Certificate revoked');
      setConfirmRevoke(null);
      queryClient.invalidateQueries({ queryKey: ['admin-certificates'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const certs = data?.certificates ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const filtered = search
    ? certs.filter(c =>
        c.learner_name?.toLowerCase().includes(search.toLowerCase()) ||
        c.learner_email?.toLowerCase().includes(search.toLowerCase()) ||
        c.space_title?.toLowerCase().includes(search.toLowerCase())
      )
    : certs;

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { setSearch(searchInput); setPage(0); } }}
            placeholder="Search learner or space…"
            className="pl-9 pr-4 py-2 w-full border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        {search && (
          <button onClick={() => { setSearch(''); setSearchInput(''); setPage(0); }}
            className="p-2 rounded-[var(--radius)] hover:bg-muted transition-colors text-muted-foreground">
            <X className="w-4 h-4" />
          </button>
        )}
        <span className="text-xs text-muted-foreground ml-auto">{total} total</span>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 border border-dashed border-border rounded-[var(--radius)]">
          <Award className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No certificates issued yet.</p>
          <button
            onClick={() => setShowIssueModal(true)}
            className="mt-3 flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-emerald-700 transition-colors mx-auto"
          >
            <SendHorizonal className="w-4 h-4" />
            Issue First Certificate
          </button>
        </div>
      ) : (
        <>
          <div className="border border-border rounded-[var(--radius)] overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Learner</th>
                  <th className="text-left px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground hidden sm:table-cell">Space</th>
                  <th className="text-left px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground hidden md:table-cell">Issued</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {filtered.map(cert => (
                  <tr key={cert.certificate_id} className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{cert.learner_name || '—'}</p>
                      <p className="text-xs text-muted-foreground">{cert.learner_email}</p>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground hidden sm:table-cell">{cert.space_title}</td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{fmtDate(cert.issued_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <a
                          href={`/api/spaces/${cert.space_id}/certificate?user_id=${cert.certificate_id}`}
                          target="_blank"
                          className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                          title="Download"
                        >
                          <Download className="w-4 h-4" />
                        </a>
                        <button
                          onClick={() => setConfirmRevoke(cert)}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-muted-foreground hover:text-red-600 transition-colors"
                          title="Revoke"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs disabled:opacity-40 hover:bg-muted transition-colors"
              >
                <ChevronLeft className="w-3 h-3" /> Previous
              </button>
              <span className="text-xs text-muted-foreground">Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 px-3 py-1.5 border border-border rounded-[var(--radius)] text-xs disabled:opacity-40 hover:bg-muted transition-colors"
              >
                Next <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Revoke confirm */}
      {confirmRevoke && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm mx-4 p-6 shadow-lg">
            <p className="font-semibold text-sm mb-1">Revoke certificate?</p>
            <p className="text-sm text-muted-foreground mb-4">
              This will revoke {confirmRevoke.learner_name}&apos;s certificate for &ldquo;{confirmRevoke.space_title}&rdquo;. This cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setConfirmRevoke(null)}
                className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors">
                Cancel
              </button>
              <button
                onClick={() => revokeMutation.mutate(confirmRevoke.certificate_id)}
                disabled={revokeMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {revokeMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Revoke
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────

export function CertificatesManager() {
  const [tab, setTab] = useState<'templates' | 'issued'>('templates');
  const [showIssueModal, setShowIssueModal] = useState(false);

  return (
    <div className="flex flex-col min-h-screen bg-background">
      <Header title="Certificates" />
      <main className="flex-1 px-6 py-6 max-w-5xl mx-auto w-full">
        {/* Page header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Award className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Certificate Management</h1>
            <p className="text-sm text-muted-foreground">
              Create branded templates — creators pick these when adding certificates to learning spaces.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 border-b border-border">
          {([
            { key: 'templates', label: 'Templates', icon: LayoutTemplate },
            { key: 'issued', label: 'Issued Certificates', icon: ListChecks },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
                tab === key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {tab === 'issued' && (
          <div className="flex justify-end px-0 mb-4">
            <button
              onClick={() => setShowIssueModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-[var(--radius)] text-sm font-medium hover:bg-emerald-700 transition-colors"
            >
              <SendHorizonal className="w-4 h-4" />
              Issue Certificate
            </button>
          </div>
        )}

        {tab === 'templates' ? <TemplatesTab /> : <IssuedTab />}
        {showIssueModal && <IssueManualCertModal onClose={() => setShowIssueModal(false)} />}
      </main>
    </div>
  );
}
