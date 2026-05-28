import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const period = searchParams.get('period') || '7d';

  try {
    const data = await apiRequest(`/api/v1/admin/usage?period=${period}`, {
      method: 'GET',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch usage data' },
      { status: err.status || 500 }
    );
  }
}
