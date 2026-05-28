import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(_: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const data = await apiRequest(`/api/v1/teams/${params.id}`, {
      method: 'GET',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch team' },
      { status: err.status || 500 }
    );
  }
}

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const body = await req.json();
    const data = await apiRequest(`/api/v1/teams/${params.id}`, {
      method: 'PUT',
      jwtToken: accessToken,
      body,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to update team' },
      { status: err.status || 500 }
    );
  }
}

export async function DELETE(_: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    await apiRequest(`/api/v1/teams/${params.id}`, {
      method: 'DELETE',
      jwtToken: accessToken,
    });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to delete team' },
      { status: err.status || 500 }
    );
  }
}
