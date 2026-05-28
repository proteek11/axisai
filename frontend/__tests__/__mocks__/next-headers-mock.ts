/**
 * Minimal next/headers stub for Vitest.
 *
 * The real next/headers uses React's async local storage context and can only
 * be called inside Next.js Server Components or Route Handlers running on the
 * Next.js runtime.  In Vitest (Node), calling it throws immediately.
 *
 * This stub exports a vi.fn() for `cookies` so tests can control what the
 * cookie store returns via vi.mocked(cookies).mockReturnValue(...).
 */
import { vi } from 'vitest';

export const cookies = vi.fn(() => ({
  get: vi.fn((_name: string) => undefined as { value: string } | undefined),
  getAll: vi.fn(() => [] as { name: string; value: string }[]),
  has: vi.fn((_name: string) => false),
  set: vi.fn(),
  delete: vi.fn(),
}));

export const headers = vi.fn(() => new Headers());
