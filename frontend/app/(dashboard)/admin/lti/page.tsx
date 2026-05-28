'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Copy, Check, Trash2, Pencil, ToggleLeft, ToggleRight,
  Link2, Shield, ChevronDown, ChevronUp, ExternalLink, RefreshCw,
} from 'lucide-react';
// No shadcn/ui — using native Tailwind buttons and badges

interface LTIPlatform {
  id: string;
  name: string;
  issuer: string;
  client_id: string;
  auth_login_url: string;
  auth_token_url: string;
  key_set_url: string;
  deployment_ids: string[];
  is_active: boolean;
  created_at: string;
  // axis-ai config values to paste into Moodle
  axis_tool_url: string;
  axis_login_url: string;
  axis_jwks_url: string;
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="ml-1 text-[#79697b] hover:text-[#1447e6] transition-colors">
      {copied ? <Check className="w-3.5 h-3.5 text-green-600" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-[#f3f1f3] last:border-0">
      <span className="text-xs text-[#79697b] w-32 flex-shrink-0 pt-0.5">{label}</span>
      <span className="text-xs font-mono text-[#0c090c] break-all flex-1">{value}</span>
      <CopyButton value={value} />
    </div>
  );
}

function PlatformCard({ platform, onToggle, onDelete }: {
  platform: LTIPlatform;
  onToggle: (id: string, active: boolean) => void;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`bg-white border rounded-xl overflow-hidden transition-all ${platform.is_active ? 'border-[#e7e4e7]' : 'border-[#f3f1f3] opacity-70'}`}>
      {/* Header */}
      <div className="flex items-center gap-3 p-4">
        <div className="w-9 h-9 rounded-full bg-[#dbeafe] flex items-center justify-center flex-shrink-0">
          <Link2 className="w-4 h-4 text-[#1447e6]" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[#0c090c] truncate">{platform.name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${platform.is_active ? 'border-green-300 text-green-700 bg-green-50' : 'border-gray-300 text-gray-500 bg-gray-50'}`}>
              {platform.is_active ? 'Active' : 'Disabled'}
            </span>
          </div>
          <p className="text-xs text-[#79697b] truncate">{platform.issuer}</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onToggle(platform.id, !platform.is_active)}
            className="p-1.5 text-[#79697b] hover:text-[#1447e6] transition-colors"
            title={platform.is_active ? 'Disable' : 'Enable'}
          >
            {platform.is_active
              ? <ToggleRight className="w-5 h-5 text-[#1447e6]" />
              : <ToggleLeft className="w-5 h-5" />}
          </button>
          <button
            onClick={() => onDelete(platform.id)}
            className="p-1.5 text-[#79697b] hover:text-red-500 transition-colors"
            title="Delete platform"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-[#79697b] hover:text-[#0c090c] transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-[#f3f1f3]">
          {/* axis-ai config to paste into Moodle */}
          <div className="p-4 bg-[#f0fdf4]">
            <p className="text-xs font-semibold text-[#15803d] uppercase tracking-wider mb-2">
              📋 Paste these into Moodle → External Tool setup
            </p>
            <ConfigRow label="Tool URL" value={platform.axis_tool_url} />
            <ConfigRow label="Initiate Login URL" value={platform.axis_login_url} />
            <ConfigRow label="JWKS / Keyset URL" value={platform.axis_jwks_url} />
            <ConfigRow label="Redirect URI" value={platform.axis_tool_url} />
          </div>
          {/* Moodle config stored in axis-ai */}
          <div className="p-4">
            <p className="text-xs font-semibold text-[#79697b] uppercase tracking-wider mb-2">Moodle config stored in axis-ai</p>
            <ConfigRow label="Issuer" value={platform.issuer} />
            <ConfigRow label="Client ID" value={platform.client_id} />
            <ConfigRow label="Auth Login URL" value={platform.auth_login_url} />
            <ConfigRow label="Auth Token URL" value={platform.auth_token_url} />
            <ConfigRow label="JWKS URL" value={platform.key_set_url} />
            <div className="flex items-start gap-2 py-1.5">
              <span className="text-xs text-[#79697b] w-32 flex-shrink-0">Deployment IDs</span>
              <span className="text-xs font-mono text-[#0c090c]">{platform.deployment_ids.join(', ')}</span>
            </div>
          </div>
          {/* Custom param tip */}
          <div className="px-4 pb-4">
            <div className="bg-[#f8f6f8] border border-[#e7e4e7] rounded-lg p-3">
              <p className="text-xs font-semibold text-[#0c090c] mb-1">Optional: Link a Moodle course to a specific space</p>
              <p className="text-xs text-[#79697b] mb-2">
                In Moodle → External Tool → Custom parameters, add:
              </p>
              <code className="block text-xs font-mono bg-[#0c090c] text-[#86efac] rounded px-2 py-1.5">
                space_slug=your-space-slug
              </code>
              <p className="text-xs text-[#79697b] mt-1">
                The slug is shown on each learning space's settings. Leave blank to show the full dashboard.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RegisterModal({ onClose, onSaved, tenantOptions }: {
  onClose: () => void;
  onSaved: () => void;
  tenantOptions: { id: string; name: string }[];
}) {
  const [form, setForm] = useState({
    name: '',
    tenant_id: tenantOptions[0]?.id || '',
    issuer: '',
    client_id: '',
    auth_login_url: '',
    auth_token_url: '',
    key_set_url: '',
    deployment_ids: '1',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await fetch('/api/admin/lti/platforms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          deployment_ids: form.deployment_ids.split(',').map(s => s.trim()).filter(Boolean),
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'Failed to save');
        return;
      }
      onSaved();
      onClose();
    } catch {
      setError('Network error');
    } finally {
      setSaving(false);
    }
  };

