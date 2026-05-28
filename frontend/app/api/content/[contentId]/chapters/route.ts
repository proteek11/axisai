/**
 * Chapters proxy — GET /api/content/[contentId]/chapters
 *
 * Returns AI-generated video chapters with timestamps and summaries.
 * Only available for video content items that have been processed with
 * the "chapters" output type enabled.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  }

  const lang = req.nextUrl.searchParams.get('language') ?? 'en';

  try {
    const data = await apiRequest(
      `/api/v1/content/${params.contentId}/chapters?language=${lang}`,
    );
    return NextResponse.json(data);
  } catch (err: any) {
    if (err.status === 404) return NextResponse.json(null, { status: 404 });
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
