/**
 * Chat history proxy — GET /api/chat/history?content_id=X
 *
 * Fetches the full message history for the learner's chat session on a
 * given content item. Steps:
 *   1. POST /api/v1/axis/chat/sessions     → get or create the session
 *   2. GET  /api/v1/axis/chat/sessions/{id}/history → retrieve messages
 *
 * Used by ChatPanel on mount to restore previous conversation context.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

interface AxisHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

interface AxisSessionResponse {
  session_id: string;
  content_item_id: string | null;
  created_at: string;
}

interface AxisHistoryResponse {
  session_id: string;
  messages: AxisHistoryMessage[];
}

export async function GET(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  }

  const contentId = req.nextUrl.searchParams.get('content_id');

  try {
    // Step 1: get or create the session for this content item
    const session = await apiRequest<AxisSessionResponse>(
      '/api/v1/axis/chat/sessions',
      {
        method: 'POST',
        body: { content_item_id: contentId ?? null },
        jwtToken: accessToken,
      },
    );

    // Step 2: fetch message history
    const history = await apiRequest<AxisHistoryResponse>(
      `/api/v1/axis/chat/sessions/${session.session_id}/history`,
      {
        method: 'GET',
        jwtToken: accessToken,
      },
    );

    return NextResponse.json({
      session_id: session.session_id,
      messages: history.messages,
    });
  } catch (err: any) {
    // Non-fatal — chat panel can start fresh if history fetch fails
    return NextResponse.json({ session_id: null, messages: [] });
  }
}
