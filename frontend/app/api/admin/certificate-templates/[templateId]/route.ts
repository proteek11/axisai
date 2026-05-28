import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function PUT(req: NextRequest, { params }: { params: { templateId: string } }) {
  const token = cookies().get('axis_access')?.value;
  const body = await req.json();
  try {
    const data = await apiRequest(`/api/v1/admin/certificate-templates/${params.templateId}`, { method: 'PUT', body, jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(_req: NextRequest, { params }: { params: { templateId: string } }) {
  const token = cookies().get('axis_access')?.value;
  try {
    await apiRequest(`/api/v1/admin/certificate-templates/${params.templateId}`, { method: 'DELETE', jwtToken: token });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
