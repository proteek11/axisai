import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const token = cookies().get('axis_access')?.value;
  try {
    const data = await apiRequest(`/api/v1/spaces/${params.id}/cert-configs`, { method: 'GET', jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const token = cookies().get('axis_access')?.value;
  const body = await req.json();
  try {
    const data = await apiRequest(`/api/v1/spaces/${params.id}/cert-configs`, { method: 'POST', body, jwtToken: token });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
