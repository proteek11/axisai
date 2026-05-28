/**
 * Note detail proxy — PUT/DELETE /api/me/notes/[noteId]
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { noteId: string } },
) {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const body = await req.json();
  try {
    const data = await apiRequest(`/api/v1/me/notes/${params.noteId}`, {
      method: 'PUT', body, jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { noteId: string } },
) {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  try {
    await apiRequest(`/api/v1/me/notes/${params.noteId}`, {
      method: 'DELETE', jwtToken: accessToken,
    });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
