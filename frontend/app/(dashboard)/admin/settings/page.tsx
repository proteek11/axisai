'use client';

import { useEffect, useRef, useState } from 'react';
import { Palette, RotateCcw, Save, Eye, EyeOff, Loader2, CheckCircle2, Upload, X, Shield, ToggleLeft, ToggleRight, Mail, Send, Server, ChevronDown, ChevronUp, AlertCircle, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { applyBranding } from '@/components/branding/branding-provider';

// ── Types ────────────────────────────────────────────────────────────────────

interface BrandingTokens {
  primary: string;
  primary_foreground: string;
  background: string;
  foreground: string;
  card: string;
  muted: string;
  muted_foreground: string;
  border: string;
  sidebar_background: string;
  sidebar_primary: string;
  radius: string;
  site_name: string;
  logo_url: string;
}

// ── Defaults (matches globals.css light-mode values) ─────────────────────────

const DEFAULTS: BrandingTokens = {
  primary:            '#1447e6',
  primary_foreground: '#eff6ff',
  background:         '#ffffff',
  foreground:         '#0c090c',
  card:               '#ffffff',
  muted:              '#f3f1f3',
  muted_foreground:   '#79697b',
  border:             '#e7e4e7',
  sidebar_background: '#f8f6f8',
  sidebar_primary:    '#155dfc',
  radius:             '0.875rem',
  site_name:          'Axis AI',
  logo_url:           '',
};

// ── Token groups for the UI ───────────────────────────────────────────────────

const COLOR_GROUPS = [
  {
    label: 'Brand',
    description: 'Primary action colour used on buttons, active items and highlights.',
    tokens: [
      { key: 'primary',            label: 'Primary',             hint: 'Brand blue — buttons, links, highlights' },
      { key: 'primary_foreground', label: 'Primary Foreground',  hint: 'Text on primary-coloured surfaces' },
    ],
  },
  {
    label: 'Surfaces',
    description: 'Background colours for the main canvas, cards, and muted areas.',
    tokens: [
      { key: 'background', label: 'Page Background', hint: 'Main content area background' },
      { key: 'card',       label: 'Card Background',  hint: 'Elevated card / panel background' },
      { key: 'muted',      label: 'Muted Surface',    hint: 'Subtle bg — inputs, tags, code blocks' },
    ],
  },
  {
    label: 'Text',
    description: 'Foreground colours for body copy and secondary labels.',
    tokens: [
      { key: 'foreground',         label: 'Primary Text',   hint: 'Headings and body copy' },
      { key: 'muted_foreground',   label: 'Secondary Text', hint: 'Labels, placeholders, subtitles' },
    ],
  },
  {
    label: 'Borders',
    description: 'Divider and outline colours.',
    tokens: [
      { key: 'border', label: 'Border', hint: 'Card borders, dividers, input outlines' },
    ],
  },
  {
    label: 'Sidebar',
    description: 'Navigation sidebar palette.',
    tokens: [
      { key: 'sidebar_background', label: 'Sidebar Background', hint: 'Left-nav background colour' },
      { key: 'sidebar_primary',    label: 'Sidebar Active',     hint: 'Active nav-item highlight' },
    ],
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Convert hex (#rrggbb) → HSL channel string ("H S% L%") for CSS vars.
 * Tailwind config wraps vars as hsl(var(--x)), so vars must hold channels only.
 * Passes non-hex strings through unchanged (already HSL or dimension).
 */
function hexToHslChannels(hex: string): string {
  if (!hex || !hex.startsWith('#')) return hex;
  const clean = hex.replace('#', '');
  if (clean.length < 6) return hex;
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

/**
 * Convert HSL channel string ("H S% L%") → hex (#rrggbb).
 * Used to display stored HSL values in the hex color input.
 */
function hslChannelsToHex(hsl: string): string {
  const parts = hsl.trim().split(/\s+/);
  if (parts.length < 3) return '#000000';
  const h = parseFloat(parts[0]) / 360;
  const s = parseFloat(parts[1]) / 100;
  const l = parseFloat(parts[2]) / 100;
  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  const toH = (x: number) => Math.round(x * 255).toString(16).padStart(2, '0');
  return `#${toH(r)}${toH(g)}${toH(b)}`;
}

function isColorKey(key: string) {
  return key !== 'radius' && key !== 'site_name' && key !== 'logo_url';
}

/**
 * Normalise any stored value to #rrggbb for <input type="color">.
 * Stored values may be hex (preferred) or HSL channels (legacy).
 */
function toHex(val: string): string {
  if (!val) return '#000000';
  if (val.startsWith('#')) return val.slice(0, 7);
  // HSL channels "H S% L%" — convert to hex
  if (/^\d/.test(val)) return hslChannelsToHex(val);
  return '#000000';
}

// ── ColorSwatch + Picker ──────────────────────────────────────────────────────

function ColorPicker({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const hexVal = toHex(value);

  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-[var(--radius)] hover:bg-muted/50 transition-colors group">
      {/* Swatch — <label> wraps <input type="color"> so clicking anywhere on it opens the native picker */}
      <label
        className="relative w-9 h-9 rounded-lg border border-border flex-shrink-0 shadow-sm hover:scale-110 transition-transform cursor-pointer"
        style={{ backgroundColor: hexVal }}
        title="Click to change colour"
      >
        <input
          type="color"
          value={hexVal}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          style={{ border: 'none', padding: 0 }}
        />
      </label>
      {/* Labels */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-foreground leading-tight">{label}</p>
        <p className="text-[11px] text-muted-foreground leading-snug">{hint}</p>
      </div>
      {/* Hex text input */}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={32}
        className="w-24 text-xs font-mono bg-muted border border-border rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
        spellCheck={false}
      />
    </div>
  );
}

// ── Live Preview Panel ────────────────────────────────────────────────────────
// Uses inline styles with raw hex values — works correctly independent of
// CSS vars, so the preview is always accurate regardless of var format.

function LivePreview({ tokens }: { tokens: BrandingTokens }) {
  return (
    <div
      className="rounded-xl border overflow-hidden text-xs"
      style={{
        background: tokens.background,
        borderColor: tokens.border,
        color: tokens.foreground,
        fontFamily: 'inherit',
      }}
    >
      {/* Mini sidebar */}
      <div className="flex" style={{ minHeight: 220 }}>
        <div
          className="flex flex-col gap-1 p-2 w-28 flex-shrink-0"
          style={{ background: tokens.sidebar_background, borderRight: `1px solid ${tokens.border}` }}
        >
          {/* Logo */}
          <div className="flex items-center gap-1.5 px-1 py-1.5 mb-1">
            <div
              className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0"
              style={{ background: tokens.primary }}
            >
              <span className="text-[8px] font-bold" style={{ color: tokens.primary_foreground }}>A</span>
            </div>
            <span className="text-[10px] font-bold truncate" style={{ color: tokens.foreground }}>
              {tokens.site_name || 'Axis AI'}
            </span>
          </div>
          {/* Nav items */}
          {['Dashboard', 'Spaces', 'Users'].map((item, i) => (
            <div
              key={item}
              className="px-2 py-1 rounded text-[10px] truncate"
              style={
                i === 0
                  ? { background: tokens.sidebar_primary, color: tokens.primary_foreground }
                  : { color: tokens.muted_foreground }
              }
            >
              {item}
            </div>
          ))}
        </div>
        {/* Main area */}
        <div className="flex-1 p-3">
          <p className="font-semibold text-[11px] mb-2" style={{ color: tokens.foreground }}>Overview</p>
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-1.5 mb-2">
            {['Learners', 'Spaces'].map((s) => (
              <div
                key={s}
                className="rounded-lg p-2"
                style={{ background: tokens.card, border: `1px solid ${tokens.border}` }}
              >
                <p className="font-bold text-sm" style={{ color: tokens.foreground }}>42</p>
                <p className="text-[10px]" style={{ color: tokens.muted_foreground }}>{s}</p>
              </div>
            ))}
          </div>
          {/* Button */}
          <button
            className="px-3 py-1 rounded text-[10px] font-medium"
            style={{
              background: tokens.primary,
              color: tokens.primary_foreground,
              borderRadius: tokens.radius,
            }}
          >
            + New Space
          </button>
          {/* Muted pill */}
          <span
            className="ml-2 px-2 py-0.5 rounded-full text-[10px]"
            style={{ background: tokens.muted, color: tokens.muted_foreground }}
          >
            Draft
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────



/* ══════════════════════════════════════════════════════════════
   Email / Mailing Settings Section
══════════════════════════════════════════════════════════════ */

interface SmtpConfig {
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password: string;
  from_name: string;
  from_email: string;
  use_tls: boolean;
  use_ssl: boolean;
}

interface TriggerConfig {
  enabled: boolean;
  subject: string;
  body: string;
}

interface EmailSettings {
  email_config: SmtpConfig;
  email_triggers: Record<string, TriggerConfig>;
}

const DEFAULT_SMTP: SmtpConfig = {
  smtp_host: '', smtp_port: 587, smtp_user: '', smtp_password: '',
  from_name: 'Axis AI', from_email: '', use_tls: true, use_ssl: false,
};

const TRIGGER_META: Record<string, { label: string; description: string; vars: string[] }> = {
  welcome: {
    label: 'Welcome Email',
    description: 'Sent when admin creates a new user account.',
    vars: ['full_name', 'email', 'password', 'login_url'],
  },
  space_shared: {
    label: 'Space Shared',
    description: 'Sent when a learning space is shared with a learner.',
    vars: ['full_name', 'shared_by', 'space_title', 'space_url'],
  },
  team_added: {
    label: 'Added to Team',
    description: 'Sent when a user is added to a team.',
    vars: ['full_name', 'team_name', 'added_by', 'login_url'],
  },
};

function EmailSettingsSection() {
  const [settings, setSettings] = useState<EmailSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [testEmail, setTestEmail] = useState('');
  const [sendingTest, setSendingTest] = useState(false);
  const [expandedTrigger, setExpandedTrigger] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetch('/api/admin/settings/email', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) setSettings(d);
        else setSettings({ email_config: DEFAULT_SMTP, email_triggers: {} });
      })
      .catch(() => setSettings({ email_config: DEFAULT_SMTP, email_triggers: {} }))
      .finally(() => setLoading(false));
  }, []);

  const updateConfig = (patch: Partial<SmtpConfig>) => {
    setSettings(s => s ? { ...s, email_config: { ...s.email_config, ...patch } } : s);
    setDirty(true);
    setTestResult(null);
  };

  const updateTrigger = (key: string, patch: Partial<TriggerConfig>) => {
    setSettings(s => {
      if (!s) return s;
      return {
        ...s,
        email_triggers: {
          ...s.email_triggers,
          [key]: { ...s.email_triggers[key], ...patch },
        },
      };
    });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const r = await fetch('/api/admin/settings/email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(settings),
      });
      if (!r.ok) throw new Error();
      const updated = await r.json();
      setSettings(updated);
      setDirty(false);
      toast.success('Email settings saved');
    } catch {
      toast.error('Failed to save email settings');
    } finally { setSaving(false); }
  };

  const handleTestConnection = async () => {
    if (!settings) return;
    setTesting(true);
    setTestResult(null);
    try {
      const r = await fetch('/api/admin/settings/email/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email_config: settings.email_config }),
      });
      const d = await r.json();
      setTestResult(d);
    } catch {
      setTestResult({ ok: false, error: 'Request failed' });
    } finally { setTesting(false); }
  };

  const handleSendTest = async () => {
    if (!settings || !testEmail) return;
    setSendingTest(true);
    try {
      const r = await fetch('/api/admin/settings/email/test?send=1', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email_config: settings.email_config, to_email: testEmail }),
      });
      const d = await r.json();
      if (d.ok) toast.success(`Test email sent to ${testEmail}`);
      else toast.error(`Send failed: ${d.error || 'Unknown error'}`);
    } catch {
      toast.error('Failed to send test email');
    } finally { setSendingTest(false); }
  };

  if (loading) return (
    <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-2 text-muted-foreground text-sm">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading email settings…
    </div>
  );

  if (!settings) return null;
  const cfg = settings.email_config;

  return (
    <div className="space-y-4">
      {/* SMTP Config card */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Email / SMTP</h2>
          </div>
          <div className="flex items-center gap-2">
            {testResult && (
              <span className={`flex items-center gap-1 text-xs font-medium ${testResult.ok ? 'text-green-600' : 'text-red-500'}`}>
                {testResult.ok
                  ? <><CheckCircle className="w-3.5 h-3.5" /> Connected</>
                  : <><AlertCircle className="w-3.5 h-3.5" /> {testResult.error?.slice(0, 40)}</>}
              </span>
            )}
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testing || !cfg.smtp_host || !cfg.from_email}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] border border-border hover:bg-muted text-muted-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Server className="w-3 h-3" />}
              Test connection
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !dirty}
              className="flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-[var(--radius)] bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* SMTP Host */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Host</label>
            <input
              type="text"
              value={cfg.smtp_host}
              onChange={e => updateConfig({ smtp_host: e.target.value })}
              placeholder="smtp.gmail.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>
          {/* SMTP Port */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Port</label>
            <input
              type="number"
              value={cfg.smtp_port}
              onChange={e => updateConfig({ smtp_port: parseInt(e.target.value) || 587 })}
              placeholder="587"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
            />
          </div>
          {/* Username */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Username</label>
            <input
              type="text"
              value={cfg.smtp_user}
              onChange={e => updateConfig({ smtp_user: e.target.value })}
              placeholder="you@gmail.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>
          {/* Password */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Password</label>
            <input
              type="password"
              value={cfg.smtp_password}
              onChange={e => updateConfig({ smtp_password: e.target.value })}
              placeholder="App password or SMTP password"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>
          {/* From Name */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">From Name</label>
            <input
              type="text"
              value={cfg.from_name}
              onChange={e => updateConfig({ from_name: e.target.value })}
              placeholder="Axis AI"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>
          {/* From Email */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">From Email</label>
            <input
              type="email"
              value={cfg.from_email}
              onChange={e => updateConfig({ from_email: e.target.value })}
              placeholder="noreply@yourdomain.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
            />
          </div>
        </div>

        {/* TLS/SSL toggles */}
        <div className="flex items-center gap-6 mt-3 pt-3 border-t border-border">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={cfg.use_tls}
              onChange={e => updateConfig({ use_tls: e.target.checked, use_ssl: e.target.checked ? false : cfg.use_ssl })}
              className="w-4 h-4 accent-primary rounded"
            />
            <span className="text-sm text-foreground">Use STARTTLS</span>
            <span className="text-xs text-muted-foreground">(port 587, recommended)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={cfg.use_ssl}
              onChange={e => updateConfig({ use_ssl: e.target.checked, use_tls: e.target.checked ? false : cfg.use_tls })}
              className="w-4 h-4 accent-primary rounded"
            />
            <span className="text-sm text-foreground">Use SSL/TLS</span>
            <span className="text-xs text-muted-foreground">(port 465)</span>
          </label>
        </div>

        {/* Send test email */}
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
          <input
            type="email"
            value={testEmail}
            onChange={e => setTestEmail(e.target.value)}
            placeholder="Send a test email to…"
            className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={handleSendTest}
            disabled={sendingTest || !testEmail || !cfg.smtp_host || !cfg.from_email}
            className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-[var(--radius)] border border-primary text-primary hover:bg-primary/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-medium whitespace-nowrap"
          >
            {sendingTest ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
            Send test
          </button>
        </div>
      </div>

      {/* Per-trigger email templates */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-4">
          <Mail className="w-4 h-4 text-primary" />
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Email Triggers</h2>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Configure which emails are sent automatically. Use <code className="bg-muted px-1 rounded font-mono text-xs">{"{{variable}}"}</code> placeholders in subject and body.
        </p>

        <div className="space-y-2">
          {Object.entries(TRIGGER_META).map(([key, meta]) => {
            const trigger = settings.email_triggers[key] ?? { enabled: false, subject: '', body: '' };
            const isOpen = expandedTrigger === key;

            return (
              <div key={key} className="border border-border rounded-lg overflow-hidden">
                {/* Trigger header row */}
                <div className="flex items-center gap-3 px-3 py-2.5 bg-muted/30">
                  <button
                    type="button"
                    onClick={() => updateTrigger(key, { enabled: !trigger.enabled })}
                    className="flex-shrink-0"
                    aria-pressed={trigger.enabled}
                  >
                    {trigger.enabled
                      ? <ToggleRight className="w-7 h-7 text-primary" />
                      : <ToggleLeft className="w-7 h-7 text-muted-foreground" />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">{meta.label}</p>
                    <p className="text-xs text-muted-foreground">{meta.description}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpandedTrigger(isOpen ? null : key)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded hover:bg-muted"
                  >
                    Edit template
                    {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {/* Expandable template editor */}
                {isOpen && (
                  <div className="p-3 space-y-3 border-t border-border bg-background">
                    {/* Available variables */}
                    <div className="flex flex-wrap gap-1">
                      {meta.vars.map(v => (
                        <span key={v} className="px-1.5 py-0.5 bg-muted border border-border rounded text-[10px] font-mono text-muted-foreground">
                          {`{{${v}}}`}
                        </span>
                      ))}
                    </div>
                    {/* Subject */}
                    <div>
                      <label className="text-xs font-medium text-foreground block mb-1">Subject</label>
                      <input
                        type="text"
                        value={trigger.subject}
                        onChange={e => updateTrigger(key, { subject: e.target.value })}
                        className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                      />
                    </div>
                    {/* Body */}
                    <div>
                      <label className="text-xs font-medium text-foreground block mb-1">Body</label>
                      <textarea
                        value={trigger.body}
                        onChange={e => updateTrigger(key, { body: e.target.value })}
                        rows={8}
                        className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground font-mono resize-y"
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="flex justify-end mt-4">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !dirty}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-[var(--radius)] bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {saving ? 'Saving…' : 'Save email settings'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════
   Authentication Settings Section
══════════════════════════════════════════════════════════════ */
function AuthSettingsSection() {
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch('/api/auth/settings', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setGoogleEnabled(d.google_auth_enabled); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const toggle = async () => {
    setSaving(true);
    try {
      const r = await fetch('/api/auth/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ google_auth_enabled: !googleEnabled }),
      });
      if (!r.ok) throw new Error();
      setGoogleEnabled(v => !v);
      toast.success(googleEnabled ? 'Google login disabled' : 'Google login enabled');
    } catch {
      toast.error('Failed to update setting');
    } finally { setSaving(false); }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Shield className="w-4 h-4 text-primary" />
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Authentication</h2>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
      ) : (
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm font-medium">Google Sign-In</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Allow users to sign in using their Google account.
              {!process.env.GOOGLE_CLIENT_ID && ' (Requires GOOGLE_CLIENT_ID in .env to function.)'}
            </p>
          </div>
          <button
            type="button"
            onClick={toggle}
            disabled={saving}
            className="flex items-center gap-1.5 text-sm font-medium transition-colors disabled:opacity-50"
            aria-pressed={googleEnabled}
          >
            {saving
              ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              : googleEnabled
                ? <ToggleRight className="w-8 h-8 text-primary" />
                : <ToggleLeft className="w-8 h-8 text-muted-foreground" />}
            <span className={googleEnabled ? 'text-primary' : 'text-muted-foreground'}>
              {googleEnabled ? 'On' : 'Off'}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

export default function SiteBrandingPage() {
  const [tokens, setTokens] = useState<BrandingTokens>(DEFAULTS);
  const [original, setOriginal] = useState<BrandingTokens>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  // Load saved branding on mount
  useEffect(() => {
    fetch('/api/admin/settings/branding', { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        const merged: BrandingTokens = { ...DEFAULTS };
        for (const k of Object.keys(DEFAULTS) as (keyof BrandingTokens)[]) {
          if (data[k] != null && data[k] !== '') merged[k] = data[k];
        }
        setTokens(merged);
        setOriginal(merged);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  /**
   * Derived CSS vars that must stay in sync with a parent branding token.
   * When a token changes live, all listed vars are updated to the same HSL value.
   */
  const DERIVED_FROM: Record<string, string[]> = {
    primary:            ['--ring'],
    primary_foreground: ['--sidebar-primary-foreground'],
    foreground:         ['--card-foreground', '--popover-foreground', '--secondary-foreground', '--accent-foreground', '--sidebar-foreground'],
    card:               ['--popover'],
    muted:              ['--secondary', '--accent', '--sidebar-accent'],
    border:             ['--input', '--sidebar-border'],
  };

  /**
   * Update a token in state AND live-apply it to the page's CSS variables.
   *
   * ⚠️  CSS var format:
   *   globals.css stores vars as HSL channels: "--background: 0 0% 100%"
   *   Tailwind reads them as: background: "hsl(var(--background))"
   *   So we must write HSL channels ("H S% L%"), not hex, to :root.
   *   State + DB always store hex (human-readable for the picker).
   *
   * ⚠️  Derived vars:
   *   globals.css has 25 vars; the UI exposes 10. The other 15 mirror a
   *   parent token (e.g. --ring mirrors --primary, --input mirrors --border).
   *   They are kept in sync via DERIVED_FROM above.
   */
  const setToken = (key: keyof BrandingTokens, value: string) => {
    setTokens((prev) => ({ ...prev, [key]: value }));
    setSaved(false);

    if (key === 'radius') {
      document.documentElement.style.setProperty('--radius', value);
    } else if (isColorKey(key)) {
      const hslVal = hexToHslChannels(value);
      const cssVar = `--${key.replace(/_/g, '-')}`;
      // Update primary var
      document.documentElement.style.setProperty(cssVar, hslVal);
      // Update all derived vars that mirror this token
      for (const derived of DERIVED_FROM[key] ?? []) {
        document.documentElement.style.setProperty(derived, hslVal);
      }
    }
  };

  const handleReset = () => {
    setTokens(original);
    applyBranding(original);
    setSaved(false);
  };

  const handleResetDefaults = () => {
    setTokens(DEFAULTS);
    applyBranding(DEFAULTS);
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/admin/settings/branding', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(tokens),
      });
      if (!res.ok) throw new Error('Save failed');
      const data = await res.json();
      const merged: BrandingTokens = { ...DEFAULTS };
      for (const k of Object.keys(DEFAULTS) as (keyof BrandingTokens)[]) {
        if (data[k] != null && data[k] !== '') merged[k] = data[k];
      }
      setOriginal(merged);
      setTokens(merged);
      applyBranding(merged);
      localStorage.setItem('axis_branding_v1', JSON.stringify(merged));
      setSaved(true);
      toast.success('Branding saved successfully');
    } catch {
      toast.error('Failed to save branding');
    } finally {
      setSaving(false);
    }
  };

  const isDirty = JSON.stringify(tokens) !== JSON.stringify(original);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Palette className="w-5 h-5 text-primary" />
            <h1 className="text-xl font-bold text-foreground">Site Branding</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Customise colours, typography scale, and identity for your Axis AI instance.
            Changes apply live to all users after saving.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setShowPreview((p) => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] border border-border hover:bg-muted text-muted-foreground transition-colors"
          >
            {showPreview ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {showPreview ? 'Hide preview' : 'Show preview'}
          </button>
          <button
            type="button"
            onClick={handleReset}
            disabled={!isDirty}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] border border-border hover:bg-muted text-muted-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Revert
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-[var(--radius)] bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : saved ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {saving ? 'Saving…' : saved && !isDirty ? 'Saved ✓' : 'Save branding'}
          </button>
        </div>
      </div>

      <div className={`grid gap-6 ${showPreview ? 'grid-cols-[1fr_280px]' : 'grid-cols-1'}`}>
        {/* Left: editor */}
        <div className="space-y-4">

          {/* Identity */}
          <div className="bg-card border border-border rounded-xl p-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Identity
            </h2>
            <div className="space-y-3">
              {/* Site name */}
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Site Name</label>
                <input
                  type="text"
                  value={tokens.site_name}
                  onChange={(e) => setToken('site_name', e.target.value)}
                  placeholder="Axis AI"
                  className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
                />
              </div>
              {/* Logo URL */}
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Logo URL</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={tokens.logo_url}
                    onChange={(e) => setToken('logo_url', e.target.value)}
                    placeholder="https://… or leave blank for default icon"
                    className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
                  />
                  {tokens.logo_url && (
                    <img
                      src={tokens.logo_url}
                      alt="logo"
                      className="w-8 h-8 rounded object-contain border border-border bg-muted flex-shrink-0"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Enter a publicly accessible image URL. Leave blank to use the default Axis icon.
                </p>
              </div>
            </div>
          </div>

          {/* Border radius */}
          <div className="bg-card border border-border rounded-xl p-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3">
              Shape
            </h2>
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="text-xs font-medium text-foreground block mb-1">Border Radius</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={24}
                    step={1}
                    value={parseFloat(tokens.radius) * 16 || 14}
                    onChange={(e) => {
                      const px = parseInt(e.target.value);
                      const rem = `${(px / 16).toFixed(3)}rem`;
                      setToken('radius', rem);
                    }}
                    className="flex-1 accent-primary"
                  />
                  <input
                    type="text"
                    value={tokens.radius}
                    onChange={(e) => setToken('radius', e.target.value)}
                    className="w-24 text-xs font-mono bg-muted border border-border rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                {['0rem', '0.25rem', '0.5rem', '0.875rem', '1.5rem'].map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setToken('radius', r)}
                    title={r}
                    className={`w-7 h-7 bg-primary/80 border transition-all ${tokens.radius === r ? 'border-primary ring-1 ring-primary' : 'border-border'}`}
                    style={{ borderRadius: r }}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Color groups */}
          {COLOR_GROUPS.map((group) => (
            <div key={group.label} className="bg-card border border-border rounded-xl p-4">
              <div className="mb-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  {group.label}
                </h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">{group.description}</p>
              </div>
              <div className="space-y-0.5">
                {group.tokens.map(({ key, label, hint }) => (
                  <ColorPicker
                    key={key}
                    label={label}
                    hint={hint}
                    value={tokens[key as keyof BrandingTokens] as string}
                    onChange={(v) => setToken(key as keyof BrandingTokens, v)}
                  />
                ))}
              </div>
            </div>
          ))}


          {/* Reset to defaults */}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleResetDefaults}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2"
            >
              Reset everything to factory defaults
            </button>
          </div>
        </div>

        {/* Right: Live preview */}
        {showPreview && (
          <div className="space-y-3">
            <div className="sticky top-6">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
                  Live Preview
                </p>
                <span className="text-[10px] text-muted-foreground">Updates as you edit</span>
              </div>
              <LivePreview tokens={tokens} />

              {/* Token reference table */}
              <div className="mt-4 bg-card border border-border rounded-xl p-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-2">
                  CSS Variables
                </p>
                <div className="space-y-1">
                  {(Object.keys(DEFAULTS) as (keyof BrandingTokens)[])
                    .filter((k) => isColorKey(k) && k !== 'radius')
                    .map((k) => (
                    <div key={k} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-sm border border-border flex-shrink-0"
                        style={{ backgroundColor: tokens[k] as string }}
                      />
                      <span className="text-[10px] font-mono text-muted-foreground flex-1 truncate">
                        --{k.replace(/_/g, '-')}
                      </span>
                      <span className="text-[10px] font-mono text-foreground">
                        {tokens[k]}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
