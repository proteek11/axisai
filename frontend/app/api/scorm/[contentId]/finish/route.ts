import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

/** POST /api/scorm/[contentId]/finish — mark session terminated */
export async function POST(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId') ?? '';

  try {
    const body = await req.json().catch(() => ({}));
    const data = await apiRequest(
      `/api/v1/scorm/${params.contentId}/finish?space_id=${spaceId}`,
      { method: 'POST', body, jwtToken: accessToken }
    );
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { status?: number }).status ?? 500;
    const detail = (err as { detail?: string }).detail ?? 'Finish failed';
    return NextResponse.json({ error: detail }, { status });
  }
}
