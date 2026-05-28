/**
 * Typed API client — server-side only.
 * All calls to axisai.edzlms.com go through here.
 * The FastAPI API key (AXIS_AI_KEY) is NEVER exposed to the browser.
 * Called only from Next.js API route handlers.
 */

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

/** Default request timeout in milliseconds (30 s). */
const FETCH_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    message?: string,
  ) {
    super(message || detail);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** If provided, used as Bearer token (for JWT-authenticated endpoints) */
  jwtToken?: string;
  /** Override the default 30 s timeout (ms). Pass 0 to disable. */
  timeoutMs?: number;
}

/**
 * Make a server-side request to the FastAPI backend.
 * Uses the tenant API key by default.
 * Pass jwtToken for user-auth endpoints (/auth/*, /spaces/*, /axis/*).
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', body, headers = {}, jwtToken, timeoutMs = FETCH_TIMEOUT_MS } = options;

  const authHeader = jwtToken
    ? `Bearer ${jwtToken}`
    : `Bearer ${AXIS_AI_KEY}`;

  const reqHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: authHeader,
    'X-Requested-With': 'axis-frontend',
    ...headers,
  };

  // Wrap fetch in an AbortController so hanging FastAPI calls don't block
  // the Next.js server indefinitely.
  const controller = new AbortController();
  const timer =
    timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;

  let response: Response;
  try {
    response = await fetch(`${AXIS_AI_URL}${path}`, {
      method,
      headers: reqHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      throw new ApiError(504, 'Request timed out — FastAPI did not respond in time');
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const json = await response.json();
      // Prefer string fields over objects (json.detail is often {} which is truthy but useless)
      const strField = [json.message, json.error, json.detail].find(
        (v) => v && typeof v === 'string',
      );
      const raw = strField ?? json.detail ?? json.message ?? json.error ?? detail;
      // FastAPI 422 detail is an array of validation errors — serialize it
      detail = typeof raw === 'string' ? raw : JSON.stringify(raw);
    } catch {
      // ignore parse error
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/**
 * Upload a file to FastAPI (multipart/form-data).
 * Used for content ingest (PDF, video) and KB file uploads.
 */
export async function apiUpload<T>(
  path: string,
  formData: FormData,
  jwtToken?: string,
  timeoutMs = FETCH_TIMEOUT_MS,
): Promise<T> {
  const authHeader = jwtToken
    ? `Bearer ${jwtToken}`
    : `Bearer ${AXIS_AI_KEY}`;

  const controller = new AbortController();
  const timer =
    timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;

  let response: Response;
  try {
    response = await fetch(`${AXIS_AI_URL}${path}`, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'X-Requested-With': 'axis-frontend',
        // Do NOT set Content-Type — fetch sets multipart boundary automatically
      },
      body: formData,
      cache: 'no-store',
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      throw new ApiError(504, 'Upload timed out — FastAPI did not respond in time');
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const json = await response.json();
      detail = json.detail || detail;
    } catch {}
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}
