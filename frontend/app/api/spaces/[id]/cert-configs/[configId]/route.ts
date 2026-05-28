import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function DELETE(_req: NextRequest, { params }: { params: { id: string; configId: string } }) {
  const token = cookies().get('axis_access')?.value;
  try {
    await apiRequest(`/api/v1/spaces/${params.id}/cert-configs/${params.configId}`, { method: 'DELETE', jwtToken: token });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
