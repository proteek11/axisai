'use client';

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Settings2, Plus, Trash2, Pencil, GripVertical, Loader2,
  AlertTriangle, X, Check, UserPlus, ChevronDown, ChevronRight,
  Target, Building2, Users, RotateCcw, Save,
} from 'lucide-react';
import { toast } from 'sonner';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ProficiencyLevel {
  id: string;
  label: string;
  description: string | null;
  level_order: number;
}

interface OrgRole {
  id: string;
  name: string;
  team_id: string | null;
  team_name: string | null;
  skill_target_count: number;
  is_archived: boolean;
  created_at: string;
}

interface SkillTarget {
  id: string;
  skill_id: string;
  skill_name: string;
  target_level_id: string;
  target_level_label: string;
}

interface SkillOption {
  id: string;
  name: string;
  category_name: string | null;
}

interface Team {
  id: string;
  name: string;
}

interface AxisUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const api = {
  getLevels: () =>
    fetch('/api/org-setup/proficiency-levels').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  createLevel: (body: { label: string; description?: string; level_order: number }) =>
    fetch('/api/org-setup/proficiency-levels', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  updateLevel: (id: string, body: { label?: string; description?: string; level_order?: number }) =>
    fetch(`/api/org-setup/proficiency-levels/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  deleteLevel: (id: string) =>
    fetch(`/api/org-setup/proficiency-levels/${id}`, { method: 'DELETE' })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } }),

  getRoles: () =>
    fetch('/api/org-setup/org-roles').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  createRole: (body: { name: string; team_id?: string | null }) =>
    fetch('/api/org-setup/org-roles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  updateRole: (id: string, body: { name?: string; team_id?: string | null; is_archived?: boolean }) =>
    fetch(`/api/org-setup/org-roles/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  deleteRole: (id: string) =>
    fetch(`/api/org-setup/org-roles/${id}`, { method: 'DELETE' })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } }),

  getRoleTargets: (roleId: string) =>
    fetch(`/api/org-setup/org-roles/${roleId}/skill-targets`).then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  addTarget: (roleId: string, body: { skill_id: string; target_level_id: string }) =>
    fetch(`/api/org-setup/org-roles/${roleId}/skill-targets`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),
  removeTarget: (roleId: string, targetId: string) =>
    fetch(`/api/org-setup/org-roles/${roleId}/skill-targets/${targetId}`, { method: 'DELETE' })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } }),

  assignUserRole: (userId: string, orgRoleId: string) =>
    fetch(`/api/org-setup/users/${userId}/org-role`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ org_role_id: orgRoleId }) })
      .then(async (r) => { if (!r.ok) { const d = await r.json().catch(() => ({})); throw Object.assign(new Error(d.error || 'Failed'), { status: r.status }); } return r.json(); }),

  getTeams: () =>
    fetch('/api/teams').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  getUsers: () =>
    fetch('/api/admin/users').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  getSkills: () =>
    fetch('/api/skills?limit=200').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
};

const DEFAULT_LEVELS = [
  { label: 'Awareness', description: 'Basic awareness of concepts and terminology', level_order: 1 },
  { label: 'Working', description: 'Able to apply skills in standard situations with guidance', level_order: 2 },
  { label: 'Expert', description: 'Deep expertise; can guide others and handle complex scenarios', level_order: 3 },
];

// ── Confirm / Warning modal ────────────────────────────────────────────────────

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
        <div className="flex items-start gap-3 mb-5">
          <div className="w-9 h-9 rounded-full bg-amber-50 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4.5 h-4.5 text-amber-600" />
          </div>
          <p className="text-sm text-foreground pt-1.5">{message}</p>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-red-600 text-white rounded-[var(--radius)] hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Delete anyway
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Proficiency Scale tab ──────────────────────────────────────────────────────

