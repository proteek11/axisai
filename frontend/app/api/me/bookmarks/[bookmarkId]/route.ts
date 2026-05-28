/**
 * Bookmark delete proxy — DELETE /api/me/bookmarks/[bookmarkId]
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { bookmarkId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  try {
    await apiRequest(`/api/v1/me/bookmarks/${params.bookmarkId}`, {
      method: 'DELETE', jwtToken: accessToken,
    });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
