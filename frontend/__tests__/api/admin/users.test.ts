/**
 * Unit tests for /api/admin/users (GET list + POST create)
 * Admin-only endpoint.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { GET, POST } from '@/app/api/admin/users/route';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const USERS_LIST = [
  { id: 'u1', email: 'alice@edzlms.com', full_name: 'Alice', role: 'creator', is_active: true },
  { id: 'u2', email: 'bob@edzlms.com', full_name: 'Bob', role: 'learner', is_active: true },
];

const NEW_USER_BODY = {
  email: 'charlie@edzlms.com',
  full_name: 'Charlie',
  password: 'Str0ngP@ss!',
  role: 'learner',
};

const NEW_USER_RESPONSE = { id: 'u3', ...NEW_USER_BODY, is_active: true };

// ─── GET /api/admin/users ─────────────────────────────────────────────────────

describe('GET /api/admin/users', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  it('returns the full user list from FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(USERS_LIST));

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    expect(body).toHaveLength(2);
    expect(body[0].email).toBe('alice@edzlms.com');
  });

  it('calls the correct FastAPI endpoint with admin token', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(USERS_LIST));

    await GET();

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/auth/users');
    expect(opts.headers['Authorization']).toBe('Bearer admin-jwt');
  });

  it('returns 403 when FastAPI rejects non-admin token', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Admin role required'));

    const res = await GET();
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });

  it('returns 500 on fetch failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('DB down'));

    const res = await GET();
    expect(res.status).toBe(500);
  });
});

// ─── POST /api/admin/users ────────────────────────────────────────────────────

describe('POST /api/admin/users', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  it('creates a user and returns 201', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(NEW_USER_RESPONSE, 201));

    const req = new NextRequest('http://localhost:3000/api/admin/users', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(NEW_USER_BODY),
    });
    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.id).toBe('u3');
    expect(body.email).toBe('charlie@edzlms.com');
  });

  it('forwards user data to FastAPI correctly', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(NEW_USER_RESPONSE, 201));

    await POST(
      new NextRequest('http://localhost:3000/api/admin/users', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(NEW_USER_BODY),
      })
    );

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/auth/users');
    expect(opts.method).toBe('POST');
  });

  it('returns 409 when email already exists', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(409, 'Email already registered'));

    const res = await POST(
      new NextRequest('http://localhost:3000/api/admin/users', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(NEW_USER_BODY),
      })
    );
    expect(res.status).toBe(409);
  });

  it('returns 422 on validation error from FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(422, 'Password too short'));

    const res = await POST(
      new NextRequest('http://localhost:3000/api/admin/users', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: 'bad@test.com', password: '123' }),
      })
    );
    expect(res.status).toBe(422);
  });
});
