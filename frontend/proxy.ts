import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { canAccessPath } from "@/lib/auth/permissions";
import { decodeSession, SESSION_COOKIE } from "@/lib/auth/session";

export function proxy(request: NextRequest) {
  const session = decodeSession(request.cookies.get(SESSION_COOKIE)?.value);
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
