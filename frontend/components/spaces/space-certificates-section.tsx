'use client';
/**
 * SpaceCertificatesSection
 * Shown in the space detail page (creator/admin view).
 * - Lists active cert configs placed by the creator
 * - "Add Certificate" → pick template + set trigger
 * - Shows issued certs at the bottom
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import {
  Award, Plus, Trash2, Loader2, CheckCircle2,
  ChevronDown, ChevronUp, LayoutTemplate, X, SendHorizonal, User,
} from 'lucide-react';
import { toast } from 'sonner';

// ── Types ──────────────────────────────────────────────────────────────────

interface CertTemplate {
  id: string;
  name: string;
  type_tag: string;
  layout_style: string;
  title_text: string;
}

interface CertConfig {
  id: string;
  template_id: string | null;
  template_name: string | null;
  template_layout: string | null;
  trigger_type: string;
  trigger_value: Record<string, any>;
  custom_title: string | null;
  custom_message: string | null;
  position: number;
  is_active: boolean;
}

interface IssuedCert {
  certificate_id: string;
  learner_name: string;
  learner_email: string;
  issued_at: string;
}

const TRIGGER_LABELS: Record<string, string> = {
  all_items: 'Complete all items',
  percentage: 'Complete % of items',
  assessment: 'Pass an assessment',
  manual: 'Manually issued',
};


// ── Issue Certificate Modal (manual issuance) ──────────────────────────────

function IssueCertModal({
  spaceId,
  onClose,
}: {
  spaceId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('');

  const { data: usersData, isLoading: usersLoading } = useQuery<{ users: Array<{ id: string; email: string; first_name: string; last_name: string }> }>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const r = await fetch('/api/admin/users');
      if (!r.ok) return { users: [] };
      return r.json();
    },
  });

  const filteredUsers = (usersData?.users ?? []).filter(u => {
    const name = `${u.first_name ?? ''} ${u.last_name ?? ''} ${u.email}`.toLowerCase();
    return name.includes(search.toLowerCase());
  });

  const issueMutation = useMutation({
    mutationFn: async () => {
      const r = await fetch('/api/admin/certificates/issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ space_id: spaceId, user_id: selectedUserId }),
      });
      if (!r.ok) throw new Error((await r.json()).error || 'Failed to issue certificate');
      return r.json();
    },
    onSuccess: (data) => {
      toast.success(`Certificate issued to ${data.learner_name}`);
      queryClient.invalidateQueries({ queryKey: ['space-certificates', spaceId] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md mx-4 shadow-xl flex flex-col max-h-[90dvh]">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <SendHorizonal className="w-4 h-4 text-primary" />
            <p className="font-semibold text-sm">Issue Certificate to Learner</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <p className="text-xs text-muted-foreground">
            Manually award a certificate to any learner, bypassing completion requirements.
          </p>
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Search Learner</label>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Name or email…"
              className="mt-2 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          {usersLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading users…
            </div>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {filteredUsers.slice(0, 20).map(u => (
                <label
                  key={u.id}
                  className={cn(
                    'flex items-center gap-3 p-2.5 rounded-[var(--radius)] border cursor-pointer transition-colors',
                    selectedUserId === u.id
                      ? 'border-primary bg-primary/5'
                      : 'border-transparent hover:bg-muted/50',
                  )}
                >
                  <input
                    type="radio"
                    name="user"
                    value={u.id}
                    checked={selectedUserId === u.id}
                    onChange={() => setSelectedUserId(u.id)}
                    className="accent-primary"
                  />
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <User className="w-3.5 h-3.5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {[u.first_name, u.last_name].filter(Boolean).join(' ') || u.email}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                    </div>
                  </div>
                </label>
              ))}
              {filteredUsers.length === 0 && (
                <p className="text-sm text-muted-foreground py-2 text-center">No users found</p>
              )}
            </div>
          )}
        </div>

        <div className="flex gap-2 px-5 py-4 border-t border-border flex-shrink-0 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => issueMutation.mutate()}
            disabled={issueMutation.isPending || !selectedUserId}
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

// ── Add Cert Modal ─────────────────────────────────────────────────────────

function AddCertModal({
  spaceId,
  itemCount,
  onClose,
}: {
  spaceId: string;
  itemCount: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [triggerType, setTriggerType] = useState('all_items');
  const [percentage, setPercentage] = useState(80);
  const [customTitle, setCustomTitle] = useState('');
  const [customMessage, setCustomMessage] = useState('');

  const { data: templates = [], isLoading: tmplLoading } = useQuery<CertTemplate[]>({
    queryKey: ['cert-templates'],
    queryFn: async () => {
      const r = await fetch('/api/admin/certificate-templates');
      if (!r.ok) return [];
      return r.json();
    },
  });

  const addMutation = useMutation({
    mutationFn: async () => {
      const tv: Record<string, any> = {};
      if (triggerType === 'percentage') tv.percentage = percentage;

      const r = await fetch(`/api/spaces/${spaceId}/cert-configs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: selectedTemplate || null,
          trigger_type: triggerType,
          trigger_value: tv,
          custom_title: customTitle || null,
          custom_message: customMessage || null,
        }),
      });
      if (!r.ok) throw new Error((await r.json()).error || 'Failed');
      return r.json();
    },
    onSuccess: () => {
      toast.success('Certificate added to space');
      queryClient.invalidateQueries({ queryKey: ['space-cert-configs', spaceId] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-md mx-4 shadow-xl flex flex-col max-h-[90dvh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <Award className="w-4 h-4 text-primary" />
            <p className="font-semibold text-sm">Add Certificate to Space</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Template picker */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Certificate Template</label>
            {tmplLoading ? (
              <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading templates…
              </div>
            ) : templates.length === 0 ? (
              <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                No templates yet. Ask your admin to create one in Admin → Certificates → Templates.
              </div>
            ) : (
              <div className="mt-2 space-y-2">
                {templates.map(t => (
                  <label
                    key={t.id}
                    className={cn(
                      'flex items-center gap-3 p-3 rounded-[var(--radius)] border cursor-pointer transition-colors',
                      selectedTemplate === t.id
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50',
                    )}
                  >
                    <input
                      type="radio"
                      name="template"
                      value={t.id}
                      checked={selectedTemplate === t.id}
                      onChange={() => setSelectedTemplate(t.id)}
                      className="accent-primary"
                    />
                    <div>
                      <p className="text-sm font-medium">{t.name}</p>
                      <p className="text-xs text-muted-foreground">{t.title_text} · {t.layout_style}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Trigger condition */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Award When</label>
            <select
              value={triggerType}
              onChange={e => setTriggerType(e.target.value)}
              className="mt-2 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all_items">Learner completes ALL {itemCount} items</option>
              <option value="percentage">Learner completes a % of items</option>
              <option value="manual">Manual — admin issues it</option>
            </select>
            {triggerType === 'percentage' && (
              <div className="mt-2 flex items-center gap-3">
                <input
                  type="range" min={10} max={100} step={5}
                  value={percentage}
                  onChange={e => setPercentage(Number(e.target.value))}
                  className="flex-1 accent-primary"
                />
                <span className="text-sm font-semibold w-10 text-right">{percentage}%</span>
              </div>
            )}
          </div>

          {/* Custom overrides (optional) */}
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Customise (optional)</p>
            <div>
              <label className="text-xs text-muted-foreground">Custom title — overrides template</label>
              <input
                value={customTitle}
                onChange={e => setCustomTitle(e.target.value)}
                placeholder="e.g. Certificate of Achievement"
                className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Personal message to learner</label>
              <textarea
                rows={2}
                value={customMessage}
                onChange={e => setCustomMessage(e.target.value)}
                placeholder="e.g. Congratulations on completing this course!"
                className="mt-1 w-full px-3 py-2 border border-border rounded-[var(--radius)] text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-2 px-5 py-4 border-t border-border flex-shrink-0 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-border rounded-[var(--radius)] text-sm text-muted-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => addMutation.mutate()}
            disabled={addMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {addMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            Add Certificate
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Section Component ─────────────────────────────────────────────────

interface Props {
  spaceId: string;
  itemCount: number;
  isCreatorOrAdmin: boolean;
}

export function SpaceCertificatesSection({ spaceId, itemCount, isCreatorOrAdmin }: Props) {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [showIssued, setShowIssued] = useState(false);
  const [showIssue, setShowIssue] = useState(false);

  // Cert configs on this space
  const { data: configs = [], isLoading: configsLoading } = useQuery<CertConfig[]>({
    queryKey: ['space-cert-configs', spaceId],
    queryFn: async () => {
      const r = await fetch(`/api/spaces/${spaceId}/cert-configs`);
      if (!r.ok) return [];
      return r.json();
    },
    enabled: !!spaceId,
  });

  // Issued certs in this space (admin/creator only)
  const { data: issuedData } = useQuery<{ total: number; certificates: IssuedCert[] }>({
    queryKey: ['space-certificates', spaceId],
    queryFn: async () => {
      const r = await fetch(`/api/admin/certificates?space_id=${spaceId}&limit=100`);
      if (!r.ok) return { total: 0, certificates: [] };
      return r.json();
    },
    enabled: isCreatorOrAdmin && !!spaceId,
  });

  const removeMutation = useMutation({
    mutationFn: async (configId: string) => {
      const r = await fetch(`/api/spaces/${spaceId}/cert-configs/${configId}`, { method: 'DELETE' });
      if (!r.ok && r.status !== 204) throw new Error('Failed to remove');
    },
    onSuccess: () => {
      toast.success('Certificate removed from space');
      queryClient.invalidateQueries({ queryKey: ['space-cert-configs', spaceId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const TRIGGER_SUMMARY = (cfg: CertConfig) => {
    if (cfg.trigger_type === 'all_items') return `Awarded on completing all ${itemCount} items`;
    if (cfg.trigger_type === 'percentage') return `Awarded at ${cfg.trigger_value?.percentage ?? '?'}% completion`;
    if (cfg.trigger_type === 'manual') return 'Manually issued by admin';
    return cfg.trigger_type;
  };

  return (
    <>
      <div className="enterprise-card mt-6 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Award className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Certificates
            </span>
            {configs.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-xs bg-emerald-100 text-emerald-700 rounded-full font-semibold">
                {configs.length}
              </span>
            )}
          </div>
          {isCreatorOrAdmin && (
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 text-primary rounded-[var(--radius)] text-xs font-medium hover:bg-primary/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Certificate
            </button>
          )}
        </div>

        <div className="p-5">
          {configsLoading ? (
            <div className="flex items-center justify-center h-16">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : configs.length === 0 ? (
            <div className="text-center py-6">
              <Award className="w-8 h-8 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-sm font-medium text-foreground">No certificates configured</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs mx-auto">
                {isCreatorOrAdmin
                  ? 'Click "Add Certificate" to pick a template and set when learners receive it.'
                  : 'No certificates are set up for this space.'}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {configs.map(cfg => (
                <div key={cfg.id} className="flex items-start gap-3 p-3 rounded-[var(--radius)] border border-border bg-muted/20">
                  <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Award className="w-4 h-4 text-emerald-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {cfg.custom_title || cfg.template_name || 'Certificate'}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">{TRIGGER_SUMMARY(cfg)}</p>
                    {cfg.template_layout && (
                      <p className="text-xs text-muted-foreground/60">{cfg.template_layout} layout</p>
                    )}
                  </div>
                  {isCreatorOrAdmin && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {cfg.trigger_type === 'manual' && (
                        <button
                          onClick={() => setShowIssue(true)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-[var(--radius)] hover:bg-emerald-100 transition-colors"
                          title="Issue certificate to a learner"
                        >
                          <SendHorizonal className="w-3 h-3" />
                          Issue
                        </button>
                      )}
                      <button
                        onClick={() => removeMutation.mutate(cfg.id)}
                        disabled={removeMutation.isPending}
                        className="p-1.5 rounded hover:bg-red-50 text-muted-foreground hover:text-red-600 transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Issued certs toggle (creator/admin) */}
          {isCreatorOrAdmin && issuedData && issuedData.total > 0 && (
            <div className="mt-4 pt-4 border-t border-border">
              <button
                onClick={() => setShowIssued(v => !v)}
                className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
              >
                {showIssued ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                {issuedData.total} certificate{issuedData.total !== 1 ? 's' : ''} issued
              </button>
              {showIssued && (
                <div className="mt-3 space-y-2">
                  {issuedData.certificates.slice(0, 10).map(c => (
                    <div key={c.certificate_id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                      <div className="flex items-center gap-2.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                        <div>
                          <p className="text-sm font-medium">{c.learner_name || '—'}</p>
                          {c.learner_email && <p className="text-xs text-muted-foreground">{c.learner_email}</p>}
                        </div>
                      </div>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(c.issued_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    </div>
                  ))}
                  {issuedData.total > 10 && (
                    <p className="text-xs text-center text-muted-foreground pt-1">
                      +{issuedData.total - 10} more —{' '}
                      <a href="/admin/certificates" className="text-primary underline hover:no-underline">
                        View all in Admin → Certificates
                      </a>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showIssue && (
        <IssueCertModal
          spaceId={spaceId}
          onClose={() => setShowIssue(false)}
        />
      )}

      {showAdd && (
        <AddCertModal
          spaceId={spaceId}
          itemCount={itemCount}
          onClose={() => setShowAdd(false)}
        />
      )}
    </>
  );
}
