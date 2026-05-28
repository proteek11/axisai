'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Settings2, Users, RefreshCw, TrendingUp, AlertTriangle, CheckCircle } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface TokenDefault {
  role: 'admin' | 'creator' | 'learner';
  monthly_token_limit: number;
}

interface UserBudget {
  user_id: string;
  email: string;
  role: string;
  full_name: string | null;
  used: int;
  limit: int;
  remaining: int;
  pct_used: number;
  has_override: boolean;
  override_reason: string | null;
  override_set_by: string | null;
}

// Temporary fix for TypeScript not recognising 'int' from Python schema
type int = number;

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

function pctColor(pct: number): string {
  if (pct >= 0.9) return 'bg-red-500';
  if (pct >= 0.7) return 'bg-amber-400';
  return 'bg-primary';
}

const ROLE_COLORS: Record<string, string> = {
  admin: 'text-purple-600 bg-purple-50 border-purple-200',
  creator: 'text-blue-600 bg-blue-50 border-blue-200',
  learner: 'text-emerald-600 bg-emerald-50 border-emerald-200',
};

// ── Override Modal ─────────────────────────────────────────────────────────────

function OverrideModal({
  user,
  onClose,
  onSave,
}: {
  user: UserBudget;
  onClose: () => void;
  onSave: (userId: string, limit: number | null, reason: string) => void;
}) {
  const [useDefault, setUseDefault] = useState(!user.has_override);
  const [limitInput, setLimitInput] = useState(
    user.has_override ? String(user.limit) : ''
  );
  const [reason, setReason] = useState(user.override_reason ?? '');

  function handleSave() {
    const limit = useDefault ? null : parseInt(limitInput, 10);
    if (!useDefault && (!limit || limit < 1000)) {
      toast.error('Minimum limit is 1,000 tokens');
      return;
    }
    onSave(user.user_id, limit, reason);
    onClose();
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-xl p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-base font-bold">Token Budget Override</h2>
            <p className="text-sm text-muted-foreground mt-0.5">{user.email}</p>
          </div>
          <span className={`text-xs font-semibold px-2 py-1 rounded-full border capitalize ${ROLE_COLORS[user.role] ?? ''}`}>
            {user.role}
          </span>
        </div>

        {/* Current usage summary */}
        <div className="bg-muted/50 rounded-xl p-3 mb-5 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Used this month</span>
            <span className="font-semibold">{fmtTokens(user.used)} / {fmtTokens(user.limit)}</span>
          </div>
          <div className="h-1.5 bg-border rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${pctColor(user.pct_used)}`}
              style={{ width: `${Math.min(user.pct_used * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* Use role default toggle */}
        <label className="flex items-center gap-3 cursor-pointer mb-4">
          <div
            className={`w-10 h-5 rounded-full transition-colors ${useDefault ? 'bg-primary' : 'bg-border'} relative`}
            onClick={() => setUseDefault((v) => !v)}
          >
            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${useDefault ? 'left-5' : 'left-0.5'}`} />
          </div>
          <span className="text-sm font-medium">Use role default</span>
        </label>

        {/* Custom limit input */}
        {!useDefault && (
          <div className="mb-4">
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground block mb-1.5">
              Monthly Token Limit
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={limitInput}
                onChange={(e) => setLimitInput(e.target.value)}
                placeholder="e.g. 750000"
                min={1000}
                step={10000}
                className="flex-1 border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              <div className="text-sm text-muted-foreground whitespace-nowrap">
                ≈ {limitInput ? fmtTokens(parseInt(limitInput, 10) || 0) : '—'}
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Minimum: 1,000 · Rough guide: 1 page ≈ 750 tokens
            </p>
          </div>
        )}

        {/* Reason */}
        <div className="mb-5">
          <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground block mb-1.5">
            Reason <span className="font-normal normal-case">(optional)</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Power user with extra content needs"
            rows={2}
            maxLength={500}
            className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
          />
        </div>

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-border rounded-xl hover:bg-muted/50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-xl font-medium"
          >
            {useDefault ? 'Revert to default' : 'Apply override'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Role Defaults Editor ───────────────────────────────────────────────────────

function RoleDefaultsCard({ defaults }: { defaults: TokenDefault[] }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Record<string, string>>({});

  const updateMutation = useMutation({
    mutationFn: async ({ role, limit }: { role: string; limit: number }) => {
      const res = await fetch(`/api/admin/token-defaults/${role}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monthly_token_limit: limit }),
      });
      if (!res.ok) throw new Error('Failed to update');
      return res.json();
    },
    onSuccess: (_, { role }) => {
      toast.success(`Updated default for ${role}`);
      queryClient.invalidateQueries({ queryKey: ['token-defaults'] });
      setEditing((e) => { const next = { ...e }; delete next[role]; return next; });
    },
    onError: () => toast.error('Failed to update role default'),
  });

  return (
    <div className="bg-white border border-border rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Settings2 className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Role Defaults (tokens / month)
        </h2>
      </div>
      <div className="space-y-3">
        {defaults.map((d) => {
          const isEditing = d.role in editing;
          const inputVal = editing[d.role] ?? String(d.monthly_token_limit);
          return (
            <div key={d.role} className="flex items-center gap-3">
              <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border w-20 text-center capitalize ${ROLE_COLORS[d.role] ?? ''}`}>
                {d.role}
              </span>
              {isEditing ? (
                <>
                  <input
                    type="number"
                    value={inputVal}
                    onChange={(e) => setEditing((prev) => ({ ...prev, [d.role]: e.target.value }))}
                    className="border border-border rounded-xl px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <button
                    onClick={() => {
                      const limit = parseInt(inputVal, 10);
                      if (limit >= 1000) updateMutation.mutate({ role: d.role, limit });
                    }}
                    className="text-xs px-3 py-1.5 bg-primary text-white rounded-xl"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing((e) => { const n = { ...e }; delete n[d.role]; return n; })}
                    className="text-xs px-3 py-1.5 border border-border rounded-xl"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <span className="text-sm font-semibold flex-1">
                    {fmtTokens(d.monthly_token_limit)}
                    <span className="text-xs text-muted-foreground font-normal ml-1">
                      ({d.monthly_token_limit.toLocaleString()})
                    </span>
                  </span>
                  <button
                    onClick={() => setEditing((e) => ({ ...e, [d.role]: String(d.monthly_token_limit) }))}
                    className="text-xs text-primary border border-primary/30 px-3 py-1 rounded-xl hover:bg-primary/5"
                  >
                    Edit
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function TokenBudgetManager() {
  const queryClient = useQueryClient();
  const [selectedUser, setSelectedUser] = useState<UserBudget | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const { data: defaults = [], isLoading: defaultsLoading } = useQuery<TokenDefault[]>({
    queryKey: ['token-defaults'],
    queryFn: () => fetch('/api/admin/token-defaults').then((r) => r.json()),
  });

  const { data: budgets = [], isLoading: budgetsLoading } = useQuery<UserBudget[]>({
    queryKey: ['token-budgets'],
    queryFn: () => fetch('/api/admin/token-budgets').then((r) => r.json()),
    refetchInterval: 30_000, // refresh every 30s
  });

  const overrideMutation = useMutation({
    mutationFn: async ({
      userId,
      limit,
      reason,
    }: {
      userId: string;
      limit: number | null;
      reason: string;
    }) => {
      const res = await fetch(`/api/admin/token-budgets/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monthly_token_limit: limit, reason: reason || null }),
      });
      if (!res.ok) throw new Error('Failed to set override');
      return res.json();
    },
    onSuccess: () => {
      toast.success('Token budget updated');
      queryClient.invalidateQueries({ queryKey: ['token-budgets'] });
    },
    onError: () => toast.error('Failed to update budget'),
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/admin/token-budgets/reset', { method: 'POST' });
      if (!res.ok) throw new Error('Reset failed');
      return res.json();
    },
    onSuccess: (data) => {
      toast.success(data.message ?? 'Monthly usage reset complete');
      queryClient.invalidateQueries({ queryKey: ['token-budgets'] });
    },
    onError: () => toast.error('Reset failed'),
  });

  const filtered = budgets.filter(
    (u) =>
      u.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (u.full_name ?? '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const highUsage = budgets.filter((u) => u.pct_used >= 0.8);

  if (defaultsLoading || budgetsLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground text-sm">
        Loading token budgets…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Alert banner for high-usage users */}
      {highUsage.length > 0 && (
        <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" />
          <div>
            <span className="font-semibold">{highUsage.length} user{highUsage.length > 1 ? 's' : ''}</span>
            {' '}at or above 80% of their monthly budget:
            {' '}{highUsage.map((u) => u.email).join(', ')}
          </div>
        </div>
      )}

      {/* Role defaults */}
      <RoleDefaultsCard defaults={defaults} />

      {/* Per-user table */}
      <div className="bg-white border border-border rounded-2xl overflow-hidden">
        {/* Table header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Per-User Budgets
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search users…"
              className="text-sm border border-border rounded-xl px-3 py-1.5 w-48 focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              onClick={() => {
                if (confirm('Reset ALL users\' monthly usage to zero? This cannot be undone.')) {
                  resetMutation.mutate();
                }
              }}
              disabled={resetMutation.isPending}
              className="flex items-center gap-1.5 text-xs border border-border px-3 py-1.5 rounded-xl hover:bg-muted/50 disabled:opacity-50"
            >
              <RefreshCw className="w-3 h-3" />
              {resetMutation.isPending ? 'Resetting…' : 'Reset Month'}
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground px-5 py-3">
                  User
                </th>
                <th className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground px-4 py-3">
                  Role
                </th>
                <th className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground px-4 py-3">
                  Usage this month
                </th>
                <th className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground px-4 py-3">
                  Limit
                </th>
                <th className="text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground px-4 py-3">
                  Override
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center text-sm text-muted-foreground py-10">
                    No users found
                  </td>
                </tr>
              )}
              {filtered.map((u) => (
                <tr key={u.user_id} className="border-b border-border last:border-0 hover:bg-muted/30">
                  <td className="px-5 py-3">
                    <div className="text-sm font-medium">{u.full_name ?? '—'}</div>
                    <div className="text-xs text-muted-foreground">{u.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border capitalize ${ROLE_COLORS[u.role] ?? ''}`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 min-w-[160px]">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${pctColor(u.pct_used)}`}
                          style={{ width: `${Math.min(u.pct_used * 100, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {fmtTokens(u.used)} / {fmtTokens(u.limit)}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {Math.round(u.pct_used * 100)}% used · {fmtTokens(u.remaining)} remaining
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold">
                    {fmtTokens(u.limit)}
                  </td>
                  <td className="px-4 py-3">
                    {u.has_override ? (
                      <div className="flex items-center gap-1 text-xs text-amber-600">
                        <TrendingUp className="w-3 h-3" />
                        Custom
                        {u.override_reason && (
                          <span className="text-muted-foreground ml-1 truncate max-w-[120px]" title={u.override_reason}>
                            · {u.override_reason}
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <CheckCircle className="w-3 h-3" />
                        Role default
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setSelectedUser(u)}
                      className="text-xs text-primary border border-primary/30 px-3 py-1 rounded-xl hover:bg-primary/5"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Override modal */}
      {selectedUser && (
        <OverrideModal
          user={selectedUser}
          onClose={() => setSelectedUser(null)}
          onSave={(userId, limit, reason) => {
            overrideMutation.mutate({ userId, limit, reason });
          }}
        />
      )}
    </div>
  );
}
