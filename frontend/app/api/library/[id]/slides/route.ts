import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = await cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/slides`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    return NextResponse.json(await res.json(), { status: res.status });
  }

  const data = await res.json();

  // Rewrite image_url / thumbnail_url to go through the Next.js authenticated proxy
  // Backend returns: /api/v1/library/{id}/slides/{n}  and  /api/v1/library/{id}/slides/{n}/thumb
  // We rewrite to:   /api/library/{id}/slides/{n}     and  /api/library/{id}/slides/{n}?thumb=1
  if (Array.isArray(data.slides)) {
    data.slides = data.slides.map((slide: Record<string, unknown>) => ({
      ...slide,
      image_url: `/api/library/${params.id}/slides/${slide.index}`,
      thumbnail_url: `/api/library/${params.id}/slides/${slide.index}?thumb=1`,
    }));
  }

  return NextResponse.json(data, { status: 200 });
}
