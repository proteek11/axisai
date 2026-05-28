import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const body = await req.json();
    const data = await apiRequest(`/api/v1/teams/${params.id}/members`, {
      method: 'POST',
      jwtToken: accessToken,
      body,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to add members' },
      { status: err.status || 500 }
    );
  }
}

export async function DELETE(req: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const body = await req.json();
    const data = await apiRequest(`/api/v1/teams/${params.id}/members`, {
      method: 'DELETE',
      jwtToken: accessToken,
      body,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to remove members' },
      { status: err.status || 500 }
    );
  }
}
