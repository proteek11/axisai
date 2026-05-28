import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

async function handler(
  req: NextRequest,
  { params }: { params: { id: string; contentId: string } },
) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const url = `${BACKEND}/api/v1/spaces/${params.id}/content/${params.contentId}/gen-settings`;
  const opts: RequestInit = {
    method: req.method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };
  if (req.method === 'PATCH') {
    const body = await req.json().catch(() => ({}));
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export { handler as GET, handler as PATCH };
