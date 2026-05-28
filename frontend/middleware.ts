/**
 * Next.js middleware — role-based route protection.
 *
 * Protected routes:
 *   /dashboard/*   → any authenticated user
 *   /spaces/*      → admin | creator
 *   /admin/*       → admin only
 *   /learn/*       → learner | creator | admin (or guest token for /learn/guest/*)
 *   /api/admin/*   → admin role in JWT
 *   /api/spaces/new/*   → admin | creator role in JWT (learners can GET /api/spaces)
 *   /api/teams/*  → admin | creator role in JWT
 *   /api/admin/users/*  → admin role in JWT
 *
 * The refresh token (HttpOnly cookie: axis_refresh) is used to issue a new
 * access token when the in-memory token is absent. The middleware only does
 * a lightweight JWT decode (no signature verify — that happens in API routes).
 * Signature is verified by FastAPI on every API call.
 */

import { NextRequest, NextResponse } from 'next/server';

const PUBLIC_PATHS = [
  '/',          // landing page — always public
  '/login',
  '/api/auth/login',
  '/api/auth/refresh',
  '/learn/guest',   // guest share-token paths
];

const ROLE_PATHS: Record<string, string[]> = {
  '/admin': ['admin'],
  '/api/admin': ['admin'],
  '/spaces': ['admin', 'creator'],
  // NOTE: /api/spaces is intentionally NOT restricted here — learners need
  // GET /api/spaces to load their library. The FastAPI backend enforces RBAC:
  // learners only see spaces they've been granted access to.
  // Only restrict the write/management sub-routes.
  '/api/spaces/new': ['admin', 'creator'],
  '/api/teams': ['admin', 'creator'],
};

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const json = Buffer.from(base64, 'base64').toString('utf8');
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function isTokenExpired(payload: Record<string, unknown>): boolean {
  const exp = payload.exp as number | undefined;
  if (!exp) return true;
  return Date.now() / 1000 > exp;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always allow public paths
  if (PUBLIC_PATHS.some((p) => p === '/' ? pathname === '/' : pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow static files and Next.js internals
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.includes('.')
  ) {
    return NextResponse.next();
  }

  // Extract access token from Authorization header (set by client on API routes)
  // or from the axis_access cookie (set server-side after login)
  const accessToken =
    request.cookies.get('axis_access')?.value ||
    request.headers.get('authorization')?.replace('Bearer ', '');

  const refreshToken = request.cookies.get('axis_refresh')?.value;

  let payload: Record<string, unknown> | null = null;

  if (accessToken) {
    payload = decodeJwtPayload(accessToken);
    if (payload && isTokenExpired(payload)) {
      payload = null; // will try refresh below
    }
  }

  // If no valid access token, try to refresh using the HttpOnly cookie
  if (!payload && refreshToken) {
    try {
      const refreshUrl = new URL('/api/auth/refresh', request.url);
      const refreshResponse = await fetch(refreshUrl.toString(), {
        method: 'POST',
        headers: {
          // Forward the cookie header so the HttpOnly axis_refresh cookie is
          // sent to the route handler — do NOT put the token in the body.
          cookie: request.headers.get('cookie') || '',
        },
      });

      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        payload = decodeJwtPayload(data.access_token);

        // Build response and set the new access token cookie
        const response = NextResponse.next();
        response.cookies.set('axis_access', data.access_token, {
          httpOnly: false, // readable by client JS for API calls
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'strict',
          maxAge: 900, // 15 minutes
          path: '/',
        });
        return applyRoleCheck(pathname, payload, request, response);
      }
    } catch {
      // Refresh failed — fall through to login redirect
    }
  }

  // Not authenticated — redirect to login
  if (!payload) {
    // API routes return 401
    if (pathname.startsWith('/api/')) {
      return NextResponse.json(
        { detail: 'Authentication required' },
        { status: 401 }
      );
    }
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return applyRoleCheck(pathname, payload, request, NextResponse.next());
}

function applyRoleCheck(
  pathname: string,
  payload: Record<string, unknown> | null,
  request: NextRequest,
  response: NextResponse
): NextResponse {
  if (!payload) {
    const loginUrl = new URL('/login', request.url);
    return NextResponse.redirect(loginUrl);
  }

  const role = payload.role as string | undefined;

  for (const [prefix, allowedRoles] of Object.entries(ROLE_PATHS)) {
    if (pathname.startsWith(prefix)) {
      if (!role || !allowedRoles.includes(role)) {
        if (pathname.startsWith('/api/')) {
          return NextResponse.json({ detail: 'Forbidden' }, { status: 403 });
        }
        const dashUrl = new URL('/dashboard', request.url);
        return NextResponse.redirect(dashUrl);
      }
    }
  }

  return response;
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
