import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const query = searchParams.get('q') || '';
  const limit = searchParams.get('limit') || '50';

  try {
    // GET /api/v1/kb/items returns a plain array — wrap it for the UI
    const items = await apiRequest<unknown[]>(
      `/api/v1/kb/items?include_inactive=false`,
      { method: 'GET' }
    );
    return NextResponse.json({ items: items ?? [], total: items?.length ?? 0 });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch KB items' },
      { status: err.status || 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { source_type, title, content } = body;

  try {
    let data: unknown;
    if (source_type === 'url') {
      // URL ingestion: POST /api/v1/kb/ingest
      data = await apiRequest('/api/v1/kb/ingest', {
        method: 'POST',
        body: { source_url: content, title, doc_type: 'support' },
      });
    } else {
      // Text ingestion: POST /api/v1/kb/ingest/text
      data = await apiRequest('/api/v1/kb/ingest/text', {
        method: 'POST',
        body: { text: content, title, doc_type: 'support' },
      });
    }
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to create KB item' },
      { status: err.status || 500 }
    );
  }
}
