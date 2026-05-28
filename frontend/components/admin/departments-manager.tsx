'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { cn } from '@/lib/utils';
import {
  Users, Plus, Loader2, Trash2, Pencil, ChevronDown, ChevronRight,
  UserPlus, UserMinus, Building2, X, Check, AlertCircle,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

interface Member {
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
  added_at: string;
}

interface Department {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  member_count: number;
  created_at: string;
  updated_at: string;
  members?: Member[];
}

interface DepartmentListResponse {
  departments: Department[];
  total: number;
}

interface AxisUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
}

// ── API helpers ───────────────────────────────────────────────────────────────

const api = {
  fetchDepartments: () =>
    fetch('/api/departments').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  fetchDepartment: (id: string) =>
    fetch(`/api/departments/${id}`).then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  createDepartment: (body: { name: string; description?: string }) =>
    fetch('/api/departments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  updateDepartment: (id: string, body: Partial<{ name: string; description: string | null; is_active: boolean }>) =>
    fetch(`/api/departments/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  deleteDepartment: (id: string) =>
    fetch(`/api/departments/${id}`, { method: 'DELETE' }).then((r) => { if (!r.ok) throw new Error('Failed'); }),
  addMembers: (id: string, user_ids: string[]) =>
    fetch(`/api/departments/${id}/members`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_ids }) })
      .then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  removeMembers: (id: string, user_ids: string[]) =>
    fetch(`/api/departments/${id}/members`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_ids }) })
      .then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
  fetchUsers: () =>
    fetch('/api/admin/users').then((r) => { if (!r.ok) throw new Error('Failed'); return r.json(); }),
};

// ── Create/Edit department modal ──────────────────────────────────────────────

function DeptModal({
  dept,
  onClose,
  onSave,
  saving,
}: {
  dept?: Department;
  onClose: () => void;
  onSave: (data: { name: string; description: string }) => void;
  saving: boolean;
}) {
  const [name, setName] = useState(dept?.name ?? '');
  const [desc, setDesc] = useState(dept?.description ?? '');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold text-primary text-lg">
            {dept ? 'Edit Department' : 'New Department'}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="section-label mb-1.5">Department Name *</label>
            <input
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="e.g. Engineering, Marketing"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="section-label mb-1.5">Description</label>
            <textarea
              className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
              placeholder="Optional description"
              rows={3}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 mt-6 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave({ name: name.trim(), description: desc.trim() })}
            disabled={!name.trim() || saving}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {dept ? 'Save Changes' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Add members modal ─────────────────────────────────────────────────────────

function AddMembersModal({
  dept,
  allUsers,
  onClose,
  onAdd,
  saving,
}: {
  dept: Department;
  allUsers: AxisUser[];
  onClose: () => void;
  onAdd: (user_ids: string[]) => void;
  saving: boolean;
}) {
  const currentMemberIds = new Set((dept.members ?? []).map((m) => m.user_id));
  const available = allUsers.filter((u) => !currentMemberIds.has(u.id) && u.is_active);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');

  const filtered = available.filter((u) =>
    (u.full_name ?? '').toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-primary text-lg">Add Members to {dept.name}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>

        <input
          className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3"
          placeholder="Search users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <div className="border border-border rounded-[var(--radius)] overflow-hidden max-h-64 overflow-y-auto mb-4">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {available.length === 0 ? 'All users are already members' : 'No matching users'}
            </p>
          ) : (
            filtered.map((u) => (
              <button
                key={u.id}
                onClick={() => toggle(u.id)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50 border-b border-border last:border-0 text-left transition-colors"
              >
                <div className={cn(
                  'w-5 h-5 rounded border flex items-center justify-center flex-shrink-0',
                  selected.has(u.id) ? 'bg-primary border-primary' : 'border-border'
                )}>
                  {selected.has(u.id) && <Check className="w-3 h-3 text-primary-foreground" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{u.full_name || u.email}</p>
                  {u.full_name && <p className="text-xs text-muted-foreground truncate">{u.email}</p>}
                </div>
                <span className="text-xs text-muted-foreground capitalize">{u.role}</span>
              </button>
            ))
          )}
        </div>

        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">{selected.size} selected</p>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors">
              Cancel
            </button>
            <button
              onClick={() => onAdd(Array.from(selected))}
              disabled={selected.size === 0 || saving}
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Add {selected.size > 0 ? `${selected.size} ` : ''}Member{selected.size !== 1 ? 's' : ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Department row ────────────────────────────────────────────────────────────

function DeptRow({
  dept,
  allUsers,
  onEdit,
  onDelete,
}: {
  dept: Department;
  allUsers: AxisUser[];
  onEdit: (d: Department) => void;
  onDelete: (d: Department) => void;
}) {
  const [open, setOpen] = useState(false);
  const [addModal, setAddModal] = useState(false);
  const qc = useQueryClient();

  const { data: detail, isLoading: loadingDetail } = useQuery<Department>({
    queryKey: ['department', dept.id],
    queryFn: () => api.fetchDepartment(dept.id),
    enabled: open,
  });

  const addMut = useMutation({
    mutationFn: (ids: string[]) => api.addMembers(dept.id, ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['department', dept.id] });
      qc.invalidateQueries({ queryKey: ['departments'] });
      setAddModal(false);
    },
  });

  const removeMut = useMutation({
    mutationFn: (uid: string) => api.removeMembers(dept.id, [uid]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['department', dept.id] });
      qc.invalidateQueries({ queryKey: ['departments'] });
    },
  });

  const members = detail?.members ?? [];

  return (
    <>
      <div className="border border-border rounded-[var(--radius)] bg-card overflow-hidden">
        {/* Header row */}
        <div className="flex items-center gap-3 px-4 py-3">
          <button onClick={() => setOpen((v) => !v)} className="text-muted-foreground hover:text-foreground">
            {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
          <div className="w-8 h-8 rounded-full bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Building2 className="w-4 h-4 text-blue-600" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-semibold text-sm text-primary">{dept.name}</p>
              {!dept.is_active && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
                  Inactive
                </span>
              )}
            </div>
            {dept.description && (
              <p className="text-xs text-muted-foreground truncate">{dept.description}</p>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Users className="w-3.5 h-3.5" />
            {dept.member_count}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setAddModal(true)}
              title="Add members"
              className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-primary"
            >
              <UserPlus className="w-4 h-4" />
            </button>
            <button
              onClick={() => onEdit(dept)}
              title="Edit department"
              className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-primary"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              onClick={() => onDelete(dept)}
              title="Delete department"
              className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-red-600"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Members panel */}
        {open && (
          <div className="border-t border-border bg-muted/20 px-4 py-3">
            {loadingDetail ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading members…
              </div>
            ) : members.length === 0 ? (
              <p className="text-sm text-muted-foreground">No members yet. Click <span className="text-primary">+</span> to add some.</p>
            ) : (
              <div className="space-y-1">
                {members.map((m) => (
                  <div key={m.user_id} className="flex items-center gap-2 py-1">
                    <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <span className="text-[10px] font-bold text-primary">
                        {(m.full_name || m.email).charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-foreground">{m.full_name || m.email}</span>
                      {m.full_name && (
                        <span className="text-xs text-muted-foreground ml-1.5">{m.email}</span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground capitalize">{m.role}</span>
                    <button
                      onClick={() => removeMut.mutate(m.user_id)}
                      disabled={removeMut.isPending}
                      title="Remove from department"
                      className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-red-600"
                    >
                      <UserMinus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {addModal && detail && (
        <AddMembersModal
          dept={detail}
          allUsers={allUsers}
          onClose={() => setAddModal(false)}
          onAdd={(ids) => addMut.mutate(ids)}
          saving={addMut.isPending}
        />
      )}
      {addModal && !detail && loadingDetail && (
        <AddMembersModal
          dept={{ ...dept, members: [] }}
          allUsers={allUsers}
          onClose={() => setAddModal(false)}
          onAdd={(ids) => addMut.mutate(ids)}
          saving={addMut.isPending}
        />
      )}
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function DepartmentsManager() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editDept, setEditDept] = useState<Department | null>(null);
  const [deleteDept, setDeleteDept] = useState<Department | null>(null);

  const { data, isLoading } = useQuery<DepartmentListResponse>({
    queryKey: ['departments'],
    queryFn: api.fetchDepartments,
    refetchInterval: 30_000,
  });

  const { data: usersData } = useQuery<{ users: AxisUser[] }>({
    queryKey: ['admin', 'users'],
    queryFn: api.fetchUsers,
  });

  const allUsers = usersData?.users ?? [];
  const departments = data?.departments ?? [];

  const createMut = useMutation({
    mutationFn: api.createDepartment,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['departments'] }); setShowCreate(false); },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<Department>) =>
      api.updateDepartment(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['departments'] }); setEditDept(null); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteDepartment(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['departments'] }); setDeleteDept(null); },
  });

  return (
    <div>
      <Header
        subtitle="Group users into departments for bulk Learning Space access"
        action={
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Department
          </button>
        }
      />

      <div className="page-padding">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="enterprise-card flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-blue-50 flex items-center justify-center">
              <Building2 className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{departments.length}</p>
              <p className="text-xs text-muted-foreground">Departments</p>
            </div>
          </div>
          <div className="enterprise-card flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-green-50 flex items-center justify-center">
              <Users className="w-4 h-4 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {departments.reduce((sum, d) => sum + d.member_count, 0)}
              </p>
              <p className="text-xs text-muted-foreground">Total memberships</p>
            </div>
          </div>
        </div>

        {/* Department list */}
        {isLoading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : departments.length === 0 ? (
          <div className="enterprise-card flex flex-col items-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
              <Building2 className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="font-semibold text-primary mb-1">No departments yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Create a department to group users and share Learning Spaces with the whole group.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create First Department
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {departments.map((dept) => (
              <DeptRow
                key={dept.id}
                dept={dept}
                allUsers={allUsers}
                onEdit={setEditDept}
                onDelete={setDeleteDept}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <DeptModal
          onClose={() => setShowCreate(false)}
          onSave={(data) => createMut.mutate(data)}
          saving={createMut.isPending}
        />
      )}

      {/* Edit modal */}
      {editDept && (
        <DeptModal
          dept={editDept}
          onClose={() => setEditDept(null)}
          onSave={(data) => updateMut.mutate({ id: editDept.id, ...data })}
          saving={updateMut.isPending}
        />
      )}

      {/* Delete confirmation */}
      {deleteDept && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-background border border-border rounded-[var(--radius)] shadow-xl w-full max-w-sm p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0 mt-0.5">
                <AlertCircle className="w-4 h-4 text-red-600" />
              </div>
              <div>
                <h3 className="font-bold text-primary">Delete Department</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Are you sure you want to delete <strong>{deleteDept.name}</strong>? All
                  {deleteDept.member_count > 0 && ` ${deleteDept.member_count} membership${deleteDept.member_count !== 1 ? 's' : ''} and all`} space access grants for this department will be removed.
                </p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteDept(null)}
                className="px-4 py-2 text-sm border border-border rounded-[var(--radius)] hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMut.mutate(deleteDept.id)}
                disabled={deleteMut.isPending}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-[var(--radius)] hover:bg-red-700 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {deleteMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
