/**
 * Unit tests for POST /api/auth/login
 *
 * The route proxies credentials to FastAPI, stores the refresh token in an
 * HttpOnly cookie, and returns the access token + user to the client.
 *
 * next/server  → aliased to our stub in vitest.config.ts (no full Next.js runtime needed)
 * next/headers → aliased to our stub in vitest.config.ts
 * global.fetch → mocked per-test to simulate FastAPI responses
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { POST } from '@/app/api/auth/login/route';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const VALID_CREDENTIALS = { email: 'admin@edzlms.com', password: 'secret123' };

const FASTAPI_SUCCESS = {
  access_token: 'eyJhbGciOiJIUzI1NiJ9.access.sig',
  refresh_token: 'eyJhbGciOiJIUzI1NiJ9.refresh.sig',
  user: { id: 'u1', email: 'admin@edzlms.com', full_name: 'Admin User', role: 'admin' },
};

function makeLoginRequest(body: unknown) {
  return new NextRequest('http://localhost:3000/api/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('POST /api/auth/login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('success path', () => {
    it('returns 200 with access_token and user on valid credentials', async () => {
      global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FASTAPI_SUCCESS));

      const res = await POST(makeLoginRequest(VALID_CREDENTIALS));
      const body = await res.json();

      expect(res.status).toBe(200);
      expect(body.access_token).toBe(FASTAPI_SUCCESS.access_token);
      expect(body.user).toEqual(FASTAPI_SUCCESS.user);
      // Refresh token must NOT appear in the JSON body
      expect(body.refresh_token).toBeUndefined();
    });

    it('sets axis_refresh as an HttpOnly cookie', async () => {
      global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FASTAPI_SUCCESS));

      const res = await POST(makeLoginRequest(VALID_CREDENTIALS));
      const setCookie = res.headers.getSetCookie?.() ?? [];

      const refreshCookie = setCookie.find((c: string) => c.startsWith('axis_refresh='));
      expect(refreshCookie).toBeDefined();
      expect(refreshCookie).toContain('HttpOnly');
      expect(refreshCookie).toContain(`axis_refresh=${FASTAPI_SUCCESS.refresh_token}`);
    });

    it('sets axis_access as a readable (non-HttpOnly) cookie', async () => {
      global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FASTAPI_SUCCESS));

      const res = await POST(makeLoginRequest(VALID_CREDENTIALS));
      const setCookie = res.headers.getSetCookie?.() ?? [];

      const accessCookie = setCookie.find((c: string) => c.startsWith('axis_access='));
      expect(accessCookie).toBeDefined();
      expect(accessCookie).not.toContain('HttpOnly');
    });

    it('only forwards email + password to FastAPI — no extra fields', async () => {
      global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FASTAPI_SUCCESS));

      await POST(makeLoginRequest({ ...VALID_CREDENTIALS, malicious: 'injection' }));

      const [, opts] = (global.fetch as any).mock.calls[0];
      const forwarded = JSON.parse(opts.body);
      expect(Object.keys(forwarded)).toEqual(['email', 'password']);
    });
  });

  describe('validation errors', () => {
    it('returns 400 when email is missing', async () => {
      const res = await POST(makeLoginRequest({ password: 'secret123' }));
      expect(res.status).toBe(400);
      const body = await res.json();
      expect(body.detail).toBeTruthy();
    });

    it('returns 400 when password is missing', async () => {
      const res = await POST(makeLoginRequest({ email: 'admin@edzlms.com' }));
      expect(res.status).toBe(400);
    });

    it('returns 400 when body is empty object', async () => {
      const res = await POST(makeLoginRequest({}));
      expect(res.status).toBe(400);
    });

    it('does not call FastAPI when validation fails', async () => {
      global.fetch = vi.fn();
      await POST(makeLoginRequest({ password: 'only-password' }));
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  describe('FastAPI error propagation', () => {
    it('returns 401 when FastAPI rejects credentials', async () => {
      global.fetch = vi.fn().mockResolvedValue(
        mockFetchError(401, 'Incorrect email or password')
      );

      const res = await POST(makeLoginRequest(VALID_CREDENTIALS));
      expect(res.status).toBe(401);
      const body = await res.json();
      expect(body.detail).toBe('Incorrect email or password');
    });

    it('returns 500 on unexpected fetch error', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

      const res = await POST(makeLoginRequest(VALID_CREDENTIALS));
      expect(res.status).toBe(500);
    });
  });
});
