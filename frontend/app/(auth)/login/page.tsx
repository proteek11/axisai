'use client';

import React, { useState, Suspense, useEffect, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Eye, EyeOff, Zap, ArrowRight, BookOpen, ShieldAlert, X, Mail, KeyRound, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { useAuthStore } from '@/lib/stores/auth-store';

/* ── Schemas ── */
const loginSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});
type LoginForm = z.infer<typeof loginSchema>;

/* ── Branding cache ── */
const BRANDING_CACHE_KEY = 'axis_branding_v1';

function useBrandingMeta() {
  const [siteName, setSiteName] = useState('Axis AI');
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);

  useEffect(() => {
    try {
      const cached = localStorage.getItem(BRANDING_CACHE_KEY);
      if (cached) {
        const d = JSON.parse(cached);
        if (d.site_name) setSiteName(d.site_name);
        if (d.logo_url)  setLogoUrl(d.logo_url);
      }
    } catch {}

    fetch('/api/branding')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!d) return; if (d.site_name) setSiteName(d.site_name); if (d.logo_url) setLogoUrl(d.logo_url); })
      .catch(() => {});

    fetch('/api/auth/settings')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.google_auth_enabled) setGoogleEnabled(true); })
      .catch(() => {});
  }, []);

  return { siteName, logoUrl, googleEnabled };
}

/* ════════════════════════════════════════════════════════════
   Forgot Password Modal  (3-step: email → OTP → new password)
════════════════════════════════════════════════════════════ */
type FpStep = 'email' | 'otp' | 'password';

