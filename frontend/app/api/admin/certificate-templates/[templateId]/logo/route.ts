import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

// Use the same env var as all other backend calls
const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function POST(
  req: NextRequest,
  { params }: { params: { templateId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  // Forward raw FormData — same pattern as /api/spaces/[id]/cover-image
  const formData = await req.formData();

  try {
    const res = await fetch(
      `${AXIS_AI_URL}/api/v1/admin/certificate-templates/${params.templateId}/logo`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData,
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
