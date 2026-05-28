import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(
  req: NextRequest,
  { params }: { params: { contentId: string } }
) {
  const cookieStore = cookies();
  const token = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId');
  if (!spaceId) return NextResponse.json({ error: 'spaceId required' }, { status: 400 });

  const body = await req.json();
  try {
    // Translation runs inline via LLM — can take 60-90s. Use 120s timeout.
    const data = await apiRequest(
      `/api/v1/spaces/${spaceId}/items/${params.contentId}/translate`,
      { method: 'POST', jwtToken: token, body: body, timeoutMs: 120_000 }
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
