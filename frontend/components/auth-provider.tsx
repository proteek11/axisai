'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/stores/auth-store';

/**
 * AuthProvider
 *
 * 1. Session restore: on mount, calls /api/auth/me (or /api/auth/refresh)
 *    to rehydrate the in-memory auth store from the HttpOnly refresh cookie.
 *    This makes hard-refresh work seamlessly.
 *
 * 2. Idle timeout: if the user has no mouse/keyboard/touch/scroll activity
 *    for IDLE_TIMEOUT_MS (60 minutes), the session is automatically terminated:
 *    - Refresh token is revoked on the server (POST /api/auth/logout)
 *    - In-memory auth store is cleared
 *    - Browser is redirected to /login?reason=idle
 */

const IDLE_TIMEOUT_MS = 60 * 60 * 1000; // 60 minutes
const IDLE_CHECK_INTERVAL_MS = 60 * 1000; // check every 1 minute

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setAuth, clearAuth, setLoading, user } = useAuthStore();
  const router = useRouter();
  const lastActivityRef = useRef<number>(Date.now());

  // ── Session restore ───────────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;

    async function restoreSession() {
      setLoading(true);
      try {
        const meResponse = await fetch('/api/auth/me', { credentials: 'include' });

        if (meResponse.ok) {
          const data = await meResponse.json();
          if (mounted) setAuth(data.user, data.access_token);
          return;
        }

        // Access token expired/missing — try refresh cookie
        const refreshResponse = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include',
        });

        if (refreshResponse.ok) {
          const data = await refreshResponse.json();
          if (mounted) setAuth(data.user, data.access_token);
        } else {
          if (mounted) clearAuth();
        }
      } catch {
        if (mounted) clearAuth();
      }
    }

    restoreSession();
    return () => { mounted = false; };
  }, [setAuth, clearAuth, setLoading]);

  // ── Idle timeout ──────────────────────────────────────────────────────────
  useEffect(() => {
    // Only run the idle timer when a user is authenticated
    if (!user) return;

    const resetActivity = () => {
      lastActivityRef.current = Date.now();
    };

    const EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
    EVENTS.forEach((ev) => window.addEventListener(ev, resetActivity, { passive: true }));

    const idleTimer = setInterval(async () => {
      const idleMs = Date.now() - lastActivityRef.current;
      if (idleMs >= IDLE_TIMEOUT_MS) {
        clearInterval(idleTimer);
        // Revoke server-side refresh token
        try {
          await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
        } catch {
          // Best-effort — clear client state regardless
        }
        clearAuth();
        router.replace('/login?reason=idle');
      }
    }, IDLE_CHECK_INTERVAL_MS);

    return () => {
      clearInterval(idleTimer);
      EVENTS.forEach((ev) => window.removeEventListener(ev, resetActivity));
    };
  }, [user, clearAuth, router]);

  return <>{children}</>;
}
