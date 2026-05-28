/**
 * Zustand auth store — holds the access token and user in memory.
 * The refresh token lives in an HttpOnly cookie (set by Next.js API routes).
 * Access token is stored in memory only — never localStorage (XSS risk).
 */
'use client';

import { create } from 'zustand';

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: 'admin' | 'creator' | 'learner';
  tenant_id: string;
  is_active: boolean;
  avatar_url?: string | null;
  team_id?: string | null;
  team_name?: string | null;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;

  setAuth: (user: AuthUser, accessToken: string) => void;
  clearAuth: () => void;
  setLoading: (v: boolean) => void;
  updateUser: (partial: Partial<AuthUser>) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isLoading: true,

  setAuth: (user, accessToken) => set({ user, accessToken, isLoading: false }),
  clearAuth: () => set({ user: null, accessToken: null, isLoading: false }),
  setLoading: (v) => set({ isLoading: v }),
  updateUser: (partial) =>
    set((state) => ({
      user: state.user ? { ...state.user, ...partial } : state.user,
    })),
}));
