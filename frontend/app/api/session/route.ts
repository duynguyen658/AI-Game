import { NextResponse } from "next/server";
import { z } from "zod";
import {
  demoAuthEnabled,
  encodeSession,
  SESSION_COOKIE,
  sessionCookieOptions,
} from "@/lib/auth/session";
import { getAuthAdapter } from "@/lib/auth/adapter";
import { interactiveRoles } from "@/lib/auth/types";

const loginSchema = z.object({
  actorId: z.string().trim().min(2).max(100),
  displayName: z.string().trim().min(2).max(100),
  role: z.enum(interactiveRoles),
});

export async function POST(request: Request) {
  if (!demoAuthEnabled()) {
    return NextResponse.json(
      { message: "Demo authentication is disabled" },
      { status: 503 },
    );
  }
  const parsed = loginSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { message: "Enter a valid demo identity and role" },
      { status: 422 },
    );
  }
  const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60 * 8;
  const response = NextResponse.json({ user: parsed.data });
  response.cookies.set(SESSION_COOKIE, encodeSession({
    ...parsed.data,
    mode: "demo",
    expiresAt,
  }), { ...sessionCookieOptions, maxAge: 60 * 60 * 8 });
  return response;
}

export async function DELETE() {
  await getAuthAdapter().logout();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
  return response;
}
