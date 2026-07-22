import { cookies } from "next/headers";
import { getAuthMode } from "@/lib/env/server";
import { shouldUseSecureCookies } from "./cookie-policy";
import { seal, unseal } from "./crypto";
import { isUserRole, type SessionUser } from "./types";

export const SESSION_COOKIE = "cl_session";
export const OIDC_TRANSACTION_COOKIE = "cl_oidc_transaction";

export type AuthenticatedSession = {
  actor: {
    id: string;
    role: SessionUser["role"];
    displayName?: string;
    email?: string;
  };
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  accessTokenExpiresAt: number;
  sessionExpiresAt: number;
  createdAt: number;
  refreshedAt?: number;
  provider: "oidc";
  sessionVersion: number;
};

export type DemoSession = SessionUser & {
  mode: "demo";
  sessionExpiresAt: number;
  createdAt: number;
};

export type PublicSession = SessionUser & { mode: "demo" | "oidc"; sessionExpiresAt: number };

export type OidcTransaction = {
  state: string;
  nonce: string;
  codeVerifier: string;
  expiresAt: number;
};

export function isAuthenticatedSession(value: unknown): value is AuthenticatedSession {
  const parsed = value as Partial<AuthenticatedSession> | null;
  return Boolean(
    parsed &&
    parsed.provider === "oidc" &&
    typeof parsed.actor?.id === "string" &&
    isUserRole(parsed.actor.role) &&
    typeof parsed.accessToken === "string" &&
    parsed.accessToken.length > 0 &&
    typeof parsed.accessTokenExpiresAt === "number" &&
    typeof parsed.sessionExpiresAt === "number" &&
    typeof parsed.createdAt === "number" &&
    Number.isInteger(parsed.sessionVersion) &&
    parsed.sessionVersion! >= 1
  );
}

export function encodeSession(session: DemoSession) {
  return seal(session, "SESSION_SECRET");
}

export function decodeSession(value: string | undefined, now = Math.floor(Date.now() / 1000)): DemoSession | null {
  const parsed = unseal<Partial<DemoSession> & { expiresAt?: number }>(value, "SESSION_SECRET");
  if (
    !parsed ||
    parsed.mode !== "demo" ||
    typeof parsed.actorId !== "string" ||
    typeof parsed.displayName !== "string" ||
    !isUserRole(parsed.role) ||
    typeof parsed.sessionExpiresAt !== "number" ||
    parsed.sessionExpiresAt <= now
  ) return null;
  return parsed as DemoSession;
}

export function encodeOidcTransaction(transaction: OidcTransaction) {
  return seal(transaction, "SESSION_SECRET");
}

export function decodeOidcTransaction(value: string | undefined): OidcTransaction | null {
  const parsed = unseal<Partial<OidcTransaction>>(value, "SESSION_SECRET");
  if (
    !parsed ||
    typeof parsed.state !== "string" ||
    typeof parsed.nonce !== "string" ||
    typeof parsed.codeVerifier !== "string" ||
    typeof parsed.expiresAt !== "number" ||
    parsed.expiresAt <= Math.floor(Date.now() / 1000)
  ) return null;
  return parsed as OidcTransaction;
}

export function toPublicSession(session: AuthenticatedSession): PublicSession {
  return {
    actorId: session.actor.id,
    role: session.actor.role,
    displayName: session.actor.displayName ?? session.actor.email ?? session.actor.id,
    mode: "oidc",
    sessionExpiresAt: session.sessionExpiresAt,
  };
}

export async function getSession(): Promise<PublicSession | null> {
  const value = (await cookies()).get(SESSION_COOKIE)?.value;
  if (getAuthMode() === "demo") return decodeSession(value);
  const { getOidcSessionStore } = await import("./session-store");
  const stored = await getOidcSessionStore().readSession(value);
  return stored.outcome === "FOUND" ? toPublicSession(stored.session) : null;
}

export function demoAuthEnabled() {
  return getAuthMode() === "demo" && process.env.DEMO_AUTH_ENABLED === "true";
}

export const sessionCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: shouldUseSecureCookies(
    process.env.NODE_ENV,
    process.env.AUTH_MODE === "demo" ? "demo" : "oidc",
    process.env.ALLOW_PRODUCTION_DEMO === "true",
  ),
  path: "/",
};
