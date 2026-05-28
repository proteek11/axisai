import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

export async function POST(_: NextRequest, { params }: { params: { id: string; assessmentId: string } }) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const res = await fetch(`${BACKEND}/api/v1/spaces/${params.id}/assessments/${params.assessmentId}/publish`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` },
  });
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}
