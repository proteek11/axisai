/**
 * Shared test utilities for axis-frontend
 *
 * - createJwt()       build a fake (unsigned) JWT for middleware tests
 * - mockCookies()     vi-mock helper for next/headers
 * - makeRequest()     factory for NextRequest test instances
 */
import { vi } from 'vitest';
import { NextRequest } from 'next/server';

// ─── JWT helpers ────────────────────────────────────────────────────────────

export interface JwtPayload {
  sub?: string;
  email?: string;
  role?: 'admin' | 'creator' | 'learner';
  exp?: number; // unix seconds
  [key: string]: unknown;
}

/**
 * Build a minimal, non-signed JWT string.
 * The middleware only does a base64-decode (no signature verify), so this is
 * sufficient for middleware unit tests.
 */
export function createJwt(payload: JwtPayload, expiresInSeconds = 3600): string {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const exp = Math.floor(Date.now() / 1000) + expiresInSeconds;
  const body = Buffer.from(JSON.stringify({ exp, ...payload })).toString('base64url');
  return `${header}.${body}.fake-sig`;
}

/** Returns an already-expired JWT (exp in the past). */
export function createExpiredJwt(payload: JwtPayload = {}): string {
  return createJwt(payload, -60); // expired 60 s ago
}

// ─── Cookie mock ────────────────────────────────────────────────────────────

/**
 * Returns a jest-mock-compatible cookie store.
 * Usage inside a beforeEach after vi.mock('next/headers', ...) at module scope.
 */
export function buildCookieStore(cookieMap: Record<string, string>) {
  return {
    get: vi.fn((name: string) => {
      const val = cookieMap[name];
      return val !== undefined ? { value: val } : undefined;
    }),
  };
}

// ─── NextRequest factory ────────────────────────────────────────────────────

interface MakeRequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  searchParams?: Record<string, string>;
  cookies?: Record<string, string>;
}

/**
 * Build a NextRequest for route handler tests.
 * Uses the standard WHATWG Request constructor which NextRequest extends.
 */
export function makeRequest(
  path: string,
  { method = 'GET', body, headers = {}, searchParams = {}, cookies = {} }: MakeRequestOptions = {}
): NextRequest {
  const url = new URL(path, 'http://localhost:3000');
  for (const [k, v] of Object.entries(searchParams)) {
    url.searchParams.set(k, v);
  }

  // Build cookie header string
  const cookieHeader = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');

  const reqHeaders: Record<string, string> = { ...headers };
  if (cookieHeader) reqHeaders['cookie'] = cookieHeader;
  if (body) reqHeaders['content-type'] = 'application/json';

  return new NextRequest(url.toString(), {
    method,
    headers: reqHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

// ─── Fetch mock helpers ──────────────────────────────────────────────────────

/** Build a Response-like object that vitest fetch mocks can return. */
export function mockFetchOk(data: unknown, status = 200) {
  return Promise.resolve({
    ok: true,
    status,
    json: async () => data,
  } as Response);
}

export function mockFetchError(status: number, detail = 'Error from FastAPI') {
  return Promise.resolve({
    ok: false,
    status,
    json: async () => ({ detail }),
  } as Response);
}
