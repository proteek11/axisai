import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

type Ctx = { params: { path: string[] } };

function buildPath(path: string[], req: NextRequest) {
  return `/api/v1/org-setup/${path.join('/')}${req.nextUrl.search}`;
}

export async function GET(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  try {
    const data = await apiRequest(buildPath(params.path, req), { jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  try {
    const body = await req.json();
    const data = await apiRequest(buildPath(params.path, req), {
      method: 'POST', jwtToken: token, body,
    });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function PUT(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  try {
    const body = await req.json();
    const data = await apiRequest(buildPath(params.path, req), {
      method: 'PUT', jwtToken: token, body,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function DELETE(req: NextRequest, { params }: Ctx) {
  const token = cookies().get('axis_access')?.value;
  try {
    const data = await apiRequest(buildPath(params.path, req), {
      method: 'DELETE', jwtToken: token,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}
