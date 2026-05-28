import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

async function handler(req: NextRequest, { params }: { params: { id: string } }) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const url = `${BACKEND}/api/v1/spaces/${params.id}/assessments`;
  const opts: RequestInit = { method: req.method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, cache: 'no-store' };
  if (req.method === 'POST') opts.body = JSON.stringify(await req.json().catch(() => ({})));
  const res = await fetch(url, opts);
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}
export { handler as GET, handler as POST };
