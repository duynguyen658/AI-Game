import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { isUserRole, type SessionUser } from "./types";

export const SESSION_COOKIE = "cl_demo_session";

function secret() {
  const configured = process.env.DEMO_SESSION_SECRET;
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    throw new Error("DEMO_SESSION_SECRET is required in production");
  }
  return "local-development-session-secret-not-for-production";
}

function sign(payload: string) {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

export function encodeSession(user: SessionUser) {
  const payload = Buffer.from(JSON.stringify(user)).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

export function decodeSession(value: string | undefined): SessionUser | null {
  if (!value) return null;
  const [payload, signature] = value.split(".");
  if (!payload || !signature) return null;
  const expected = Buffer.from(sign(payload));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) {
    return null;
  }
  try {
    const parsed = JSON.parse(
      Buffer.from(payload, "base64url").toString("utf8"),
    ) as Partial<SessionUser>;
    if (
      typeof parsed.actorId !== "string" ||
      typeof parsed.displayName !== "string" ||
      !isUserRole(parsed.role)
    ) {
      return null;
    }
    return parsed as SessionUser;
  } catch {
    return null;
  }
}

export async function getSession() {
  return decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
}

export function demoAuthEnabled() {
  return process.env.DEMO_AUTH_ENABLED !== "false";
}
