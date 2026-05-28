import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || process.env.NEXT_PUBLIC_API_URL || 'https://axisai.edzlms.com';

export async function DELETE(_: NextRequest, { params }: { params: { id: string; spaceId: string } }) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/spaces/${params.spaceId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 204) return new NextResponse(null, { status: 204 });
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}
