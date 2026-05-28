/**
 * GET /api/course-builder/progress/[spaceId]
 * Poll generation progress for all chapters in a space.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  req: NextRequest,
  { params }: { params: { spaceId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const data = await apiRequest(
      `/api/v1/course-builder/progress/${params.spaceId}`,
      { method: 'GET', jwtToken: accessToken },
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
