import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);

  const params = new URLSearchParams();
  for (const key of ['limit', 'offset', 'task_type', 'status', 'date_from', 'date_to']) {
    const val = searchParams.get(key);
    if (val) params.set(key, val);
  }
  if (!params.has('limit')) params.set('limit', '50');
  if (!params.has('offset')) params.set('offset', '0');

  try {
    const data = await apiRequest(
      `/api/v1/admin/audit?${params.toString()}`,
      { method: 'GET', jwtToken: accessToken }
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch audit log' },
      { status: err.status || 500 }
    );
  }
}
