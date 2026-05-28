import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

/** GET /api/scorm/[contentId]/report/csv — stream CSV download */
export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId') ?? '';

  const authHeader = accessToken ? `Bearer ${accessToken}` : '';

  const backendUrl = `${AXIS_AI_URL}/api/v1/scorm/${params.contentId}/report/csv?space_id=${spaceId}`;

  try {
    const response = await fetch(backendUrl, {
      headers: {
        Authorization: authHeader,
        'X-Requested-With': 'axis-frontend',
      },
    });

    if (!response.ok) {
      return new NextResponse('Report not available', { status: response.status });
    }

    const body = await response.arrayBuffer();
    const filename = response.headers.get('Content-Disposition') ?? 'attachment; filename="scorm_report.csv"';

    return new NextResponse(body, {
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': filename,
      },
    });
  } catch (err) {
    console.error('[scorm/report/csv]', err);
    return new NextResponse('Error generating report', { status: 500 });
  }
}