function ProficiencyTab() {
  const qc = useQueryClient();
  const { data: levels = [], isLoading } = useQuery<ProficiencyLevel[]>({
    queryKey: ['proficiency-levels'],
    queryFn: api.getLevels,
  });

  // Local edit state: map id → { label, description }
  const [edits, setEdits] = useState<Record<string, { label: string; description: string }>>({});
  const [pendingDelete, setPendingDelete] = useState<ProficiencyLevel | null>(null);
  const [deleteError, setDeleteError] = useState('');

  const sorted = [...levels].sort((a, b) => a.level_order - b.level_order);

  const createMut = useMutation({
    mutationFn: (body: { label: string; description: string; level_order: number }) => api.createLevel(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['proficiency-levels'] }); toast.success('Level added'); },
    onError: (e: any) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string; label: string; description: string }) => api.updateLevel(id, body),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['proficiency-levels'] });
      setEdits((p) => { const n = { ...p }; delete n[vars.id]; return n; });
      toast.success('Saved');
    },
    onError: (e: any) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteLevel(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['proficiency-levels'] }); setPendingDelete(null); toast.success('Level deleted'); },
    onError: (e: any) => {
      if ((e as any).status === 409) {
        setDeleteError(e.message || 'This level is in use by skill targets.');
      } else {
        toast.error(e.message);
        setPendingDelete(null);
      }
    },
  });

  const seedMut = useMutation({
    mutationFn: async () => {
      // Delete all existing then create defaults
      for (const l of levels) {
        await api.deleteLevel(l.id).catch(() => {});
      }
      for (const d of DEFAULT_LEVELS) {
        await api.createLevel(d);
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['proficiency-levels'] }); toast.success('Restored to defaults'); },
    onError: () => toast.error('Partial restore — some levels may be in use'),
  });

  const getEdit = (lv: ProficiencyLevel) =>
    edits[lv.id] ?? { label: lv.label, description: lv.description ?? '' };

  const handleAdd = () => {
    if (sorted.length >= 6) { toast.warning('Maximum 6 proficiency levels allowed'); return; }
    createMut.mutate({ label: 'New Level', description: '', level_order: sorted.length + 1 });
  };

  if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-4">
      {pendingDelete && (
        <ConfirmModal
          message={deleteError || `Delete level "${pendingDelete.label}"? This cannot be undone.`}
          onConfirm={() => deleteMut.mutate(pendingDelete.id)}
          onCancel={() => { setPendingDelete(null); setDeleteError(''); }}
          loading={deleteMut.isPending}
        />
      )}

      <div className="enterprise-card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <p className="font-semibold text-sm text-foreground">Proficiency Levels</p>
            <p className="text-xs text-muted-foreground mt-0.5">{sorted.length}/6 levels defined</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => seedMut.mutate()}
              disabled={seedMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-border rounded-[var(--radius)] hover:bg-muted transition-colors text-muted-foreground"
            >
              {seedMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
              Default seed
            </button>
            <button
              onClick={handleAdd}
              disabled={sorted.length >= 6 || createMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Plus className="w-3 h-3" /> Add Level
            </button>
          </div>
        </div>

        {sorted.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <Target className="w-8 h-8 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground">No proficiency levels yet.</p>
            <p className="text-xs text-muted-foreground mt-1">Add levels or restore the default seed.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {sorted.map((lv) => {
              const edit = getEdit(lv);
              const isDirty = edit.label !== lv.label || edit.description !== (lv.description ?? '');
              return (
                <div key={lv.id} className="flex items-start gap-3 px-5 py-4">
                  <div className="flex items-center gap-2 mt-2 flex-shrink-0">
                    <GripVertical className="w-4 h-4 text-muted-foreground/50 cursor-grab" />
                    <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                      {lv.level_order}
                    </span>
                  </div>
                  <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input
                      value={edit.label}
                      onChange={(e) => setEdits((p) => ({ ...p, [lv.id]: { ...edit, label: e.target.value } }))}
                      className="px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="Label"
                    />
                    <input
                      value={edit.description}
                      onChange={(e) => setEdits((p) => ({ ...p, [lv.id]: { ...edit, description: e.target.value } }))}
                      className="px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="Description (optional)"
                    />
                  </div>
                  <div className="flex items-center gap-1 mt-1.5 flex-shrink-0">
                    {isDirty && (
                      <button
                        onClick={() => updateMut.mutate({ id: lv.id, ...edit })}
                        disabled={updateMut.isPending}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50"
                      >
                        {updateMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        Save
                      </button>
                    )}
                    <button
                      onClick={() => setPendingDelete(lv)}
                      className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-[var(--radius)] transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Skill Targets sub-section ──────────────────────────────────────────────────

function SkillTargetsSection({ role, levels }: { role: OrgRole; levels: ProficiencyLevel[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [newSkillId, setNewSkillId] = useState('');
  const [newLevelId, setNewLevelId] = useState('');

  const { data: targets = [], isLoading } = useQuery<SkillTarget[]>({
    queryKey: ['role-targets', role.id],
    queryFn: () => api.getRoleTargets(role.id),
    enabled: open,
  });

  const { data: skillsData } = useQuery<{ skills: SkillOption[] }>({
    queryKey: ['skills-list-light'],
    queryFn: api.getSkills,
    enabled: open,
  });
  const skills = skillsData?.skills ?? [];

  const addMut = useMutation({
    mutationFn: () => api.addTarget(role.id, { skill_id: newSkillId, target_level_id: newLevelId }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['role-targets', role.id] }); qc.invalidateQueries({ queryKey: ['org-roles'] }); setNewSkillId(''); setNewLevelId(''); toast.success('Target added'); },
    onError: (e: any) => toast.error(e.message),
  });

  const removeMut = useMutation({
    mutationFn: (targetId: string) => api.removeTarget(role.id, targetId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['role-targets', role.id] }); qc.invalidateQueries({ queryKey: ['org-roles'] }); toast.success('Target removed'); },
    onError: (e: any) => toast.error(e.message),
  });

  const sortedLevels = [...levels].sort((a, b) => a.level_order - b.level_order);
  const canAdd = newSkillId && newLevelId;

  return (
    <div className="mt-2 ml-6 border-l-2 border-primary/20 pl-4">
      <button
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors mb-2"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Target className="w-3 h-3" />
        Skill Targets ({role.skill_target_count})
      </button>

      {open && (
        <div className="space-y-2">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          ) : (
            <>
              {targets.length === 0 && (
                <p className="text-xs text-muted-foreground">No skill targets set for this role.</p>
              )}
              {targets.map((t) => (
                <div key={t.id} className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-foreground">{t.skill_name}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="px-2 py-0.5 bg-primary/10 text-primary rounded-full font-medium">{t.target_level_label}</span>
                  <button
                    onClick={() => removeMut.mutate(t.id)}
                    disabled={removeMut.isPending}
                    className="ml-auto text-muted-foreground hover:text-red-600 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}

              {/* Add target row */}
              <div className="flex items-center gap-2 pt-2 border-t border-border">
                <select
                  value={newSkillId}
                  onChange={(e) => setNewSkillId(e.target.value)}
                  className="flex-1 px-2 py-1.5 text-xs border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">Select skill…</option>
                  {skills.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}{s.category_name ? ` (${s.category_name})` : ''}</option>
                  ))}
                </select>
                <select
                  value={newLevelId}
                  onChange={(e) => setNewLevelId(e.target.value)}
                  className="w-32 px-2 py-1.5 text-xs border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">Level…</option>
                  {sortedLevels.map((l) => (
                    <option key={l.id} value={l.id}>{l.label}</option>
                  ))}
                </select>
                <button
                  onClick={() => addMut.mutate()}
                  disabled={!canAdd || addMut.isPending}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {addMut.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                  Add
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Assign User modal ──────────────────────────────────────────────────────────

function AssignUserModal({
  role,
  onClose,
}: {
  role: OrgRole;
  onClose: () => void;
}) {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const qc = useQueryClient();

  const { data: usersData } = useQuery<{ users: AxisUser[]; total: number }>({
    queryKey: ['admin-users-list'],
    queryFn: api.getUsers,
  });
  const users = usersData?.users ?? [];
  const filtered = users.filter((u) => {
    const q = search.toLowerCase();
    return (u.full_name?.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
  });

  const assignMut = useMutation({
    mutationFn: () => api.assignUserRole(selectedId, role.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); toast.success('Role assigned'); onClose(); },
    onError: (e: any) => toast.error(e.message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="enterprise-card w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-sm">Assign user to "{role.name}"</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>
        <input
          autoFocus
          placeholder="Search users…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary mb-3"
        />
        <div className="max-h-48 overflow-y-auto space-y-1 mb-4">
          {filtered.length === 0 && <p className="text-xs text-muted-foreground py-4 text-center">No users found</p>}
          {filtered.map((u) => (
            <button
              key={u.id}
              onClick={() => setSelectedId(u.id)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] text-sm text-left transition-colors',
                selectedId === u.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted',
              )}
            >
              <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary flex-shrink-0">
                {(u.full_name ?? u.email).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="font-medium truncate">{u.full_name ?? '—'}</p>
                <p className="text-xs text-muted-foreground truncate">{u.email}</p>
              </div>
              {selectedId === u.id && <Check className="w-4 h-4 ml-auto flex-shrink-0" />}
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors">Cancel</button>
          <button
            onClick={() => assignMut.mutate()}
            disabled={!selectedId || assignMut.isPending}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {assignMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Assign Role
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Create/Edit Role modal ──────────────────────────────────────────────────────

function RoleModal({
  role,
  teams,
  onClose,
  onSave,
  saving,
}: {
  role?: OrgRole;
  teams: Team[];
  onClose: () => void;
  onSave: (data: { name: string; team_id: string | null; is_archived: boolean }) => void;
  saving: boolean;
}) {
  const [name, setName] = useState(role?.name ?? '');
  const [teamId, setTeamId] = useState(role?.team_id ?? '');
  const [archived, setArchived] = useState(role?.is_archived ?? false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="enterprise-card w-full max-w-md mx-4 p-6">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold text-sm">{role ? 'Edit Org Role' : 'Create Org Role'}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Role name *</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="e.g. Senior Developer"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Team (optional)</label>
            <select
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">No team</option>
              {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          {role && (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={archived}
                onChange={(e) => setArchived(e.target.checked)}
                className="rounded"
              />
              <span>Archived</span>
            </label>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors">Cancel</button>
          <button
            onClick={() => onSave({ name, team_id: teamId || null, is_archived: archived })}
            disabled={!name.trim() || saving}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {role ? 'Save Changes' : 'Create Role'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Org Roles tab ─────────────────────────────────────────────────────────────

function OrgRolesTab({ levels }: { levels: ProficiencyLevel[] }) {
  const qc = useQueryClient();
  const [modalRole, setModalRole] = useState<OrgRole | null | undefined>(undefined); // undefined = closed
  const [pendingDelete, setPendingDelete] = useState<OrgRole | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [assignRole, setAssignRole] = useState<OrgRole | null>(null);

  const { data: roles = [], isLoading } = useQuery<OrgRole[]>({
    queryKey: ['org-roles'],
    queryFn: api.getRoles,
  });
  const { data: teamsData } = useQuery<{ teams: Team[] }>({
    queryKey: ['teams'],
    queryFn: api.getTeams,
  });
  const teams = teamsData?.teams ?? [];

  const createMut = useMutation({
    mutationFn: (body: { name: string; team_id: string | null; is_archived: boolean }) => api.createRole(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); setModalRole(undefined); toast.success('Role created'); },
    onError: (e: any) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string; name: string; team_id: string | null; is_archived: boolean }) => api.updateRole(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); setModalRole(undefined); toast.success('Role updated'); },
    onError: (e: any) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteRole(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['org-roles'] }); setPendingDelete(null); toast.success('Role deleted'); },
    onError: (e: any) => {
      if ((e as any).status === 409) {
        setDeleteError(e.message || 'Users are assigned to this role.');
      } else {
        toast.error(e.message);
        setPendingDelete(null);
      }
    },
  });

  if (isLoading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-4">
      {modalRole !== undefined && (
        <RoleModal
          role={modalRole ?? undefined}
          teams={teams}
          onClose={() => setModalRole(undefined)}
          onSave={(data) => {
            if (modalRole) {
              updateMut.mutate({ id: modalRole.id, ...data });
            } else {
              createMut.mutate(data);
            }
          }}
          saving={createMut.isPending || updateMut.isPending}
        />
      )}
      {assignRole && (
        <AssignUserModal role={assignRole} onClose={() => setAssignRole(null)} />
      )}
      {pendingDelete && (
        <ConfirmModal
          message={deleteError || `Delete org role "${pendingDelete.name}"? This cannot be undone.`}
          onConfirm={() => deleteMut.mutate(pendingDelete.id)}
          onCancel={() => { setPendingDelete(null); setDeleteError(''); }}
          loading={deleteMut.isPending}
        />
      )}

      <div className="enterprise-card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div>
            <p className="font-semibold text-sm text-foreground">Org Roles</p>
            <p className="text-xs text-muted-foreground mt-0.5">{roles.length} role{roles.length !== 1 ? 's' : ''} defined</p>
          </div>
          <button
            onClick={() => setModalRole(null)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-primary text-white rounded-[var(--radius)] hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-3 h-3" /> Create Role
          </button>
        </div>

        {roles.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <Building2 className="w-8 h-8 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground">No org roles yet.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {/* Header */}
            <div className="hidden sm:grid grid-cols-[1fr_160px_100px_80px_130px] gap-4 px-5 py-2 bg-muted/50">
              {['Role Name', 'Team', 'Targets', 'Archived', 'Actions'].map((h) => (
                <span key={h} className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{h}</span>
              ))}
            </div>
            {roles.map((role) => (
              <div key={role.id} className="px-5 py-3">
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_160px_100px_80px_130px] gap-2 sm:gap-4 items-center">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Building2 className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <span className="text-sm font-medium text-foreground">{role.name}</span>
                  </div>
                  <span className="text-xs text-muted-foreground">{role.team_name ?? '—'}</span>
                  <span className="text-xs text-muted-foreground">{role.skill_target_count} targets</span>
                  <span className={cn('text-xs font-medium', role.is_archived ? 'text-amber-600' : 'text-green-600')}>
                    {role.is_archived ? 'Archived' : 'Active'}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setAssignRole(role)}
                      className="flex items-center gap-1 px-2 py-1 text-xs border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
                    >
                      <UserPlus className="w-3 h-3" /> Assign
                    </button>
                    <button
                      onClick={() => setModalRole(role)}
                      className="p-1.5 text-muted-foreground hover:text-primary hover:bg-primary/5 rounded-[var(--radius)] transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setPendingDelete(role)}
                      className="p-1.5 text-muted-foreground hover:text-red-600 hover:bg-red-50 rounded-[var(--radius)] transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <SkillTargetsSection role={role} levels={levels} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function OrgSetupPage() {
  const [tab, setTab] = useState<'proficiency' | 'roles'>('proficiency');

  const { data: levels = [] } = useQuery<ProficiencyLevel[]>({
    queryKey: ['proficiency-levels'],
    queryFn: api.getLevels,
  });

  return (
    <div>
      <Header
        title="Org Setup"
        subtitle="Configure proficiency levels and org roles for your organisation"
      />
      <div className="page-padding max-w-4xl space-y-6">
        {/* Tabs */}
        <div className="flex items-center gap-1 p-1 bg-muted rounded-[var(--radius)] w-fit">
          {([
            { key: 'proficiency', label: 'Proficiency Scale', icon: Target },
            { key: 'roles', label: 'Org Roles', icon: Building2 },
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

        {tab === 'proficiency' && <ProficiencyTab />}
        {tab === 'roles' && <OrgRolesTab levels={levels} />}
      </div>
    </div>
  );
}
