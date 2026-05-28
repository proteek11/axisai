import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  try {
    const raw: any[] = await apiRequest(`/api/v1/spaces/${params.id}/access`, {
      method: 'GET', jwtToken: accessToken,
    });
    // Backend returns a flat list; transform into { users, teams } for the ShareModal
    const users = (raw ?? [])
      .filter((r: any) => r.user_id)
      .map((r: any) => ({ user_id: r.user_id, email: r.user_email, full_name: r.user_name }));
    const teams = (raw ?? [])
      .filter((r: any) => r.team_id)
      .map((r: any) => ({ team_id: r.team_id, name: r.team_name }));
    return NextResponse.json({ users, teams });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();
  // body: { type: 'user'|'dept', id: string }
  try {
    let data;
    if (body.type === 'dept') {
      data = await apiRequest(`/api/v1/spaces/${params.id}/access/depts`, {
        method: 'POST', body: { team_id: body.id }, jwtToken: accessToken,
      });
    } else {
      data = await apiRequest(`/api/v1/spaces/${params.id}/access/users`, {
        method: 'POST', body: { user_id: body.id }, jwtToken: accessToken,
      });
    }
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const type = searchParams.get('type');
  const targetId = searchParams.get('targetId');
  try {
    if (type === 'dept') {
      await apiRequest(`/api/v1/spaces/${params.id}/access/depts/${targetId}`, {
        method: 'DELETE', jwtToken: accessToken,
      });
    } else {
      await apiRequest(`/api/v1/spaces/${params.id}/access/users/${targetId}`, {
        method: 'DELETE', jwtToken: accessToken,
      });
    }
    return NextResponse.json({ success: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
