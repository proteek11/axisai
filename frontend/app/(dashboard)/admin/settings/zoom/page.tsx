'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  Video, Save, TestTube2, CheckCircle2, AlertCircle,
  Loader2, ChevronLeft, Eye, EyeOff, ExternalLink, Copy, Info,
} from 'lucide-react';

interface ZoomConfig {
  zoom_enabled: boolean;
  zoom_account_id: string;
  zoom_client_id: string;
  zoom_client_secret_set: boolean;
  zoom_webhook_secret_set: boolean;
  webhook_url: string;
  zoom_default_auto_record: boolean;
  zoom_default_import_recording: boolean;
  zoom_default_import_attendance: boolean;
  zoom_default_generate_ai: boolean;
}

interface ZoomTestResult {
  ok: boolean;
  email?: string;
  account_id?: string;
  plan_type?: number;
  error?: string;
}

const PLAN_LABELS: Record<number, string> = { 1: 'Basic', 2: 'Licensed', 3: 'On-Prem' };

// Webhook URL is always the axis-ai backend, regardless of frontend origin
const WEBHOOK_URL = `${process.env.NEXT_PUBLIC_AXIS_AI_URL || 'https://axisai.edzlms.com'}/api/v1/webhooks/zoom`;

export default function ZoomConfigPage() {
  const [form, setForm] = useState({
    zoom_enabled: true,
    zoom_account_id: '',
    zoom_client_id: '',
    zoom_client_secret: '',
    zoom_webhook_secret: '',
    zoom_default_auto_record: true,
    zoom_default_import_recording: true,
    zoom_default_import_attendance: true,
    zoom_default_generate_ai: true,
  });
  const [showSecret, setShowSecret] = useState(false);
  const [showWebhookSecret, setShowWebhookSecret] = useState(false);
  const [testResult, setTestResult] = useState<ZoomTestResult | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Load current config
  const { data: config, isLoading } = useQuery<ZoomConfig>({
    queryKey: ['zoom-config'],
    queryFn: async () => {
      const res = await fetch('/api/admin/zoom-config');
      if (!res.ok) throw new Error('Failed to load config');
      return res.json();
    },
    onSuccess: (data: ZoomConfig) => {
      if (!loaded) {
        setForm(f => ({
          ...f,
          zoom_enabled: data.zoom_enabled,
          zoom_account_id: data.zoom_account_id || '',
          zoom_client_id: data.zoom_client_id || '',
          zoom_default_auto_record: data.zoom_default_auto_record,
          zoom_default_import_recording: data.zoom_default_import_recording,
          zoom_default_import_attendance: data.zoom_default_import_attendance,
          zoom_default_generate_ai: data.zoom_default_generate_ai,
        }));
        setLoaded(true);
      }
    },
  } as any);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!form.zoom_account_id || !form.zoom_client_id) throw new Error('Account ID and Client ID are required');
      if (!form.zoom_client_secret && !config?.zoom_client_secret_set) throw new Error('Client Secret is required');
      if (!form.zoom_webhook_secret && !config?.zoom_webhook_secret_set) throw new Error('Webhook Secret is required');

      const body: Record<string, any> = { ...form };
      // If secrets are blank + already set, don't send them (keep existing)
      if (!form.zoom_client_secret) delete body.zoom_client_secret;
      if (!form.zoom_webhook_secret) delete body.zoom_webhook_secret;
      // But backend requires them — so if existing, send a placeholder... actually we need to resend
      // Solution: if blank + already set, skip saving (user didn't change it)
      // We'll handle this by sending only when non-blank
      if (!form.zoom_client_secret && config?.zoom_client_secret_set) {
        // Keep existing — but API requires these fields. Re-fetch won't work since secrets are masked.
        // UI should inform user: "leave blank to keep existing"
        body.zoom_client_secret = '<<KEEP_EXISTING>>';
      }
      if (!form.zoom_webhook_secret && config?.zoom_webhook_secret_set) {
        body.zoom_webhook_secret = '<<KEEP_EXISTING>>';
      }

      const res = await fetch('/api/admin/zoom-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Save failed');
      }
      return res.json();
    },
    onSuccess: () => toast.success('Zoom configuration saved'),
    onError: (err: Error) => toast.error(err.message),
  });

  const testMutation = useMutation({
    mutationFn: async (): Promise<ZoomTestResult> => {
      const res = await fetch('/api/admin/zoom-config/test', { method: 'POST' });
      return res.json();
    },
    onSuccess: (data) => {
      setTestResult(data);
      if (data.ok) toast.success('Zoom connection successful!');
      else toast.error(`Zoom test failed: ${data.error}`);
    },
    onError: () => toast.error('Test request failed'),
  });

  const toggle = (key: string) => setForm(f => ({ ...f, [key]: !(f as any)[key] }));

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Back */}
      <Link
        href="/admin/settings"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
      >
        <ChevronLeft className="w-4 h-4" />
        Admin Settings
      </Link>

      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
          <Video className="w-5 h-5 text-blue-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-primary">Zoom Integration</h1>
          <p className="text-sm text-muted-foreground">Server-to-Server OAuth for live class scheduling</p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-6">

          {/* Setup guide */}
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-[var(--radius)] text-sm text-blue-800 space-y-1">
            <p className="font-semibold flex items-center gap-1.5"><Info className="w-4 h-4" /> Setup steps</p>
            <ol className="list-decimal ml-4 space-y-0.5 text-blue-700">
              <li>In Zoom Marketplace, create a <strong>Server-to-Server OAuth App</strong></li>
              <li>Add scopes: <code className="bg-blue-100 px-1 rounded">meeting:write:admin</code>, <code className="bg-blue-100 px-1 rounded">report:read:admin</code>, <code className="bg-blue-100 px-1 rounded">cloud_recording:read:admin</code></li>
              <li>Copy the Account ID, Client ID, Client Secret below</li>
              <li>Under <strong>Event Subscriptions</strong>, set webhook URL to the URL shown below</li>
              <li>Subscribe to: <code className="bg-blue-100 px-1 rounded">meeting.ended</code>, <code className="bg-blue-100 px-1 rounded">recording.completed</code></li>
              <li>Copy the Webhook Secret Token below</li>
            </ol>
          </div>

          {/* Enable toggle */}
          <div className="flex items-center justify-between p-4 border border-border rounded-[var(--radius)]">
            <div>
              <p className="text-sm font-semibold text-foreground">Enable Zoom Integration</p>
              <p className="text-xs text-muted-foreground">Allow creators to schedule Zoom live classes</p>
            </div>
            <button
              onClick={() => toggle('zoom_enabled')}
              style={{ width: 40, height: 22 }}
              className={`rounded-full transition-colors relative flex-shrink-0 ${form.zoom_enabled ? 'bg-primary' : 'bg-muted'}`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                form.zoom_enabled ? 'translate-x-5' : 'translate-x-0.5'
              }`} style={{ width: 18, height: 18 }} />
            </button>
          </div>

          {/* Credentials */}
          <div className="border border-border rounded-[var(--radius)] overflow-hidden">
            <div className="px-4 py-3 bg-muted/30 border-b border-border">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">OAuth Credentials</p>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">
                  Account ID *
                </label>
                <input
                  value={form.zoom_account_id}
                  onChange={e => setForm(f => ({ ...f, zoom_account_id: e.target.value }))}
                  placeholder="e.g. AbCdEfGhIj"
                  className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">
                  Client ID *
                </label>
                <input
                  value={form.zoom_client_id}
                  onChange={e => setForm(f => ({ ...f, zoom_client_id: e.target.value }))}
                  placeholder="e.g. XXXXXXXXXXXXXXXXXXXX"
                  className="w-full border border-border rounded-[var(--radius)] px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">
                  Client Secret {config?.zoom_client_secret_set ? '(leave blank to keep existing)' : '*'}
                </label>
                <div className="relative">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    value={form.zoom_client_secret}
                    onChange={e => setForm(f => ({ ...f, zoom_client_secret: e.target.value }))}
                    placeholder={config?.zoom_client_secret_set ? '••••••••••••••• (set)' : 'Paste client secret'}
                    className="w-full border border-border rounded-[var(--radius)] px-3 py-2 pr-10 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold uppercase tracking-widest text-muted-foreground block mb-1">
                  Webhook Secret Token {config?.zoom_webhook_secret_set ? '(leave blank to keep existing)' : '*'}
                </label>
                <div className="relative">
                  <input
                    type={showWebhookSecret ? 'text' : 'password'}
                    value={form.zoom_webhook_secret}
                    onChange={e => setForm(f => ({ ...f, zoom_webhook_secret: e.target.value }))}
                    placeholder={config?.zoom_webhook_secret_set ? '••••••••••••••• (set)' : 'Paste webhook secret token'}
                    className="w-full border border-border rounded-[var(--radius)] px-3 py-2 pr-10 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowWebhookSecret(!showWebhookSecret)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showWebhookSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Webhook URL — always visible so admin can set it in Zoom before saving credentials */}
          <div className="border border-border rounded-[var(--radius)] overflow-hidden">
            <div className="px-4 py-3 bg-muted/30 border-b border-border">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Your Webhook URL</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Paste this in your Zoom app → Event Subscriptions → Endpoint URL
              </p>
            </div>
            <div className="p-4 flex items-center gap-2">
              <code className="flex-1 text-xs bg-muted px-3 py-2 rounded-[var(--radius)] truncate text-foreground">
                {WEBHOOK_URL}
              </code>
              <button
                onClick={() => { navigator.clipboard.writeText(WEBHOOK_URL); toast.success('Copied!'); }}
                className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                title="Copy webhook URL"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Default settings */}
          <div className="border border-border rounded-[var(--radius)] overflow-hidden">
            <div className="px-4 py-3 bg-muted/30 border-b border-border">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Platform Defaults</p>
              <p className="text-xs text-muted-foreground mt-0.5">Creators can override these per class</p>
            </div>
            <div className="divide-y divide-border">
              {([
                { key: 'zoom_default_auto_record',        label: 'Auto-record meetings',                desc: 'Cloud recording starts automatically' },
                { key: 'zoom_default_import_recording',   label: 'Import recording to learning space',  desc: 'Download and attach MP4 after class ends' },
                { key: 'zoom_default_import_attendance',  label: 'Import attendance report',            desc: 'Save participant join/leave times' },
                { key: 'zoom_default_generate_ai',        label: 'Generate AI outputs from recording',  desc: 'Summary, quiz, flashcards from the MP4' },
              ] as Array<{ key: string; label: string; desc: string }>).map(({ key, label, desc }) => (
                <div key={key} className="flex items-center justify-between p-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">{label}</p>
                    <p className="text-xs text-muted-foreground">{desc}</p>
                  </div>
                  <button
                    onClick={() => toggle(key)}
                    style={{ width: 40, height: 22 }}
                    className={`rounded-full transition-colors relative flex-shrink-0 ml-4 ${(form as any)[key] ? 'bg-primary' : 'bg-muted'}`}
                  >
                    <span className={`absolute top-0.5 rounded-full bg-white shadow transition-transform ${
                      (form as any)[key] ? 'translate-x-5' : 'translate-x-0.5'
                    }`} style={{ width: 18, height: 18 }} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Test result */}
          {testResult && (
            <div className={`p-4 border rounded-[var(--radius)] text-sm ${
              testResult.ok
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-700'
            }`}>
              {testResult.ok ? (
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                  <div>
                    <p className="font-semibold">Connection successful!</p>
                    <p className="text-xs mt-0.5">
                      Account: {testResult.email} · Plan: {PLAN_LABELS[testResult.plan_type ?? 0] ?? 'Unknown'}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <div>
                    <p className="font-semibold">Connection failed</p>
                    <p className="text-xs mt-0.5">{testResult.error}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex justify-between items-center pt-2">
            <button
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending || !config?.zoom_client_secret_set}
              className="flex items-center gap-2 px-4 py-2 text-sm border border-border rounded-[var(--radius)] text-foreground hover:bg-muted/50 disabled:opacity-50 transition-colors"
            >
              {testMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <TestTube2 className="w-4 h-4" />}
              Test Connection
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 px-5 py-2 text-sm bg-primary text-primary-foreground rounded-[var(--radius)] font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Configuration
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
