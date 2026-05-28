import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND =
  process.env.AXIS_AI_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'https://axisai.edzlms.com';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));

  try {
    // POST to /api/v1/library/{id}/regenerate — JWT-auth endpoint in library.py
    const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/regenerate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        output_types: body.output_types || body.tasks || ['summary'],
        language: body.language || 'en',
      }),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
