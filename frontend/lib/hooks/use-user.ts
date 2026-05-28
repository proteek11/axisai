'use client';

import { useAuthStore } from '@/lib/stores/auth-store';

/** Returns the current authenticated user (or null if not logged in). */
export function useUser() {
  return useAuthStore((s) => s.user);
}

/** Returns true if the current user has the given role. */
export function useRole(...roles: string[]) {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  return roles.includes(user.role);
}

/** Returns the access token for making authenticated requests. */
export function useAccessToken() {
  return useAuthStore((s) => s.accessToken);
}
