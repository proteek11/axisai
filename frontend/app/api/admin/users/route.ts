import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const data = await apiRequest('/api/v1/auth/users', {
      method: 'GET',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch users' },
      { status: err.status || 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const body = await req.json();
    const data = await apiRequest('/api/v1/auth/users', {
      method: 'POST',
      jwtToken: accessToken,
      body,
    });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to create user' },
      { status: err.status || 500 }
    );
  }
}
