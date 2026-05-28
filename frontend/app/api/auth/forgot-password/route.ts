import { NextRequest, NextResponse } from 'next/server';
const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
export async function POST(req: NextRequest) {
  const body = await req.json();
  const r = await fetch(`${AXIS_AI_URL}/api/v1/auth/forgot-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return NextResponse.json(data, { status: r.status });
}
