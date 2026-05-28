import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  _req: NextRequest,
  { params }: { params: { jobId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest(`/api/v1/jobs/${params.jobId}`, {
      method: 'GET', jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
