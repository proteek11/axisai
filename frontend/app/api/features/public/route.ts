import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

/** GET /api/features/public — returns IC, chat flags for nav gating. */
export async function GET(_req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest('/api/v1/features/public', { jwtToken: accessToken });
    return NextResponse.json(data);
  } catch {
    // Never block the UI — return safe defaults
    return NextResponse.json({ interactive_content: true, chat: true, kb_chat: true });
  }
}
