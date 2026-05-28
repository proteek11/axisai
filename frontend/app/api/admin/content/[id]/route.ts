import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    await apiRequest(`/api/v1/admin/content/${params.id}`, {
      method: 'DELETE',
      jwtToken: accessToken,
    });
    return new NextResponse(null, { status: 204 });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to delete content item' },
      { status: err.status || 500 }
    );
  }
}
