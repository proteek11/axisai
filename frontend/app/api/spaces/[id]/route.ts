import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest(`/api/v1/spaces/${params.id}`, {
      method: 'GET', jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();
  try {
    const data = await apiRequest(`/api/v1/spaces/${params.id}`, {
      method: 'PUT', body: body, jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const deleteContent = searchParams.get('delete_exclusive_content') === 'true';
  const qs = deleteContent ? '?delete_exclusive_content=true' : '';
  try {
    await apiRequest(`/api/v1/spaces/${params.id}${qs}`, {
      method: 'DELETE', jwtToken: accessToken,
    });
    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
