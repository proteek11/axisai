import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

function authHeader(accessToken: string | undefined): string {
  return accessToken ? `Bearer ${accessToken}` : `Bearer ${AXIS_AI_KEY}`;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const res = await fetch(
      `${AXIS_AI_URL}/api/v1/library/${params.id}/pdf-interactions`,
      { headers: { Authorization: authHeader(accessToken) }, cache: 'no-store' }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const body = await req.json();
    const res = await fetch(
      `${AXIS_AI_URL}/api/v1/library/${params.id}/pdf-interactions`,
      {
        method: 'PUT',
        headers: { Authorization: authHeader(accessToken), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
