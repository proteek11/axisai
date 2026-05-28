/**
 * Content URL update proxy — PATCH /api/spaces/[id]/content/[contentId]
 * C-09: Update source_url (and optional title) for an existing content item.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; contentId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  try {
    const data = await apiRequest(
      `/api/v1/spaces/${params.id}/content/${params.contentId}/url`,
      { method: 'PATCH', body, jwtToken: accessToken },
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
