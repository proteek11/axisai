/**
 * Unit tests for middleware.ts
 *
 * The middleware does:
 *  - Public path passthrough
 *  - JWT decode (no signature verify) from axis_access cookie
 *  - Token refresh via /api/auth/refresh when access token is expired
 *  - Role-based access control for /admin, /spaces, /api/admin, /api/spaces
 *  - Redirect to /login when unauthenticated (page routes)
 *  - 401 JSON response when unauthenticated (API routes)
 *  - 403 / redirect to /dashboard when role insufficient
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest, NextResponse } from 'next/server';
import { middleware } from '@/middleware';
import { createJwt, createExpiredJwt } from '@/__tests__/helpers/setup';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeReq(
  pathname: string,
  options: {
    accessToken?: string;
    refreshToken?: string;
    authHeader?: string;
  } = {}
): NextRequest {
  const url = `http://localhost:3000${pathname}`;
  const cookieParts: string[] = [];
  if (options.accessToken) cookieParts.push(`axis_access=${options.accessToken}`);
  if (options.refreshToken) cookieParts.push(`axis_refresh=${options.refreshToken}`);

  const headers: Record<string, string> = {};
  if (cookieParts.length) headers['cookie'] = cookieParts.join('; ');
  if (options.authHeader) headers['authorization'] = options.authHeader;

  return new NextRequest(url, { headers });
}

// Tokens for each role
const adminToken = createJwt({ sub: 'u1', email: 'admin@test.com', role: 'admin' });
const creatorToken = createJwt({ sub: 'u2', email: 'creator@test.com', role: 'creator' });
const learnerToken = createJwt({ sub: 'u3', email: 'learner@test.com', role: 'learner' });
const expiredToken = createExpiredJwt({ sub: 'u4', role: 'admin' });

// ─── Public paths ─────────────────────────────────────────────────────────────

describe('Public paths — always pass through', () => {
  it('allows / (landing page)', async () => {
    const res = await middleware(makeReq('/'));
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });

  it('allows /login', async () => {
    const res = await middleware(makeReq('/login'));
    expect(res.status).not.toBe(401);
    expect(res.status).not.toBe(403);
  });

  it('allows /api/auth/login', async () => {
    const res = await middleware(makeReq('/api/auth/login'));
    expect(res.status).not.toBe(401);
  });

  it('allows /api/auth/refresh', async () => {
    const res = await middleware(makeReq('/api/auth/refresh'));
    expect(res.status).not.toBe(401);
  });

  it('allows /_next/static paths (Next.js internals)', async () => {
    const res = await middleware(makeReq('/_next/static/chunks/main.js'));
    expect(res.status).toBe(200);
  });

  it('allows paths with file extensions (static assets)', async () => {
    const res = await middleware(makeReq('/favicon.ico'));
    expect(res.status).toBe(200);
  });
});

// ─── Unauthenticated access ──────────────────────────────────────────────────

describe('Unauthenticated requests', () => {
  it('redirects to /login when accessing /dashboard without token', async () => {
    const res = await middleware(makeReq('/dashboard'));
    expect(res.status).toBe(307);
    expect(res.headers.get('location')).toContain('/login');
  });

  it('appends ?from= param to redirect so user lands back after login', async () => {
    const res = await middleware(makeReq('/dashboard'));
    const location = res.headers.get('location') ?? '';
    expect(location).toContain('from=%2Fdashboard');
  });

  it('returns 401 JSON when accessing /api/* without token', async () => {
    const res = await middleware(makeReq('/api/spaces'));
    expect(res.status).toBe(401);
    const body = await res.json();
    expect(body.detail).toBeTruthy();
  });

  it('returns 401 for /api/admin routes without token', async () => {
    const res = await middleware(makeReq('/api/admin/users'));
    expect(res.status).toBe(401);
  });
});

// ─── Authenticated — any role ─────────────────────────────────────────────────

describe('Authenticated — any role', () => {
  it('allows admin to access /dashboard', async () => {
    const res = await middleware(makeReq('/dashboard', { accessToken: adminToken }));
    expect(res.status).toBe(200);
  });

  it('allows creator to access /dashboard', async () => {
    const res = await middleware(makeReq('/dashboard', { accessToken: creatorToken }));
    expect(res.status).toBe(200);
  });

  it('allows learner to access /dashboard', async () => {
    const res = await middleware(makeReq('/dashboard', { accessToken: learnerToken }));
    expect(res.status).toBe(200);
  });
});

// ─── Admin-only routes ────────────────────────────────────────────────────────

describe('Admin-only routes (/admin, /api/admin)', () => {
  it('allows admin to access /admin/users', async () => {
    const res = await middleware(makeReq('/admin/users', { accessToken: adminToken }));
    expect(res.status).toBe(200);
  });

  it('redirects creator away from /admin (→ /dashboard)', async () => {
    const res = await middleware(makeReq('/admin/users', { accessToken: creatorToken }));
    expect(res.status).toBe(307);
    expect(res.headers.get('location')).toContain('/dashboard');
  });

  it('redirects learner away from /admin (→ /dashboard)', async () => {
    const res = await middleware(makeReq('/admin', { accessToken: learnerToken }));
    expect(res.status).toBe(307);
    expect(res.headers.get('location')).toContain('/dashboard');
  });

  it('returns 403 for creator on /api/admin routes', async () => {
    const res = await middleware(makeReq('/api/admin/users', { accessToken: creatorToken }));
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.detail).toBe('Forbidden');
  });

  it('returns 403 for learner on /api/admin routes', async () => {
    const res = await middleware(makeReq('/api/admin/status', { accessToken: learnerToken }));
    expect(res.status).toBe(403);
  });

  it('allows admin on /api/admin routes', async () => {
    const res = await middleware(makeReq('/api/admin/status', { accessToken: adminToken }));
    expect(res.status).toBe(200);
  });
});

// ─── Creator + Admin routes ───────────────────────────────────────────────────

describe('Creator/Admin-only routes (/spaces, /api/spaces)', () => {
  it('allows creator to access /spaces', async () => {
    const res = await middleware(makeReq('/spaces', { accessToken: creatorToken }));
    expect(res.status).toBe(200);
  });

  it('allows admin to access /spaces', async () => {
    const res = await middleware(makeReq('/spaces', { accessToken: adminToken }));
    expect(res.status).toBe(200);
  });

  it('redirects learner away from /spaces (→ /dashboard)', async () => {
    const res = await middleware(makeReq('/spaces', { accessToken: learnerToken }));
    expect(res.status).toBe(307);
    expect(res.headers.get('location')).toContain('/dashboard');
  });

  it('allows creator on /api/spaces', async () => {
    const res = await middleware(makeReq('/api/spaces', { accessToken: creatorToken }));
    expect(res.status).toBe(200);
  });

  it('returns 403 for learner on /api/spaces', async () => {
    const res = await middleware(makeReq('/api/spaces', { accessToken: learnerToken }));
    expect(res.status).toBe(403);
  });

  it('allows creator on /api/teams', async () => {
    const res = await middleware(makeReq('/api/teams', { accessToken: creatorToken }));
    expect(res.status).toBe(200);
  });

  it('returns 403 for learner on /api/teams', async () => {
    const res = await middleware(makeReq('/api/teams', { accessToken: learnerToken }));
    expect(res.status).toBe(403);
  });
});

// ─── Expired token + refresh flow ────────────────────────────────────────────

describe('Expired access token + refresh', () => {
  it('calls /api/auth/refresh when access token is expired', async () => {
    const newAccessToken = createJwt({ sub: 'u1', role: 'admin' });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: newAccessToken }),
    });

    const res = await middleware(
      makeReq('/dashboard', {
        accessToken: expiredToken,
        refreshToken: 'valid-refresh-token',
      })
    );

    // Should have refreshed and set new access token cookie
    expect(global.fetch).toHaveBeenCalled();
    const setCookie = res.headers.getSetCookie?.() ?? [];
    const accessCookie = setCookie.find((c: string) => c.startsWith('axis_access='));
    expect(accessCookie).toBeDefined();
  });

  it('redirects to /login when both tokens are expired/missing', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Refresh token expired' }),
    });

    const res = await middleware(
      makeReq('/dashboard', {
        accessToken: expiredToken,
        refreshToken: 'expired-refresh-token',
      })
    );

    expect(res.status).toBe(307);
    expect(res.headers.get('location')).toContain('/login');
  });

  it('returns 401 on /api/* when refresh fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Refresh token expired' }),
    });

    const res = await middleware(
      makeReq('/api/spaces', {
        accessToken: expiredToken,
        refreshToken: 'expired-refresh-token',
      })
    );

    expect(res.status).toBe(401);
  });
});
