/**
 * GET /api/interactive/library
 * Returns all content items that have interactions, scoped to the tenant.
 */
import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function GET() {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/interactive/library`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await upstream.json().catch(() => ({ items: [] }));
  return NextResponse.json(data, { status: upstream.status });
}
