import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

// Proxy for GET /api/v1/skills (list) and POST /api/v1/skills (create)
// Note: [...]path catch-all doesn't match the root /api/skills path — handled here.

export async function GET(req: NextRequest) {
  const token = cookies().get('axis_access')?.value;
  try {
    const data = await apiRequest(`/api/v1/skills${req.nextUrl.search}`, { jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(req: NextRequest) {
  const token = cookies().get('axis_access')?.value;
  try {
    const body = await req.json();
    const data = await apiRequest('/api/v1/skills', {
      method: 'POST', jwtToken: token, body,
    });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
