import { NextRequest, NextResponse } from 'next/server';
import { apiUpload } from '@/lib/api/client';
import { cookies } from 'next/headers';

// App Router route segment config (replaces the deprecated Pages Router `export const config`).
// Body parsing is handled natively by Next.js App Router via req.formData().
// Actual upload size limit is enforced by Nginx (client_max_body_size 500m).
export const dynamic = 'force-dynamic'; // never cache this route
export const maxDuration = 300;         // 5-minute timeout for large video uploads

/**
 * POST /api/spaces/[id]/upload
 *
 * Proxies a multipart file upload to the FastAPI
 * POST /api/v1/spaces/{space_id}/upload endpoint (JWT-authenticated,
 * no Moodle IDs required). Used by the Next.js UploadModal component.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const formData = await req.formData();
    const data = await apiUpload(
      `/api/v1/spaces/${params.id}/upload`,
      formData,
      accessToken,
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message },
      { status: err.status || 500 },
    );
  }
}
