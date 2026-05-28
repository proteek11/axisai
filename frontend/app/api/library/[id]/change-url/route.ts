import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();

  try {
    const data = await apiRequest(`/api/v1/library/${params.id}/change-url`, {
      method: 'POST',
      jwtToken: accessToken,
      body: JSON.stringify(body),
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to change URL' },
      { status: err.status || 500 }
    );
  }
}
