/**
 * GET  /api/admin/lti/platforms  — list all registered LTI platforms
 * POST /api/admin/lti/platforms  — register a new LTI platform
 */
import { NextRequest, NextResponse } from 'next/server';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function getHeaders(request: NextRequest) {
  const token = request.cookies.get('axis_access')?.value;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function GET(request: NextRequest) {
  const res = await fetch(`${API}/api/v1/admin/lti/platforms`, {
    headers: await getHeaders(request),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const res = await fetch(`${API}/api/v1/admin/lti/platforms`, {
    method: 'POST',
    headers: await getHeaders(request),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
