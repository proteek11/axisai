/**
 * Chat proxy — POST /api/chat
 *
 * Bridges the learner chat widget to the axis JWT chat pipeline.
 *
 * Request body:  { content_id: string, message: string }
 * Response body: { response: string, suggestions?: string[], sources?: object[] }
 *
 * Session management is handled server-side:
 *   1. POST /api/v1/axis/chat/sessions          → create or retrieve session
 *   2. POST /api/v1/axis/chat/sessions/{id}/message → send message, get AI answer
 *
 * The JWT access token is read from the HttpOnly cookie and forwarded as a
 * Bearer header — it never touches the client.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  }

  let body: { content_id?: string; message?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const { content_id, message } = body;
  if (!message?.trim()) {
    return NextResponse.json({ error: 'message is required' }, { status: 400 });
  }

  try {
    // ── Step 1: Get or create chat session ─────────────────────────────────
    const sessionData = await apiRequest<{ session_id: string }>(
      '/api/v1/axis/chat/sessions',
      {
        method: 'POST',
        body: { content_item_id: content_id ?? null },
        jwtToken: accessToken,
      },
    );

    const sessionId = sessionData.session_id;

    // ── Step 2: Send message to session ────────────────────────────────────
    const msgData = await apiRequest<{
      session_id: string;
      answer: string;
      suggestions: string[];
      sources: object[];
    }>(
      `/api/v1/axis/chat/sessions/${sessionId}/message`,
      {
        method: 'POST',
        body: { session_id: sessionId, message },
        jwtToken: accessToken,
      },
    );

    return NextResponse.json({
      response: msgData.answer,
      suggestions: msgData.suggestions ?? [],
      sources: msgData.sources ?? [],
    });
  } catch (err: any) {
    const status = err.status || 500;
    // Surface rate-limit and budget errors with their messages
    if (status === 429 || status === 402) {
      return NextResponse.json({ error: err.message }, { status });
    }
    return NextResponse.json(
      { error: 'AI chat is temporarily unavailable. Please try again.' },
      { status },
    );
  }
}