function ForgotPasswordModal({ onClose }: { onClose: () => void }) {
  const [step, setStep]           = useState<FpStep>('email');
  const [email, setEmail]         = useState('');
  const [otp, setOtp]             = useState(['', '', '', '', '', '']);
  const [resetToken, setResetToken] = useState('');
  const [newPw, setNewPw]         = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw]       = useState(false);
  const [loading, setLoading]     = useState(false);
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  /* step 1 — send OTP */
  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    try {
      const r = await fetch('/api/auth/forgot-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      const d = await r.json();
      toast.success(d.detail || 'Code sent — check your inbox');
      setStep('otp');
    } catch { toast.error('Network error'); }
    finally { setLoading(false); }
  };

  /* OTP input helpers */
  const handleOtpChange = (idx: number, val: string) => {
    const digit = val.replace(/\D/g, '').slice(-1);
    const next = [...otp];
    next[idx] = digit;
    setOtp(next);
    if (digit && idx < 5) otpRefs.current[idx + 1]?.focus();
  };
  const handleOtpKeyDown = (idx: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !otp[idx] && idx > 0) otpRefs.current[idx - 1]?.focus();
  };
  const handleOtpPaste = (e: React.ClipboardEvent) => {
    const digits = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6).split('');
    const next = [...otp];
    digits.forEach((d, i) => { next[i] = d; });
    setOtp(next);
    otpRefs.current[Math.min(digits.length, 5)]?.focus();
  };

  /* step 2 — verify OTP */
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = otp.join('');
    if (code.length < 6) { toast.error('Enter all 6 digits'); return; }
    setLoading(true);
    try {
      const r = await fetch('/api/auth/verify-otp', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, otp: code }),
      });
      if (!r.ok) { const d = await r.json(); toast.error(d.detail || 'Invalid code'); return; }
      const d = await r.json();
      setResetToken(d.reset_token);
      toast.success('Code verified!');
      setStep('password');
    } catch { toast.error('Network error'); }
    finally { setLoading(false); }
  };

  /* step 3 — reset password */
  const handleResetPw = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw.length < 8)  { toast.error('Password must be at least 8 characters'); return; }
    if (newPw !== confirmPw) { toast.error('Passwords do not match'); return; }
    setLoading(true);
    try {
      const r = await fetch('/api/auth/reset-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset_token: resetToken, new_password: newPw }),
      });
      if (!r.ok) { const d = await r.json(); toast.error(d.detail || 'Reset failed'); return; }
      toast.success('Password updated! Please sign in.');
      onClose();
    } catch { toast.error('Network error'); }
    finally { setLoading(false); }
  };

  const stepLabel = step === 'email' ? 'Forgot password' : step === 'otp' ? 'Enter your code' : 'Set new password';
  const stepIcon  = step === 'email' ? <Mail className="w-5 h-5" /> : step === 'otp' ? <KeyRound className="w-5 h-5" /> : <Lock className="w-5 h-5" />;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-[var(--radius)] w-full max-w-sm shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2 text-primary font-semibold">
            {stepIcon}
            <span>{stepLabel}</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-6">
          {/* Step indicator */}
          <div className="flex items-center gap-2 mb-6">
            {(['email', 'otp', 'password'] as FpStep[]).map((s, i) => (
              <React.Fragment key={s}>
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors
                  ${step === s ? 'bg-primary text-primary-foreground' :
                    (['email','otp','password'].indexOf(step) > i) ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}`}>
                  {i + 1}
                </div>
                {i < 2 && <div className={`flex-1 h-px transition-colors ${['email','otp','password'].indexOf(step) > i ? 'bg-primary/40' : 'bg-border'}`} />}
              </React.Fragment>
            ))}
          </div>

          {/* ── Step 1: Email ── */}
          {step === 'email' && (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <p className="text-sm text-muted-foreground">Enter the email address on your account and we'll send you a 6-digit code.</p>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com" autoFocus required
                className="w-full px-3.5 py-2.5 rounded-[var(--radius)] border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <button type="submit" disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50">
                {loading ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><Mail className="w-4 h-4" /> Send code</>}
              </button>
            </form>
          )}

          {/* ── Step 2: OTP ── */}
          {step === 'otp' && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <p className="text-sm text-muted-foreground">We sent a 6-digit code to <strong>{email}</strong>. Enter it below.</p>
              <div className="flex gap-2 justify-center" onPaste={handleOtpPaste}>
                {otp.map((digit, i) => (
                  <input
                    key={i} ref={el => { otpRefs.current[i] = el; }}
                    type="text" inputMode="numeric" maxLength={1} value={digit}
                    onChange={e => handleOtpChange(i, e.target.value)}
                    onKeyDown={e => handleOtpKeyDown(i, e)}
                    className="w-10 h-12 text-center text-xl font-bold rounded-[var(--radius)] border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                ))}
              </div>
              <button type="submit" disabled={loading || otp.join('').length < 6}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50">
                {loading ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><KeyRound className="w-4 h-4" /> Verify code</>}
              </button>
              <button type="button" onClick={() => setStep('email')}
                className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors">
                ← Back to email
              </button>
            </form>
          )}

          {/* ── Step 3: New password ── */}
          {step === 'password' && (
            <form onSubmit={handleResetPw} className="space-y-4">
              <p className="text-sm text-muted-foreground">Choose a strong password of at least 8 characters.</p>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={newPw} onChange={e => setNewPw(e.target.value)}
                  placeholder="New password" autoFocus
                  className="w-full px-3.5 py-2.5 pr-10 rounded-[var(--radius)] border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <button type="button" onClick={() => setShowPw(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <input type={showPw ? 'text' : 'password'} value={confirmPw} onChange={e => setConfirmPw(e.target.value)}
                placeholder="Confirm password"
                className="w-full px-3.5 py-2.5 rounded-[var(--radius)] border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <button type="submit" disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50">
                {loading ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><Lock className="w-4 h-4" /> Update password</>}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════
   Google Sign-In Button
════════════════════════════════════════════════════════════ */
function GoogleButton() {
  return (
    <a href="/api/auth/google/start"
      className="w-full flex items-center justify-center gap-3 px-4 py-2.5 border border-border bg-card rounded-[var(--radius)] text-sm font-medium hover:bg-muted/50 transition-colors">
      {/* Google G logo */}
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
      </svg>
      Continue with Google
    </a>
  );
}

/* ════════════════════════════════════════════════════════════
   Main Login Page
════════════════════════════════════════════════════════════ */
function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const from   = searchParams.get('from') || '/dashboard';
  const reason = searchParams.get('reason');
  const errorParam = searchParams.get('error');
  const { setAuth, user } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [showForgot, setShowForgot]     = useState(false);
  const { siteName, logoUrl, googleEnabled } = useBrandingMeta();

  React.useEffect(() => { if (user) { window.location.href = from; } }, [user, from]);

  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (data: LoginForm) => {
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data), credentials: 'include',
      });
      if (!r.ok) { const err = await r.json().catch(() => ({})); toast.error(err.detail || 'Login failed. Check your credentials.'); return; }
      const result = await r.json();
      setAuth(result.user, result.access_token);
      toast.success(`Welcome back, ${result.user.full_name || result.user.email}!`);
      window.location.href = from;
    } catch { toast.error('Network error. Please try again.'); }
  };

  return (
    <>
      {showForgot && <ForgotPasswordModal onClose={() => setShowForgot(false)} />}

      <div className="min-h-screen bg-background flex">
        {/* Left panel */}
        <div className="hidden lg:flex lg:w-1/2 bg-primary flex-col justify-between p-12">
          <div className="flex items-center gap-3">
            {logoUrl
              ? <img src={logoUrl} alt={siteName} className="h-10 w-auto object-contain" />
              : <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center"><Zap className="w-5 h-5 text-white" /></div>}
            <span className="text-white font-bold text-xl">{siteName}</span>
          </div>
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
                <BookOpen className="w-6 h-6 text-white" />
              </div>
            </div>
            <h1 className="text-4xl font-bold text-white leading-tight mb-4">Intelligent Learning,<br />Powered by AI</h1>
            <p className="text-primary-foreground/70 text-lg leading-relaxed">
              Upload any content — PDFs, videos, links — and get instant summaries, flashcards, quizzes, and glossaries. Build Learning Spaces your students will love.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[{ label: 'Content Items', value: '10K+' }, { label: 'AI Outputs', value: '50K+' }, { label: 'Learners', value: '5K+' }].map(s => (
              <div key={s.label} className="bg-white/10 rounded-xl p-4">
                <p className="text-2xl font-bold text-white">{s.value}</p>
                <p className="text-primary-foreground/60 text-xs uppercase tracking-wide mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel */}
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md">
            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-2 mb-8">
              {logoUrl
                ? <img src={logoUrl} alt={siteName} className="h-8 w-auto object-contain" />
                : <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center"><Zap className="w-4 h-4 text-white" /></div>}
              <span className="font-bold text-lg text-primary">{siteName}</span>
            </div>

            {/* Idle / error banners */}
            {reason === 'idle' && (
              <div className="mb-4 flex items-center gap-2.5 px-4 py-3 rounded-[var(--radius)] bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                <ShieldAlert className="w-4 h-4 flex-shrink-0" />
                <span>Your session expired due to inactivity. Please sign in again.</span>
              </div>
            )}
            {errorParam && (
              <div className="mb-4 flex items-center gap-2.5 px-4 py-3 rounded-[var(--radius)] bg-red-50 border border-red-200 text-red-800 text-sm">
                <ShieldAlert className="w-4 h-4 flex-shrink-0" />
                <span>Sign-in failed: {decodeURIComponent(errorParam).replace(/_/g, ' ')}</span>
              </div>
            )}

            <div className="mb-8">
              <h2 className="text-3xl font-bold text-primary">Sign in</h2>
              <p className="text-muted-foreground mt-1">Enter your credentials to continue</p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Email address</label>
                <input {...register('email')} type="email" autoComplete="email" placeholder="you@example.com"
                  className="w-full px-3.5 py-2.5 rounded-[var(--radius)] border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring transition-shadow placeholder:text-muted-foreground" />
                {errors.email && <p className="text-destructive text-xs mt-1">{errors.email.message}</p>}
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-sm font-medium">Password</label>
                  <button type="button" onClick={() => setShowForgot(true)}
                    className="text-xs text-primary hover:underline">Forgot password?</button>
                </div>
                <div className="relative">
                  <input {...register('password')} type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="••••••••"
                    className="w-full px-3.5 py-2.5 pr-10 rounded-[var(--radius)] border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring transition-shadow placeholder:text-muted-foreground" />
                  <button type="button" onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" tabIndex={-1}>
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {errors.password && <p className="text-destructive text-xs mt-1">{errors.password.message}</p>}
              </div>
              <button type="submit" disabled={isSubmitting}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 mt-2 bg-primary text-primary-foreground rounded-[var(--radius)] text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                {isSubmitting
                  ? <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in...</>
                  : <>Sign in <ArrowRight className="w-4 h-4" /></>}
              </button>
            </form>

            {/* Google SSO — only shown when admin has enabled it */}
            {googleEnabled && (
              <>
                <div className="flex items-center gap-3 my-5">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-xs text-muted-foreground">or</span>
                  <div className="flex-1 h-px bg-border" />
                </div>
                <GoogleButton />
              </>
            )}

            <p className="text-center text-xs text-muted-foreground mt-8">
              Contact your administrator if you don&apos;t have an account.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>}>
      <LoginContent />
    </Suspense>
  );
}
