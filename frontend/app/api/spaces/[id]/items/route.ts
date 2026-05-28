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
    const data = await apiRequest(`/api/v1/spaces/${params.id}/items`, {
      method: 'POST', body: body, jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

/**
 * GET /api/spaces/[id]/items
 * The backend has no standalone items list endpoint — items are embedded in the
 * full SpaceResponse. Proxy to GET /spaces/{id} and return just the items array.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest(`/api/v1/spaces/${params.id}`, {
      method: 'GET', jwtToken: accessToken,
    });
    // Return the items array from the full SpaceResponse
    return NextResponse.json((data as { items?: unknown[] }).items ?? []);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
