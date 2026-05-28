/**
 * POST /api/content/[contentId]/interactions/respond
 * Learner submits an answer — returns is_correct, correct_answer, explanation.
 */
import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

type Ctx = { params: { contentId: string } };

export async function POST(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  const body = await req.json();
  const res = await fetch(
    `${BACKEND}/api/v1/content/${params.contentId}/interactions/respond`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    }
  );
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
