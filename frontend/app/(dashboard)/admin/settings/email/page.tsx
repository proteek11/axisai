'use client';

import { useEffect, useState } from 'react';
import {
  Mail, Loader2, Save, Server, Send, AlertCircle,
  CheckCircle, ToggleLeft, ToggleRight, ChevronDown, ChevronUp,
} from 'lucide-react';
import { toast } from 'sonner';

interface SmtpConfig {
  smtp_host: string; smtp_port: number; smtp_user: string;
  smtp_password: string; from_name: string; from_email: string;
  use_tls: boolean; use_ssl: boolean;
}
interface TriggerConfig { enabled: boolean; subject: string; body: string; }
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

export default function EmailSettingsPage() {
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
      .then(d => setSettings(d ?? { email_config: DEFAULT_SMTP, email_triggers: {} }))
      .catch(() => setSettings({ email_config: DEFAULT_SMTP, email_triggers: {} }))
      .finally(() => setLoading(false));
  }, []);

  const updateConfig = (patch: Partial<SmtpConfig>) => {
    setSettings(s => s ? { ...s, email_config: { ...s.email_config, ...patch } } : s);
    setDirty(true); setTestResult(null);
  };
  const updateTrigger = (key: string, patch: Partial<TriggerConfig>) => {
    setSettings(s => {
      if (!s) return s;
      return { ...s, email_triggers: { ...s.email_triggers, [key]: { ...s.email_triggers[key], ...patch } } };
    });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const r = await fetch('/api/admin/settings/email', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify(settings),
      });
      if (!r.ok) throw new Error();
      const updated = await r.json();
      setSettings(updated); setDirty(false);
      toast.success('Email settings saved');
    } catch { toast.error('Failed to save email settings'); }
    finally { setSaving(false); }
  };

  const handleTestConnection = async () => {
    if (!settings) return;
    setTesting(true); setTestResult(null);
    try {
      const r = await fetch('/api/admin/settings/email/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify({ email_config: settings.email_config }),
      });
      setTestResult(await r.json());
    } catch { setTestResult({ ok: false, error: 'Request failed' }); }
    finally { setTesting(false); }
  };

  const handleSendTest = async () => {
    if (!settings || !testEmail) return;
    setSendingTest(true);
    try {
      const r = await fetch('/api/admin/settings/email/test?send=1', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'include', body: JSON.stringify({ email_config: settings.email_config, to_email: testEmail }),
      });
      const d = await r.json();
      if (d.ok) toast.success(`Test email sent to ${testEmail}`);
      else toast.error(`Failed: ${d.error || 'Unknown error'}`);
    } catch { toast.error('Failed to send test email'); }
    finally { setSendingTest(false); }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-muted-foreground gap-2">
      <Loader2 className="w-5 h-5 animate-spin" />
    </div>
  );
  if (!settings) return null;

  const cfg = settings.email_config;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center">
            <Mail className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Email Settings</h1>
            <p className="text-sm text-muted-foreground mt-0.5">Configure SMTP and automatic email triggers.</p>
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !dirty}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] hover:bg-primary/90 transition-colors disabled:opacity-50 font-medium"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving…' : 'Save Changes'}
        </button>
      </div>

      {/* SMTP Config */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">SMTP Configuration</h2>
          <div className="flex items-center gap-2">
            {testResult && (
              <span className={`flex items-center gap-1 text-xs font-medium ${testResult.ok ? 'text-green-600' : 'text-red-500'}`}>
                {testResult.ok ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                {testResult.ok ? 'Connected' : testResult.error?.slice(0, 40)}
              </span>
            )}
            <button
              onClick={handleTestConnection}
              disabled={testing || !cfg.smtp_host || !cfg.from_email}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] border border-border hover:bg-muted text-muted-foreground transition-colors disabled:opacity-40"
            >
              {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Server className="w-3 h-3" />}
              Test connection
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Host</label>
            <input type="text" value={cfg.smtp_host} onChange={e => updateConfig({ smtp_host: e.target.value })}
              placeholder="smtp.gmail.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">Port</label>
            <input type="number" value={cfg.smtp_port} onChange={e => updateConfig({ smtp_port: parseInt(e.target.value) || 587 })}
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground" />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Username</label>
            <input type="text" value={cfg.smtp_user} onChange={e => updateConfig({ smtp_user: e.target.value })}
              placeholder="you@gmail.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">SMTP Password</label>
            <input type="password" value={cfg.smtp_password} onChange={e => updateConfig({ smtp_password: e.target.value })}
              placeholder="App password"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">From Name</label>
            <input type="text" value={cfg.from_name} onChange={e => updateConfig({ from_name: e.target.value })}
              placeholder="Axis AI"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">From Email</label>
            <input type="email" value={cfg.from_email} onChange={e => updateConfig({ from_email: e.target.value })}
              placeholder="noreply@yourdomain.com"
              className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          </div>
        </div>

        <div className="flex items-center gap-6 mt-4 pt-4 border-t border-border">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={cfg.use_tls}
              onChange={e => updateConfig({ use_tls: e.target.checked, use_ssl: e.target.checked ? false : cfg.use_ssl })}
              className="w-4 h-4 accent-primary rounded" />
            <span className="text-sm text-foreground">STARTTLS</span>
            <span className="text-xs text-muted-foreground">(port 587)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={cfg.use_ssl}
              onChange={e => updateConfig({ use_ssl: e.target.checked, use_tls: e.target.checked ? false : cfg.use_tls })}
              className="w-4 h-4 accent-primary rounded" />
            <span className="text-sm text-foreground">SSL/TLS</span>
            <span className="text-xs text-muted-foreground">(port 465)</span>
          </label>
        </div>

        <div className="flex items-center gap-2 mt-4 pt-4 border-t border-border">
          <input type="email" value={testEmail} onChange={e => setTestEmail(e.target.value)}
            placeholder="Send a test email to…"
            className="flex-1 text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground" />
          <button onClick={handleSendTest} disabled={sendingTest || !testEmail || !cfg.smtp_host || !cfg.from_email}
            className="flex items-center gap-1.5 px-4 py-2 text-xs rounded-[var(--radius)] border border-primary text-primary hover:bg-primary/5 transition-colors disabled:opacity-40 font-medium whitespace-nowrap">
            {sendingTest ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
            Send test
          </button>
        </div>
      </div>

      {/* Email Triggers */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-2">Email Triggers</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Configure automatic emails. Use <code className="bg-muted px-1 rounded font-mono text-xs">{'{{variable}}'}</code> placeholders in subject and body.
        </p>

        <div className="space-y-2">
          {Object.entries(TRIGGER_META).map(([key, meta]) => {
            const trigger = settings.email_triggers[key] ?? { enabled: false, subject: '', body: '' };
            const isOpen = expandedTrigger === key;

            return (
              <div key={key} className="border border-border rounded-lg overflow-hidden">
                <div className="flex items-center gap-3 px-3 py-3 bg-muted/30">
                  <button type="button" onClick={() => updateTrigger(key, { enabled: !trigger.enabled })} className="flex-shrink-0">
                    {trigger.enabled
                      ? <ToggleRight className="w-7 h-7 text-primary" />
                      : <ToggleLeft className="w-7 h-7 text-muted-foreground" />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">{meta.label}</p>
                    <p className="text-xs text-muted-foreground">{meta.description}</p>
                  </div>
                  <button type="button" onClick={() => setExpandedTrigger(isOpen ? null : key)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded hover:bg-muted">
                    Edit template
                    {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {isOpen && (
                  <div className="p-4 space-y-3 border-t border-border bg-background">
                    <div className="flex flex-wrap gap-1">
                      {meta.vars.map(v => (
                        <span key={v} className="px-1.5 py-0.5 bg-muted border border-border rounded text-[10px] font-mono text-muted-foreground">
                          {`{{${v}}}`}
                        </span>
                      ))}
                    </div>
                    <div>
                      <label className="text-xs font-medium text-foreground block mb-1">Subject</label>
                      <input type="text" value={trigger.subject} onChange={e => updateTrigger(key, { subject: e.target.value })}
                        className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-foreground block mb-1">Body</label>
                      <textarea value={trigger.body} onChange={e => updateTrigger(key, { body: e.target.value })} rows={8}
                        className="w-full text-sm bg-muted border border-border rounded-[var(--radius)] px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary text-foreground font-mono resize-y" />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
