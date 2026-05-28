/**
 * GET    /api/admin/lti/platforms/[id]
 * PUT    /api/admin/lti/platforms/[id]
 * DELETE /api/admin/lti/platforms/[id]
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

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  const res = await fetch(`${API}/api/v1/admin/lti/platforms/${params.id}`, {
    headers: await getHeaders(request),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function PUT(request: NextRequest, { params }: { params: { id: string } }) {
  const body = await request.json();
  const res = await fetch(`${API}/api/v1/admin/lti/platforms/${params.id}`, {
    method: 'PUT',
    headers: await getHeaders(request),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function DELETE(request: NextRequest, { params }: { params: { id: string } }) {
  const res = await fetch(`${API}/api/v1/admin/lti/platforms/${params.id}`, {
    method: 'DELETE',
    headers: await getHeaders(request),
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
