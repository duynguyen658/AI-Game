import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/auth/session";

const allowedResponseHeaders = [
  "content-type",
  "content-length",
  "x-correlation-id",
  "retry-after",
];

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json(
      { message: "Authentication is required" },
      { status: 401 },
    );
  }

  const { path } = await context.params;
  const baseUrl = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";
  const target = new URL(`/${path.join("/")}`, baseUrl);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of ["content-type", "x-idempotency-key", "x-correlation-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-actor-id", session.actorId);
  headers.set("x-actor-role", session.role);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    });
    const responseHeaders = new Headers();
    for (const name of allowedResponseHeaders) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { message: "The backend is currently unavailable" },
      { status: 503 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
