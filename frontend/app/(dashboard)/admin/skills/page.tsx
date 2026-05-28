'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Layers, Plus, Trash2, Pencil, Loader2, X, Check,
  Search, Archive, ArchiveRestore, FolderOpen, Tag,
} from 'lucide-react';
import { toast } from 'sonner';

// ── Types ─────────────────────────────────────────────────────────────────────

interface SkillCategory {
  id: string;
  name: string;
  skill_count: number;
}

interface Skill {
  id: string;
  name: string;
  description: string | null;
  category_id: string | null;
  category_name: string | null;
  content_tagged_count: number;
  learners_progressing_count: number;
  is_archived: boolean;
  created_at: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const api = {
  getCategories: () =>
    fetch('/api/skills/categories').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  createCategory: (name: string) =>
    fetch('/api/skills/categories', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  updateCategory: (id: string, name: string) =>
    fetch(`/api/skills/categories/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  deleteCategory: (id: string) =>
    fetch(`/api/skills/categories/${id}`, { method: 'DELETE' })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } }),

  getSkills: (search?: string) => {
    const qs = search ? `?search=${encodeURIComponent(search)}` : '';
    return fetch(`/api/skills${qs}`).then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); });
  },
  createSkill: (body: { name: string; category_id?: string | null; description?: string }) =>
    fetch('/api/skills', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  updateSkill: (id: string, body: Partial<{ name: string; category_id: string | null; description: string; is_archived: boolean }>) =>
    fetch(`/api/skills/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  deleteSkill: (id: string) =>
    fetch(`/api/skills/${id}`, { method: 'DELETE' })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } }),
};

// ── Confirm modal ─────────────────────────────────────────────────────────────

