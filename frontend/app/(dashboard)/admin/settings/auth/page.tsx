'use client';

import { useEffect, useState } from 'react';
import { Shield, Loader2, ToggleLeft, ToggleRight } from 'lucide-react';
import { toast } from 'sonner';

export default function AuthSettingsPage() {
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
    <div className="p-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center">
          <Shield className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-foreground">Authentication Settings</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Control how users sign in to Axis AI.
          </p>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-4">
          Login Methods
        </h2>

        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="divide-y divide-border">
            {/* Email / password — always on */}
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium">Email &amp; Password</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Standard email + password login. Always enabled.
                </p>
              </div>
              <span className="text-xs font-medium text-green-600 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                Always On
              </span>
            </div>

            {/* Google OAuth */}
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium">Google Sign-In</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Allow users to sign in using their Google account.
                  Requires <code className="text-[11px] bg-muted px-1 rounded">GOOGLE_CLIENT_ID</code> and{' '}
                  <code className="text-[11px] bg-muted px-1 rounded">GOOGLE_CLIENT_SECRET</code> in <code className="text-[11px] bg-muted px-1 rounded">.env</code>.
                </p>
              </div>
              <button
                type="button"
                onClick={toggle}
                disabled={saving}
                className="flex items-center gap-1.5 text-sm font-medium transition-colors disabled:opacity-50 flex-shrink-0 ml-4"
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

            {/* LTI */}
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm font-medium">LTI 1.3 (Single Sign-On)</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Allow Moodle and other LMS platforms to authenticate learners via LTI.{' '}
                  <a href="/admin/lti" className="text-primary underline">Configure LTI platforms →</a>
                </p>
              </div>
              <span className="text-xs font-medium text-muted-foreground bg-muted border border-border px-2 py-0.5 rounded-full">
                Configured separately
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
