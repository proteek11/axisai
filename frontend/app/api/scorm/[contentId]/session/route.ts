import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

/** GET /api/scorm/[contentId]/session — get or initialise learner session (for resume) */
export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId') ?? '';

  try {
    const data = await apiRequest(
      `/api/v1/scorm/${params.contentId}/session?space_id=${spaceId}`,
      { method: 'GET', jwtToken: accessToken }
    );
    return NextResponse.json(data);
  } catch (err: unknown) {
    const status = (err as { status?: number }).status ?? 500;
    const detail = (err as { detail?: string }).detail ?? 'Failed to fetch SCORM session';
    return NextResponse.json({ error: detail }, { status });
  }
}
