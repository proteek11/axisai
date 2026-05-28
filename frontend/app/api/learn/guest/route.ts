import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';

// Public endpoint — no auth required (share token in query string)
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const token = searchParams.get('token');

  if (!token) {
    return NextResponse.json({ error: 'Share token required' }, { status: 400 });
  }

  try {
    const data = await apiRequest(`/api/v1/spaces/guest/${token}`, {
      method: 'GET',
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 403 });
  }
}
