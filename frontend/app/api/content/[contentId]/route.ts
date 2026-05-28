import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId');

  try {
    if (spaceId) {
      // Learner path — get content info from space detail (JWT auth)
      const space = await apiRequest(`/api/v1/spaces/${spaceId}`, {
        method: 'GET', jwtToken: accessToken,
      }) as { items?: Array<{ content_item_id: string; title_override?: string | null; content_title?: string | null; content_type?: string | null; content_status?: string | null; source_url?: string | null; experience_mode?: string | null }> };
      const item = (space.items ?? []).find(
        (i) => i.content_item_id === params.contentId
      );
      if (!item) {
        return NextResponse.json({ error: 'Item not found in space' }, { status: 404 });
      }
      return NextResponse.json({
        id: item.content_item_id,
        title: item.title_override ?? item.content_title ?? 'Untitled',
        content_type: item.content_type ?? 'text',
        status: item.content_status,
        source_url: item.source_url ?? null,
        experience_mode: item.experience_mode ?? 'standard',
      });
    }

    // Creator / admin path — legacy content endpoint
    const data = await apiRequest(`/api/v1/content/${params.contentId}`, {
      method: 'GET', jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    await apiRequest(`/api/v1/crud/${params.contentId}`, {
      method: 'DELETE', jwtToken: accessToken,
    });
    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
