import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const backendUrl = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';
  const apiKey = process.env.AXIS_AI_KEY || '';

  try {
    const formData = await req.formData();
    // Backend expects: file (UploadFile), title (Form) — uses tenant API key auth
    const response = await fetch(`${backendUrl}/api/v1/kb/ingest/file`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
      return NextResponse.json({ error: err.detail || 'Upload failed' }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message || 'Upload failed' }, { status: 500 });
  }
}
