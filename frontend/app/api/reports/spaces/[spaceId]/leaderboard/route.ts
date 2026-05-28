import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  req: NextRequest,
  { params }: { params: { spaceId: string } },
) {
  const token = cookies().get('axis_access')?.value;
  const qs = req.nextUrl.search;
  try {
    const data = await apiRequest(
      `/api/v1/reports/spaces/${params.spaceId}/leaderboard${qs}`,
      { jwtToken: token },
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
