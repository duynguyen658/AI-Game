import { NextResponse } from "next/server";
import { z } from "zod";
import {
  demoAuthEnabled,
  encodeSession,
  SESSION_COOKIE,
} from "@/lib/auth/session";
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
  const response = NextResponse.json({ user: parsed.data });
  response.cookies.set(SESSION_COOKIE, encodeSession(parsed.data), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return response;
}
