import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

export async function GET(_: NextRequest) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ max_upload_size_mb: 100, max_upload_size_bytes: 104857600 });
  const res = await fetch(`${BACKEND}/api/v1/admin/upload-limit`, {
    headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
  });
  if (!res.ok) return NextResponse.json({ max_upload_size_mb: 100, max_upload_size_bytes: 104857600 });
  return NextResponse.json(await res.json());
}
