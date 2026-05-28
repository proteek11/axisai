import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

/**
 * DELETE /api/admin/users/{id}/purge
 *
 * Hard-deletes a user and ALL their data (cascade).
 * Proxies to: DELETE /api/v1/auth/users/{id}/purge  (JWT auth, admin only)
 */
export async function DELETE(_: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const data = await apiRequest(`/api/v1/auth/users/${params.id}/purge`, {
      method: 'DELETE',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to delete user' },
      { status: err.status || 500 }
    );
  }
}
