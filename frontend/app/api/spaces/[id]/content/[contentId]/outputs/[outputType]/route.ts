/**
 * Output quality rating proxy
 * PATCH /api/spaces/[id]/content/[contentId]/outputs/[outputType]
 * C-12: Rate AI output quality (1 = good, -1 = poor)
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; contentId: string; outputType: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  try {
    const data = await apiRequest(
      `/api/v1/spaces/${params.id}/content/${params.contentId}/outputs/${params.outputType}/quality`,
      { method: 'PATCH', body, jwtToken: accessToken },
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