function ConfirmModal({
  message,
  onConfirm,
  onCancel,
  loading,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="enterprise-card w-full max-w-md mx-4 p-6">
        <p className="text-sm text-foreground mb-5">{message}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors">Cancel</button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-red-600 text-white rounded-[var(--radius)] hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Skill modal (create / edit) ───────────────────────────────────────────────

function SkillModal({
  skill,
  categories,
  onClose,
  onSave,
  saving,
}: {
  skill?: Skill;
  categories: SkillCategory[];
  onClose: () => void;
  onSave: (data: { name: string; category_id: string | null; description: string }) => void;
  saving: boolean;
}) {
  const [name, setName] = useState(skill?.name ?? '');
  const [catId, setCatId] = useState(skill?.category_id ?? '');
  const [desc, setDesc] = useState(skill?.description ?? '');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="enterprise-card w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold text-sm">{skill ? 'Edit Skill' : 'Create Skill'}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Skill name *</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="e.g. Python, Project Management"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Category (optional)</label>
            <select
              value={catId}
              onChange={(e) => setCatId(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">No category</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Description (optional)</label>
            <textarea
              rows={3}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
              placeholder="Brief description of this skill"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors">Cancel</button>
          <button
            onClick={() => onSave({ name, category_id: catId || null, description: desc })}
            disabled={!name.trim() || saving}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {skill ? 'Save Changes' : 'Create Skill'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Skills tab ────────────────────────────────────────────────────────────────

function SkillsTab({ categories }: { categories: SkillCategory[] }) {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [modalSkill, setModalSkill] = useState<Skill | null | undefined>(undefined);
  const [pendingDelete, setPendingDelete] = useState<Skill | null>(null);

  const { data, isLoading } = useQuery<{ skills: Skill[]; total: number }>({
    queryKey: ['skills', search],
    queryFn: () => api.getSkills(search || undefined),
    placeholderData: (prev) => prev,
  });
  const skills = data?.skills ?? [];

  const createMut = useMutation({
    mutationFn: (body: { name: string; category_id: string | null; description: string }) => api.createSkill(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills'] }); qc.invalidateQueries({ queryKey: ['skills-categories'] }); setModalSkill(undefined); toast.success('Skill created'); },
    onError: (e: any) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string; name: string; category_id: string | null; description: string }) => api.updateSkill(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills'] }); setModalSkill(undefined); toast.success('Skill updated'); },
    onError: (e: any) => toast.error(e.message),
  });

  const archiveMut = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => api.updateSkill(id, { is_archived: archived }),
    onSuccess: (_, vars) => { qc.invalidateQueries({ queryKey: ['skills'] }); toast.success(vars.archived ? 'Skill archived' : 'Skill restored'); },
    onError: (e: any) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteSkill(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills'] }); qc.invalidateQueries({ queryKey: ['skills-categories'] }); setPendingDelete(null); toast.success('Skill deleted'); },
    onError: (e: any) => { toast.error(e.message); setPendingDelete(null); },
  });

  return (
    <div className="space-y-4">
      {modalSkill !== undefined && (
        <SkillModal
          skill={modalSkill ?? undefined}
          categories={categories}
          onClose={() => setModalSkill(undefined)}
          onSave={(data) => {
            if (modalSkill) {
              updateMut.mutate({ id: modalSkill.id, ...data });
            } else {
              createMut.mutate(data);
            }
          }}
          saving={createMut.isPending || updateMut.isPending}
        />
      )}
      {pendingDelete && (
        <ConfirmModal
          message={`Delete skill "${pendingDelete.name}"? This will also remove all associated content tags and skill progress.`}
          onConfirm={() => deleteMut.mutate(pendingDelete.id)}
          onCancel={() => setPendingDelete(null)}
          loading={deleteMut.isPending}
        />
      )}

      <div className="enterprise-card p-0 overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 border-b border-border">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="Search skills…"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                toast.info('Bulk CSV import coming soon');
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-border rounded-[var(--radius)] hover:bg-muted transition-colors text-muted-foreground"
            >
              <Layers className="w-3 h-3" /> Bulk Import CSV
            </button>
            <button
              onClick={() => setModalSkill(null)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-3 h-3" /> Create Skill
            </button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
        ) : skills.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <Tag className="w-8 h-8 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground">{search ? 'No skills match your search.' : 'No skills yet.'}</p>
          </div>
        ) : (
          <>
            {/* Table header */}
            <div className="hidden sm:grid grid-cols-[1fr_160px_100px_100px_80px_110px] gap-3 px-5 py-2 bg-muted/50">
              {['Skill Name', 'Category', 'Tagged', 'Learners', 'Archived', 'Actions'].map((h) => (
                <span key={h} className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{h}</span>
              ))}
            </div>
            <div className="divide-y divide-border">
              {skills.map((sk) => (
                <div
                  key={sk.id}
                  className={cn('grid grid-cols-1 sm:grid-cols-[1fr_160px_100px_100px_80px_110px] gap-2 sm:gap-3 items-center px-5 py-3', sk.is_archived && 'opacity-60')}
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">{sk.name}</p>
                    {sk.description && <p className="text-xs text-muted-foreground truncate max-w-xs">{sk.description}</p>}
                  </div>
                  <span className="text-xs text-muted-foreground">{sk.category_name ?? '—'}</span>
                  <span className="text-xs text-muted-foreground">{sk.content_tagged_count}</span>
                  <span className="text-xs text-muted-foreground">{sk.learners_progressing_count}</span>
                  <span className={cn('text-xs font-medium', sk.is_archived ? 'text-amber-600' : 'text-green-600')}>
                    {sk.is_archived ? 'Archived' : 'Active'}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setModalSkill(sk)}
                      className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-[var(--radius)] transition-colors"
                      title="Edit"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => archiveMut.mutate({ id: sk.id, archived: !sk.is_archived })}
                      disabled={archiveMut.isPending}
                      className="p-1.5 text-muted-foreground hover:text-amber-600 hover:bg-amber-50 rounded-[var(--radius)] transition-colors"
                      title={sk.is_archived ? 'Restore' : 'Archive'}
                    >
                      {sk.is_archived ? <ArchiveRestore className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                    </button>
                    <button
                      onClick={() => setPendingDelete(sk)}
                      className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-[var(--radius)] transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Categories tab ─────────────────────────────────────────────────────────────

function CategoriesTab() {
  const qc = useQueryClient();
  const [newName, setNewName] = useState('');
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [pendingDelete, setPendingDelete] = useState<SkillCategory | null>(null);

  const { data: cats = [], isLoading } = useQuery<SkillCategory[]>({
    queryKey: ['skills-categories'],
    queryFn: api.getCategories,
  });

  const createMut = useMutation({
    mutationFn: (name: string) => api.createCategory(name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills-categories'] }); setNewName(''); toast.success('Category created'); },
    onError: (e: any) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.updateCategory(id, name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills-categories'] }); setEditId(null); toast.success('Category updated'); },
    onError: (e: any) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteCategory(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['skills-categories'] }); qc.invalidateQueries({ queryKey: ['skills'] }); setPendingDelete(null); toast.success('Category deleted'); },
    onError: (e: any) => {
      if ((e as any).status === 409 || e.message?.toLowerCase().includes('skill')) {
        toast.error('Move or delete all skills in this category first.');
      } else {
        toast.error(e.message);
      }
      setPendingDelete(null);
    },
  });

  if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-4">
      {pendingDelete && (
        <ConfirmModal
          message={
            pendingDelete.skill_count > 0
              ? `Cannot delete "${pendingDelete.name}" — it has ${pendingDelete.skill_count} skill(s). Move or delete them first.`
              : `Delete category "${pendingDelete.name}"?`
          }
          onConfirm={() => pendingDelete.skill_count > 0 ? setPendingDelete(null) : deleteMut.mutate(pendingDelete.id)}
          onCancel={() => setPendingDelete(null)}
          loading={deleteMut.isPending}
        />
      )}

      <div className="enterprise-card p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <p className="font-semibold text-sm text-foreground mb-3">Skill Categories</p>
          {/* Inline create */}
          <div className="flex items-center gap-2">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && newName.trim()) createMut.mutate(newName.trim()); }}
              className="flex-1 max-w-xs px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="New category name…"
            />
            <button
              onClick={() => { if (newName.trim()) createMut.mutate(newName.trim()); }}
              disabled={!newName.trim() || createMut.isPending}
              className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {createMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Add
            </button>
          </div>
        </div>

        {cats.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <FolderOpen className="w-8 h-8 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground">No categories yet. Create one above.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {cats.map((cat) => (
              <div key={cat.id} className="flex items-center gap-3 px-5 py-3">
                {editId === cat.id ? (
                  <>
                    <input
                      autoFocus
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') updateMut.mutate({ id: cat.id, name: editName });
                        if (e.key === 'Escape') setEditId(null);
                      }}
                      className="flex-1 px-2 py-1.5 text-sm border border-primary rounded-[var(--radius)] bg-background focus:outline-none"
                    />
                    <button
                      onClick={() => updateMut.mutate({ id: cat.id, name: editName })}
                      disabled={!editName.trim() || updateMut.isPending}
                      className="p-1.5 text-green-600 hover:bg-green-50 rounded-[var(--radius)] transition-colors"
                    >
                      {updateMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                    </button>
                    <button onClick={() => setEditId(null)} className="p-1.5 text-muted-foreground hover:bg-muted rounded-[var(--radius)] transition-colors">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <FolderOpen className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <span className="flex-1 text-sm font-medium text-foreground">{cat.name}</span>
                    <span className="text-xs text-muted-foreground">{cat.skill_count} skill{cat.skill_count !== 1 ? 's' : ''}</span>
                    <button
                      onClick={() => { setEditId(cat.id); setEditName(cat.name); }}
                      className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-[var(--radius)] transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setPendingDelete(cat)}
                      className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-[var(--radius)] transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SkillsLibraryPage() {
  const [tab, setTab] = useState<'skills' | 'categories'>('skills');

  const { data: cats = [] } = useQuery<SkillCategory[]>({
    queryKey: ['skills-categories'],
    queryFn: api.getCategories,
  });

  return (
    <div>
      <Header
        title="Skills Library"
        subtitle="Manage skills and categories used across your organisation"
      />
      <div className="page-padding max-w-5xl space-y-6">
        {/* Tabs */}
        <div className="flex items-center gap-1 p-1 bg-muted rounded-[var(--radius)] w-fit">
          {([
            { key: 'skills', label: 'Skills', icon: Tag },
            { key: 'categories', label: 'Categories', icon: FolderOpen },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-[calc(var(--radius)-2px)] transition-colors',
                tab === key
                  ? 'bg-background text-primary shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>

        {tab === 'skills' && <SkillsTab categories={cats} />}
        {tab === 'categories' && <CategoriesTab />}
      </div>
    </div>
  );
}
