import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    // DELETE /api/v1/kb/items/{id} — uses tenant API key (no jwtToken)
    await apiRequest(`/api/v1/kb/items/${params.id}`, {
      method: 'DELETE',
    });
    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to delete KB item' },
      { status: err.status || 500 }
    );
  }
}
