import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string; annId: string } }
) {
  const cookieStore = await cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const res = await fetch(
    `${BACKEND}/api/v1/library/${params.id}/pdf-annotations/${params.annId}`,
    { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }
  );

  return new NextResponse(null, { status: res.status });
}
