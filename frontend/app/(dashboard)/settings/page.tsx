'use client';

import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/header';
import { useAuthStore } from '@/lib/stores/auth-store';
import { getInitials } from '@/lib/utils';
import { toast } from 'sonner';
import { Camera, Loader2, User, Lock, Shield, Zap, TrendingUp, Building2 } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

interface TokenBudget {
  used: number;
  limit: number;
  remaining: number;
  pct_used: number;
  has_override: boolean;
}

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

const ROLE_BADGE: Record<string, string> = {
  admin:   'text-purple-600 bg-purple-50 border-purple-200',
  creator: 'text-blue-600   bg-blue-50   border-blue-200',
  learner: 'text-emerald-600 bg-emerald-50 border-emerald-200',
};

export default function SettingsPage() {
  const { user, updateUser } = useAuthStore();

  // Profile form state
  const [fullName, setFullName]               = useState(user?.full_name ?? '');
  const [email, setEmail]                     = useState(user?.email ?? '');
  const [password, setPassword]               = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSaving, setIsSaving]               = useState(false);

  // Avatar state
  const fileInputRef                        = useRef<HTMLInputElement>(null);
  const [avatarPreview, setAvatarPreview]   = useState<string | null>(null);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  const { data: budget } = useQuery<TokenBudget>({
    queryKey: ['me', 'token-budget'],
    queryFn: async () => {
      const res = await fetch('/api/me/token-budget');
      if (!res.ok) throw new Error('Failed');
      return res.json();
    },
  });

  // ── Avatar helpers ────────────────────────────────────────────────────────
  const avatarSrc = avatarPreview
    ?? (user?.avatar_url ? `${API_URL}${user.avatar_url}` : null);

  const handleAvatarClick = () => fileInputRef.current?.click();

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Client-side size guard (5 MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be smaller than 5 MB');
      return;
    }

    // Show instant preview
    const reader = new FileReader();
    reader.onload = (ev) => setAvatarPreview(ev.target?.result as string);
    reader.readAsDataURL(file);

    // Upload
    setIsUploadingAvatar(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch('/api/me/avatar', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Upload failed');
      updateUser({ avatar_url: data.avatar_url });
      toast.success('Profile picture updated');
    } catch (err: any) {
      toast.error(err.message ?? 'Upload failed');
      setAvatarPreview(null); // revert preview on failure
    } finally {
      setIsUploadingAvatar(false);
      // Reset file input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // ── Profile save ──────────────────────────────────────────────────────────
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    if (password && password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    if (password && password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    const payload: Record<string, string> = {};
    if (fullName !== (user?.full_name ?? '')) payload.full_name = fullName;
    if (email !== user?.email)               payload.email = email;
    if (password)                             payload.password = password;

    if (Object.keys(payload).length === 0) {
      toast.info('No changes to save');
      return;
    }

    setIsSaving(true);
    try {
      const res = await fetch('/api/me/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? 'Update failed');
      updateUser({ full_name: data.full_name, email: data.email });
      setPassword('');
      setConfirmPassword('');
      toast.success('Profile updated');
    } catch (err: any) {
      toast.error(err.message ?? 'Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      <Header title="Settings" subtitle="Manage your account and preferences" />

      <div className="page-padding max-w-2xl">

        {/* ── Avatar + account summary ── */}
        <div className="enterprise-card flex items-center gap-5 mb-6">
          {/* Avatar with camera overlay */}
          <div className="relative flex-shrink-0 group">
            <button
              type="button"
              onClick={handleAvatarClick}
              disabled={isUploadingAvatar}
              className="relative w-16 h-16 rounded-full overflow-hidden focus:outline-none
                focus-visible:ring-2 focus-visible:ring-primary/40"
              title="Change profile picture"
            >
              {avatarSrc ? (
                <img
                  src={avatarSrc}
                  alt="Profile"
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-primary/10 flex items-center justify-center">
                  <span className="text-xl font-bold text-primary">
                    {user ? getInitials(user.full_name || user.email) : '?'}
                  </span>
                </div>
              )}

              {/* Camera overlay on hover */}
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center
                opacity-0 group-hover:opacity-100 transition-opacity rounded-full">
                {isUploadingAvatar
                  ? <Loader2 className="w-5 h-5 text-white animate-spin" />
                  : <Camera className="w-5 h-5 text-white" />
                }
              </div>
            </button>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              onChange={handleAvatarChange}
            />
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-semibold text-base text-foreground truncate">
              {user?.full_name || user?.email}
            </p>
            <p className="text-sm text-muted-foreground truncate">{user?.email}</p>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className={`inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full border capitalize ${ROLE_BADGE[user?.role ?? ''] ?? ''}`}>
                {user?.role}
              </span>
              {user?.team_name && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground border border-border rounded-full px-2.5 py-0.5">
                  <Building2 className="w-3 h-3" />
                  {user.team_name}
                </span>
              )}
              <button
                type="button"
                onClick={handleAvatarClick}
                disabled={isUploadingAvatar}
                className="text-xs text-primary hover:underline disabled:opacity-50"
              >
                {isUploadingAvatar ? 'Uploading…' : 'Change photo'}
              </button>
            </div>
          </div>
        </div>

        {/* ── Profile form ── */}
        <div className="enterprise-card mb-6">
          <div className="flex items-center gap-2 mb-5">
            <User className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Profile
            </h2>
          </div>

          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                Full Name
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
                className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                  text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                  text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            <div className="pt-2 border-t border-border">
              <div className="flex items-center gap-2 mb-3">
                <Lock className="w-4 h-4 text-muted-foreground" />
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Change Password
                </p>
              </div>
              <div className="space-y-3">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="New password (leave blank to keep current)"
                  autoComplete="new-password"
                  className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                    text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
                {password && (
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    placeholder="Confirm new password"
                    className="w-full px-3 py-2.5 rounded-[var(--radius)] border border-border bg-background
                      text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                  />
                )}
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="submit"
                disabled={isSaving}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground
                  rounded-[var(--radius)] text-sm font-medium hover:bg-primary/90 transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Saving…</>
                ) : (
                  'Save Changes'
                )}
              </button>
            </div>
          </form>
        </div>

        {/* ── Token budget ── */}
        {budget && (
          <div className="enterprise-card mb-6">
            <div className="flex items-center gap-2 mb-5">
              <Zap className="w-4 h-4 text-primary" />
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                AI Token Budget — This Month
              </h2>
            </div>

            <div className="flex items-end justify-between mb-2">
              <div>
                <p className="text-3xl font-bold text-foreground">{fmtTokens(budget.used)}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  of {fmtTokens(budget.limit)} monthly limit
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-foreground">{fmtTokens(budget.remaining)}</p>
                <p className="text-xs text-muted-foreground">remaining</p>
              </div>
            </div>

            <div className="h-2 bg-muted rounded-full overflow-hidden mb-2">
              <div
                className={`h-full rounded-full transition-all ${pctColor(budget.pct_used)}`}
                style={{ width: `${Math.min(budget.pct_used * 100, 100)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {Math.round(budget.pct_used * 100)}% used
              {budget.has_override && (
                <span className="ml-2 text-amber-600 flex items-center gap-1 inline-flex">
                  <TrendingUp className="w-3 h-3" /> Custom limit applied by admin
                </span>
              )}
            </p>
          </div>
        )}

        {/* ── Account info ── */}
        <div className="enterprise-card">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Account
            </h2>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between py-2 border-b border-border">
              <span className="text-muted-foreground">Role</span>
              <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border capitalize ${ROLE_BADGE[user?.role ?? ''] ?? ''}`}>
                {user?.role}
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-muted-foreground">Authentication</span>
              <span className="text-xs font-medium text-foreground">Email & Password</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
