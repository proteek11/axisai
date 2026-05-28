/**
 * GET  /api/content/[contentId]/interactions  → fetch interactions list
 * PUT  /api/content/[contentId]/interactions  → save/replace interactions (creator/admin)
 */
import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

type Ctx = { params: { contentId: string } };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  const res = await fetch(`${BACKEND}/api/v1/content/${params.contentId}/interactions`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export async function PUT(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  const body = await req.json();
  const res = await fetch(`${BACKEND}/api/v1/content/${params.contentId}/interactions`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
