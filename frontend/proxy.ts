import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { canAccessPath } from "@/lib/auth/permissions";
import { decodeSession, SESSION_COOKIE, toPublicSession } from "@/lib/auth/session";
import { getAuthMode } from "@/lib/env/server";
import { getOidcSessionStore } from "@/lib/auth/session-store";

export async function proxy(request: NextRequest) {
  const cookieValue = request.cookies.get(SESSION_COOKIE)?.value;
  const session = getAuthMode() === "demo"
    ? decodeSession(cookieValue)
    : await getOidcSessionStore().readSession(cookieValue).then((result) =>
      result.outcome === "FOUND" ? toPublicSession(result.session) : null,
    );
  if (!session) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (!canAccessPath(session.role, request.nextUrl.pathname)) {
    return NextResponse.redirect(new URL("/forbidden", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/operations/:path*",
    "/analytics/business-impact/:path*",
    "/prompt-experiments/:path*",
    "/provider-comparisons/:path*",
    "/integrations/n8n/:path*",
    "/prompts/:path*",
    "/approvals/:path*",
  ],
};
