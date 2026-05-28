/**
 * Transcript proxy — GET /api/content/[contentId]/transcript
 *
 * Returns the timed transcript (segments array) for video content items.
 * Only available for youtube / vimeo / video_upload content that had captions.
 * Returns 404 (empty body) if no transcript exists — UI hides the tab silently.
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
    // Note: content.py uses API-key auth, not JWT — apiRequest uses AXIS_AI_KEY by default
    const data = await apiRequest(
      `/api/v1/content/${params.contentId}/transcript?language=${lang}`,
    );
    return NextResponse.json(data);
  } catch (err: any) {
    // 404 = no transcript (PDF or video without captions) — return empty gracefully
    if (err.status === 404) return NextResponse.json(null, { status: 404 });
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
