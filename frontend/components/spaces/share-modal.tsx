'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  X, Share2, Loader2, Copy, CheckCircle2, Trash2, Search, Globe,
  ShieldOff, UserPlus, UserCheck, Building2,
} from 'lucide-react';

interface AxisUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
}
interface Team {
  id: string;
  name: string;
  member_count?: number;
}
interface AccessResponse {
  users: Array<{ user_id: string; email: string; full_name: string | null }>;
  teams: Array<{ team_id: string; name: string }>;
}

type Tab = 'add' | 'granted' | 'link';

export function ShareModal({
  spaceId,
  onClose,
  isGuestAccessible = false,
  onGuestAccessChange,
}: {
  spaceId: string;
  onClose: () => void;
  isGuestAccessible?: boolean;
  onGuestAccessChange?: (value: boolean) => void;
}) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('add');
  const [userSearch, setUserSearch] = useState('');
  const [deptSearch, setDeptSearch] = useState('');
  const [expiresInDays, setExpiresInDays] = useState(30);
  const [shareUrl, setShareUrl] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  // ── Data fetching ────────────────────────────────────────────────────────
  const { data: access, isLoading: accessLoading } = useQuery<AccessResponse>({
    queryKey: ['space-access', spaceId],
    queryFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}/access`);
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const { data: usersData, isLoading: usersLoading } = useQuery<{ users: AxisUser[] }>({
    queryKey: ['users', 'learners'],
    queryFn: async () => {
      const res = await fetch('/api/users');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  const { data: deptsData } = useQuery<{ teams: Team[] }>({
    queryKey: ['teams'],
    queryFn: async () => {
      const res = await fetch('/api/teams');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  // ── Mutations ────────────────────────────────────────────────────────────
  const grantMutation = useMutation({
    mutationFn: async (body: { type: 'user' | 'dept'; id: string }) => {
      const res = await fetch(`/api/spaces/${spaceId}/access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to grant access');
    },
    onSuccess: () => {
      toast.success('Access granted');
      qc.invalidateQueries({ queryKey: ['space-access', spaceId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const revokeMutation = useMutation({
    mutationFn: async ({ type, id }: { type: 'user' | 'dept'; id: string }) => {
      const res = await fetch(`/api/spaces/${spaceId}/access?type=${type}&targetId=${id}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to revoke access');
    },
    onSuccess: () => {
      toast.success('Access removed');
      qc.invalidateQueries({ queryKey: ['space-access', spaceId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const revokeGuestMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/spaces/${spaceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_guest_accessible: false }),
      });
      if (!res.ok) throw new Error('Failed to revoke guest access');
    },
    onSuccess: () => {
      toast.success('Guest access revoked — the link no longer works');
      onGuestAccessChange?.(false);
      qc.invalidateQueries({ queryKey: ['space', spaceId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const generateLink = async () => {
    setIsGenerating(true);
    try {
      const res = await fetch(`/api/spaces/${spaceId}/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expires_in_days: expiresInDays }),
      });
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      setShareUrl(data.share_url);
    } catch {
      toast.error('Failed to generate share link');
    } finally {
      setIsGenerating(false);
    }
  };

  const copyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ── Derived state ─────────────────────────────────────────────────────────
  // Build sets of already-granted IDs so we never show them in the "Add" list
  const grantedUserIds = new Set((access?.users ?? []).map((u) => u.user_id));
  const grantedDeptIds = new Set((access?.teams ?? []).map((d) => d.team_id));

  const filteredUsers = (usersData?.users ?? [])
    .filter((u) => u.role === 'learner')
    .filter((u) => !grantedUserIds.has(u.id))
    .filter((u) =>
      !userSearch ||
      (u.full_name ?? '').toLowerCase().includes(userSearch.toLowerCase()) ||
      u.email.toLowerCase().includes(userSearch.toLowerCase())
    );

  const filteredDepts = (deptsData?.teams ?? [])
    .filter((d) => !grantedDeptIds.has(d.id))
    .filter((d) => !deptSearch || d.name.toLowerCase().includes(deptSearch.toLowerCase()));

  const grantedCount = (access?.users?.length ?? 0) + (access?.teams?.length ?? 0);

  // ── Tab definitions ───────────────────────────────────────────────────────
  const tabs: Array<{ key: Tab; label: string; icon: React.ElementType; badge?: number }> = [
    { key: 'add',     label: 'Add Access', icon: UserPlus },
    { key: 'granted', label: 'Has Access', icon: UserCheck, badge: grantedCount || undefined },
    { key: 'link',    label: 'Guest Link', icon: Globe },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-lg shadow-lg max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
          <h2 className="font-semibold text-primary">Share Learning Space</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border flex-shrink-0">
          {tabs.map(({ key, label, icon: Icon, badge }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cn(
                'relative flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                tab === key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
              {badge !== undefined && (
                <span className={cn(
                  'ml-0.5 inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold',
                  tab === key
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted-foreground/20 text-foreground'
                )}>
                  {badge}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="overflow-y-auto flex-1">

          {/* ── TAB: Add Access ─────────────────────────────────────────── */}
          {tab === 'add' && (
            <div className="p-6 space-y-5">

              {/* Add individual users */}
              <div>
                <p className="section-label mb-2">Add Learners</p>
                <div className="relative mb-2">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    placeholder="Search by name or email…"
                    className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background
                      focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
                <div className="space-y-0.5 max-h-48 overflow-y-auto">
                  {usersLoading || accessLoading ? (
                    <div className="flex justify-center py-4">
                      <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    </div>
                  ) : filteredUsers.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-3">
                      {userSearch ? 'No matches' : 'All learners already have access'}
                    </p>
                  ) : filteredUsers.map((u) => (
                    <div key={u.id} className="flex items-center justify-between py-2 px-2 rounded-[var(--radius)] hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-7 h-7 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center text-xs font-bold text-blue-600 flex-shrink-0">
                          {(u.full_name ?? u.email)[0].toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium truncate">{u.full_name ?? u.email}</p>
                          {u.full_name && <p className="text-xs text-muted-foreground truncate">{u.email}</p>}
                        </div>
                      </div>
                      <button
                        onClick={() => grantMutation.mutate({ type: 'user', id: u.id })}
                        disabled={grantMutation.isPending}
                        className="flex items-center gap-1 text-xs text-primary font-medium hover:text-primary/80
                          disabled:opacity-40 flex-shrink-0 ml-3 px-2.5 py-1 border border-primary/30
                          rounded-[var(--radius)] hover:bg-primary/5 transition-colors"
                      >
                        <UserPlus className="w-3 h-3" />
                        Grant
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-border" />

              {/* Add teams */}
              <div>
                <p className="section-label mb-2">Add Team</p>
                <div className="relative mb-2">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    value={deptSearch}
                    onChange={(e) => setDeptSearch(e.target.value)}
                    placeholder="Search teams…"
                    className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-[var(--radius)] bg-background
                      focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                </div>
                <div className="space-y-0.5 max-h-32 overflow-y-auto">
                  {filteredDepts.length === 0 ? (
                    <p className="text-xs text-muted-foreground text-center py-3">
                      {deptSearch ? 'No matches' : 'All teams already have access'}
                    </p>
                  ) : filteredDepts.map((d) => (
                    <div key={d.id} className="flex items-center justify-between py-2 px-2 rounded-[var(--radius)] hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-purple-50 border border-purple-100 flex items-center justify-center flex-shrink-0">
                          <Building2 className="w-3.5 h-3.5 text-purple-600" />
                        </div>
                        <div>
                          <p className="text-xs font-medium">{d.name}</p>
                          {d.member_count !== undefined && (
                            <p className="text-xs text-muted-foreground">{d.member_count} members</p>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => grantMutation.mutate({ type: 'dept', id: d.id })}
                        disabled={grantMutation.isPending}
                        className="flex items-center gap-1 text-xs text-primary font-medium hover:text-primary/80
                          disabled:opacity-40 flex-shrink-0 ml-3 px-2.5 py-1 border border-primary/30
                          rounded-[var(--radius)] hover:bg-primary/5 transition-colors"
                      >
                        <UserPlus className="w-3 h-3" />
                        Grant
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── TAB: Has Access ─────────────────────────────────────────── */}
          {tab === 'granted' && (
            <div className="p-6">
              {accessLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : grantedCount === 0 ? (
                <div className="text-center py-10">
                  <UserCheck className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
                  <p className="text-sm text-muted-foreground">No one has access yet.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Use the <span className="font-medium">Add Access</span> tab to grant access.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">

                  {/* Users with access */}
                  {(access?.users?.length ?? 0) > 0 && (
                    <div>
                      <p className="section-label mb-2">Users ({access?.users?.length})</p>
                      <div className="space-y-1">
                        {(access?.users ?? []).map((u) => (
                          <div
                            key={u.user_id}
                            className="flex items-center justify-between py-2.5 px-3 rounded-[var(--radius)] bg-muted/40 border border-border/60"
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-600 flex-shrink-0">
                                {(u.full_name ?? u.email)[0].toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <p className="text-xs font-medium text-foreground truncate">
                                  {u.full_name ?? u.email}
                                </p>
                                {u.full_name && (
                                  <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                                )}
                              </div>
                            </div>
                            <button
                              onClick={() => revokeMutation.mutate({ type: 'user', id: u.user_id })}
                              disabled={revokeMutation.isPending}
                              title="Remove access"
                              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-red-600
                                disabled:opacity-40 transition-colors flex-shrink-0 ml-3 px-2 py-1
                                rounded-[var(--radius)] hover:bg-red-50"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Teams with access */}
                  {(access?.teams?.length ?? 0) > 0 && (
                    <div>
                      <p className="section-label mb-2">Teams ({access?.teams?.length})</p>
                      <div className="space-y-1">
                        {(access?.teams ?? []).map((d) => (
                          <div
                            key={d.team_id}
                            className="flex items-center justify-between py-2.5 px-3 rounded-[var(--radius)] bg-muted/40 border border-border/60"
                          >
                            <div className="flex items-center gap-2.5">
                              <div className="w-7 h-7 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                                <Building2 className="w-3.5 h-3.5 text-purple-600" />
                              </div>
                              <p className="text-xs font-medium text-foreground">{d.name}</p>
                            </div>
                            <button
                              onClick={() => revokeMutation.mutate({ type: 'dept', id: d.team_id })}
                              disabled={revokeMutation.isPending}
                              title="Remove access"
                              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-red-600
                                disabled:opacity-40 transition-colors flex-shrink-0 ml-3 px-2 py-1
                                rounded-[var(--radius)] hover:bg-red-50"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── TAB: Guest Link ─────────────────────────────────────────── */}
          {tab === 'link' && (
            <div className="p-6 space-y-4">
              <div className={cn(
                'flex items-center justify-between px-4 py-3 rounded-[var(--radius)] border',
                isGuestAccessible
                  ? 'border-green-300 bg-green-50'
                  : 'border-border bg-muted/40',
              )}>
                <div className="flex items-center gap-2">
                  <Globe className={cn('w-4 h-4', isGuestAccessible ? 'text-green-600' : 'text-muted-foreground')} />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      Guest Access:{' '}
                      <span className={isGuestAccessible ? 'text-green-600' : 'text-muted-foreground'}>
                        {isGuestAccessible ? 'ON' : 'OFF'}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {isGuestAccessible
                        ? 'Anyone with the link can view this space'
                        : 'No public access — share with specific users instead'}
                    </p>
                  </div>
                </div>
                {isGuestAccessible && (
                  <button
                    onClick={() => revokeGuestMutation.mutate()}
                    disabled={revokeGuestMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-xs font-medium
                      rounded-[var(--radius)] hover:bg-red-700 transition-colors disabled:opacity-50 flex-shrink-0"
                  >
                    {revokeGuestMutation.isPending
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <ShieldOff className="w-3.5 h-3.5" />
                    }
                    Revoke
                  </button>
                )}
              </div>

              <p className="text-sm text-muted-foreground">
                Generate a public guest link for anyone to view this space without an account.
              </p>

              <div>
                <label className="section-label block mb-1.5">Link expires in</label>
                <select
                  value={expiresInDays}
                  onChange={(e) => setExpiresInDays(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-[var(--radius)] border border-border bg-background text-sm
                    focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  <option value={7}>7 days</option>
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                  <option value={365}>1 year</option>
                </select>
              </div>

              {!shareUrl ? (
                <button
                  onClick={generateLink}
                  disabled={isGenerating}
                  className="w-full flex items-center justify-center gap-2 py-2.5 bg-primary text-primary-foreground
                    rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />}
                  {isGenerating ? 'Generating…' : 'Generate Guest Link'}
                </button>
              ) : (
                <div className="space-y-2">
                  <label className="section-label block mb-1.5">Share Link</label>
                  <div className="flex gap-2">
                    <input
                      readOnly
                      value={shareUrl}
                      className="flex-1 px-3 py-2 rounded-[var(--radius)] border border-border bg-muted text-sm text-muted-foreground"
                    />
                    <button
                      onClick={copyLink}
                      className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-[var(--radius)]
                        text-sm hover:bg-muted transition-colors"
                    >
                      {copied ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                  <button
                    onClick={() => setShareUrl('')}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Generate new link
                  </button>
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
