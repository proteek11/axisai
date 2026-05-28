/**
 * GET /api/content/[contentId]/interactions/my-responses
 * Learner's own previous attempts — restores answered state on re-open.
 */
import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

type Ctx = { params: { contentId: string } };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  const res = await fetch(
    `${BACKEND}/api/v1/content/${params.contentId}/interactions/my-responses`,
    { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' }
  );
  const data = await res.json().catch(() => []);
  return NextResponse.json(data, { status: res.status });
}
