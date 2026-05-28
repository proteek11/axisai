/**
 * GET /api/branding
 * Public endpoint — no auth required.
 * Returns the tenant's saved branding tokens so the login page can apply
 * custom colours before the user authenticates.
 */
import { NextResponse } from 'next/server';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const upstream = await fetch(
      `${AXIS_AI_URL}/api/v1/auth/settings/branding/public`,
      { next: { revalidate: 60 } } // cache for 60s on the server — branding rarely changes
    );
    if (!upstream.ok) {
      return NextResponse.json({}, { status: 200 }); // fail silently — use CSS defaults
    }
    const data = await upstream.json();
    return NextResponse.json(data, {
      status: 200,
      headers: {
        'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300',
      },
    });
  } catch {
    return NextResponse.json({}, { status: 200 }); // fail silently
  }
}