  const field = (label: string, key: keyof typeof form, placeholder = '') => (
    <div>
      <label className="block text-xs font-semibold text-[#0c090c] mb-1">{label}</label>
      <input
        className="w-full border border-[#e7e4e7] rounded-lg px-3 py-2 text-sm text-[#0c090c] focus:outline-none focus:ring-2 focus:ring-[#1447e6] bg-white"
        value={form[key]}
        placeholder={placeholder}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
      />
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-5 border-b border-[#e7e4e7]">
          <h2 className="text-base font-bold text-[#0c090c]">Register LTI Platform</h2>
          <p className="text-xs text-[#79697b] mt-1">Enter the values from your Moodle site. Then paste axis-ai's config back into Moodle.</p>
        </div>
        <div className="p-5 flex flex-col gap-4">
          {field('Platform Name', 'name', 'e.g. ACME University Moodle')}

          <div>
            <label className="block text-xs font-semibold text-[#0c090c] mb-1">Tenant</label>
            <select
              className="w-full border border-[#e7e4e7] rounded-lg px-3 py-2 text-sm text-[#0c090c] focus:outline-none focus:ring-2 focus:ring-[#1447e6] bg-white"
              value={form.tenant_id}
              onChange={e => setForm(f => ({ ...f, tenant_id: e.target.value }))}
            >
              {tenantOptions.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          <div className="pt-1 pb-1">
            <p className="text-xs font-semibold text-[#79697b] uppercase tracking-wider">From Moodle → External Tool details</p>
          </div>

          {field('Platform URL (Issuer)', 'issuer', 'https://lms.youruniversity.edu')}
          {field('Client ID', 'client_id', 'Issued by Moodle')}
          {field('Auth Login URL', 'auth_login_url', 'https://lms.../mod/lti/auth.php')}
          {field('Auth Token URL', 'auth_token_url', 'https://lms.../mod/lti/token.php')}
          {field('JWKS / Key Set URL', 'key_set_url', 'https://lms.../mod/lti/certs.php')}
          {field('Deployment ID(s)', 'deployment_ids', '1')}
          <p className="text-xs text-[#79697b] -mt-2">Comma-separated if multiple (usually just "1")</p>

          {error && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>}
        </div>
        <div className="p-5 border-t border-[#e7e4e7] flex justify-end gap-2">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 text-sm font-medium border border-[#e7e4e7] rounded-lg text-[#0c090c] hover:bg-[#f3f1f3] disabled:opacity-50 transition-colors">Cancel</button>
          <button onClick={save} disabled={saving} className="px-4 py-2 text-sm font-medium bg-[#1447e6] hover:bg-[#0f3bcc] text-white rounded-lg disabled:opacity-50 transition-colors">
            {saving ? 'Saving…' : 'Register Platform'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminLTIPage() {
  const [platforms, setPlatforms] = useState<LTIPlatform[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  // For now, tenant dropdown is a placeholder — in production fetch from /api/admin/tenants
  const tenantOptions = [{ id: '', name: 'Default Tenant' }];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/lti/platforms');
      const data = await res.json();
      setPlatforms(data.platforms || []);
    } catch {
      setPlatforms([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleToggle = async (id: string, active: boolean) => {
    await fetch(`/api/admin/lti/platforms/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: active }),
    });
    load();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this LTI platform? Learners using this connection will lose access.')) return;
    await fetch(`/api/admin/lti/platforms/${id}`, { method: 'DELETE' });
    load();
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-[#1447e6]">LTI 1.3 Connections</h1>
          <p className="text-sm text-[#79697b] mt-1">
            Connect Moodle (or any LTI 1.3 LMS) for automatic SSO. No Moodle plugin needed.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="flex items-center px-3 py-1.5 text-sm font-medium border border-[#e7e4e7] rounded-lg text-[#0c090c] hover:bg-[#f3f1f3] transition-colors">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Refresh
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center px-3 py-1.5 text-sm font-medium bg-[#1447e6] hover:bg-[#0f3bcc] text-white rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Register Platform
          </button>
        </div>
      </div>

      {/* How it works — quick guide */}
      <div className="bg-[#eff6ff] border border-[#bfdbfe] rounded-xl p-4 mb-6">
        <div className="flex items-start gap-2">
          <Shield className="w-4 h-4 text-[#1447e6] mt-0.5 flex-shrink-0" />
          <div className="text-xs text-[#1d4ed8] space-y-1">
            <p className="font-semibold">Setup in 2 steps:</p>
            <p>1. Add axis-ai as an External Tool in Moodle → Site admin → Plugins → External tool → Manage tools → Add preconfigured tool. Choose LTI 1.3.</p>
            <p>2. Paste the axis-ai config values (shown when you expand a platform below) into Moodle. Then paste Moodle's Platform ID, Client ID, and URLs here.</p>
            <p className="font-medium">No Moodle plugin installation required.</p>
          </div>
        </div>
      </div>

      {/* Platform list */}
      {loading ? (
        <div className="text-sm text-[#79697b] text-center py-12">Loading…</div>
      ) : platforms.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-[#e7e4e7] rounded-xl">
          <Link2 className="w-8 h-8 text-[#e7e4e7] mx-auto mb-3" />
          <p className="text-sm font-semibold text-[#0c090c]">No LTI platforms yet</p>
          <p className="text-xs text-[#79697b] mt-1 mb-4">Register your first Moodle site to enable SSO launches.</p>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center px-3 py-1.5 text-sm font-medium bg-[#1447e6] hover:bg-[#0f3bcc] text-white rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Register Platform
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {platforms.map(p => (
            <PlatformCard
              key={p.id}
              platform={p}
              onToggle={handleToggle}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {showModal && (
        <RegisterModal
          onClose={() => setShowModal(false)}
          onSaved={load}
          tenantOptions={tenantOptions}
        />
      )}
    </div>
  );
}
