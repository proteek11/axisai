import { NextRequest, NextResponse } from 'next/server';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get('axis_refresh')?.value;

  if (refreshToken) {
    // Invalidate in DB (fire and forget — don't block logout on failure)
    fetch(`${AXIS_AI_URL}/api/v1/auth/logout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${AXIS_AI_KEY}`,
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => {});
  }

  const res = NextResponse.json({ success: true });
  res.cookies.delete('axis_refresh');
  res.cookies.delete('axis_access');
  return res;
}
