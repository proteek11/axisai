/**
 * Minimal next/server stub for Vitest.
 *
 * NextRequest  — extends the Web Fetch API Request class.
 *                Adds .nextUrl, .cookies, and .ip matching the real API.
 * NextResponse — extends Response with static helpers: .json(), .redirect(), .next().
 *                Also exposes a .cookies Map so route tests can inspect Set-Cookie.
 *
 * This stub is aliased to 'next/server' in vitest.config.ts so that:
 *  - API route tests can import NextRequest/NextResponse and construct real instances
 *  - The tests run without needing the full Next.js package to be installed
 */

export class NextRequest extends Request {
  nextUrl: URL;
  ip?: string;

  constructor(input: string | URL | Request, init?: RequestInit) {
    super(input, init);
    this.nextUrl = new URL(
      input instanceof Request ? input.url : input.toString()
    );
  }

  // Next.js cookies() on the request (different from next/headers cookies())
  get cookies() {
    const cookieHeader = this.headers.get('cookie') ?? '';
    const map = new Map<string, { name: string; value: string }>();
    for (const part of cookieHeader.split(';')) {
      const [name, ...rest] = part.trim().split('=');
      if (name) map.set(name.trim(), { name: name.trim(), value: rest.join('=').trim() });
    }
    return {
      get: (name: string) => map.get(name),
      getAll: () => Array.from(map.values()),
      has: (name: string) => map.has(name),
    };
  }
}

// ─── Cookie store on NextResponse ───────────────────────────────────────────

class CookieStore {
  private _cookies: Map<string, { value: string; options: Record<string, unknown> }> = new Map();
  private _rawHeaderParts: string[] = [];

  set(name: string, value: string, options: Record<string, unknown> = {}) {
    this._cookies.set(name, { value, options });

    // Build a Set-Cookie header fragment
    const parts = [`${name}=${value}`];
    if (options.maxAge !== undefined) parts.push(`Max-Age=${options.maxAge}`);
    if (options.path) parts.push(`Path=${options.path}`);
    if (options.httpOnly) parts.push('HttpOnly');
    if (options.secure) parts.push('Secure');
    if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
    this._rawHeaderParts.push(parts.join('; '));
  }

  get(name: string) {
    const c = this._cookies.get(name);
    return c ? { name, value: c.value } : undefined;
  }

  /** Returns all Set-Cookie header values (one per cookie). */
  getAll(): string[] {
    return this._rawHeaderParts;
  }
}

// ─── NextResponse ────────────────────────────────────────────────────────────

export class NextResponse extends Response {
  cookies: CookieStore;

  constructor(body?: BodyInit | null, init?: ResponseInit) {
    super(body, init);
    this.cookies = new CookieStore();
  }

  /**
   * Override headers.getSetCookie() to include cookies set via .cookies.set()
   * so tests can inspect them via res.headers.getSetCookie().
   */
  get headers(): Headers & { getSetCookie(): string[] } {
    const base = super.headers as Headers;
    const cookieStore = this.cookies;
    return new Proxy(base, {
      get(target, prop) {
        if (prop === 'getSetCookie') {
          return () => {
            const fromHeaders: string[] = [];
            target.forEach((value, key) => {
              if (key.toLowerCase() === 'set-cookie') fromHeaders.push(value);
            });
            return [...fromHeaders, ...cookieStore.getAll()];
          };
        }
        const val = (target as any)[prop];
        return typeof val === 'function' ? val.bind(target) : val;
      },
    }) as Headers & { getSetCookie(): string[] };
  }

  /** JSON response helper */
  static json(data: unknown, init?: ResponseInit): NextResponse {
    const res = new NextResponse(JSON.stringify(data), {
      ...init,
      headers: {
        'content-type': 'application/json',
        ...(init?.headers ?? {}),
      },
    });
    return res;
  }

  /** Redirect helper */
  static redirect(url: string | URL, init?: number | ResponseInit): NextResponse {
    const status = typeof init === 'number' ? init : (init?.status ?? 307);
    return new NextResponse(null, {
      status,
      headers: { location: url.toString() },
    });
  }

  /** Pass-through helper (200 OK) */
  static next(_init?: ResponseInit): NextResponse {
    return new NextResponse(null, { status: 200 });
  }
}
