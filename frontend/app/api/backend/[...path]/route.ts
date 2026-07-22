import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { getAuthAdapter } from "@/lib/auth/adapter";
import { getAuthMode, getBackendApiUrl, getBodyLimits } from "@/lib/env/server";
import {
  BodyLimitError,
  isBodyLimitError,
  parseContentLength,
  streamWithByteLimit,
} from "@/lib/bff/streaming";
import { buildUpstreamHeaders, type UpstreamIdentity } from "@/lib/bff/headers";

const allowedResponseHeaders = [
  "content-type",
  "content-length",
  "content-disposition",
  "x-correlation-id",
  "retry-after",
  "etag",
];

function errorResponse(message: string, status: number, correlationId: string, code?: string) {
  return NextResponse.json(
    { message, correlation_id: correlationId, ...(code ? { code } : {}) },
    { status, headers: { "x-correlation-id": correlationId } },
  );
}

function safeCorrelationId(value: string | null) {
  return value && /^[A-Za-z0-9._:-]{1,100}$/.test(value) ? value : randomUUID();
}

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const auth = getAuthAdapter();
  const correlationId = safeCorrelationId(request.headers.get("x-correlation-id"));

  const { path } = await context.params;
  const target = new URL(`/${path.join("/")}`, getBackendApiUrl());
  target.search = request.nextUrl.search;

  let identity: UpstreamIdentity;
  if (getAuthMode() === "demo") {
    const session = await auth.getServerSession();
    if (!session) return errorResponse("Authentication is required", 401, correlationId);
    identity = { mode: "demo", actorId: session.actorId, role: session.role };
  } else {
    const token = await auth.getAccessToken();
    if (token.status === "authentication_required") {
      return errorResponse(
        "Your session has expired. Please sign in again.",
        401,
        correlationId,
        token.errorCode,
      );
    }
    identity = { mode: "oidc", accessToken: token.accessToken };
  }
  const headers = buildUpstreamHeaders(request.headers, correlationId, identity);

  const hasBody = request.method !== "GET" && request.method !== "HEAD" && request.body;
  const isUpload = request.headers.get("content-type")?.toLowerCase().startsWith("multipart/form-data") ?? false;
  const bodyLimit = isUpload ? getBodyLimits().upload : getBodyLimits().json;
  try {
    const declaredLength = parseContentLength(request.headers.get("content-length"));
    if (declaredLength !== null && declaredLength > bodyLimit) throw new BodyLimitError();
  } catch (error) {
    if (isBodyLimitError(error)) {
      return errorResponse("Request body exceeds the configured limit", 413, correlationId);
    }
    throw error;
  }

  const upstreamAbort = new AbortController();
  let limitExceeded = false;
  request.signal.addEventListener("abort", () => upstreamAbort.abort(request.signal.reason), { once: true });
  const body = hasBody
    ? streamWithByteLimit(request.body!, bodyLimit, () => {
        limitExceeded = true;
        upstreamAbort.abort(new BodyLimitError());
      })
    : undefined;
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: upstreamAbort.signal,
    };
    if (body) init.duplex = "half";
    const upstream = await fetch(target, init);
    const responseHeaders = new Headers();
    for (const name of allowedResponseHeaders) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (limitExceeded || isBodyLimitError(error)) {
      return errorResponse("Request body exceeds the configured limit", 413, correlationId);
    }
    if (request.signal.aborted) {
      return errorResponse("Request was cancelled", 499, correlationId);
    }
    return errorResponse("The backend is currently unavailable", 503, correlationId);
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
