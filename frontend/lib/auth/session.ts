import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { isUserRole, type SessionUser } from "./types";
import { getAuthMode, requireServerEnv, type AuthMode } from "@/lib/env/server";
import { shouldUseSecureCookies } from "./cookie-policy";

export const SESSION_COOKIE = "cl_session";
export const OIDC_TRANSACTION_COOKIE = "cl_oidc_transaction";

export type AuthenticatedSession = SessionUser & {
  mode: AuthMode;
  expiresAt: number;
  accessToken?: string;
  refreshToken?: string;
  idToken?: string;
};

export type OidcTransaction = {
  state: string;
  nonce: string;
  codeVerifier: string;
  expiresAt: number;
};

function encryptionKey() {
  const configured =
    process.env.SESSION_SECRET ??
    (process.env.NODE_ENV === "production"
      ? requireServerEnv("SESSION_SECRET")
      : "local-development-session-secret-not-for-production");
  if (configured.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters");
  return createHash("sha256").update(configured).digest();
}

function encrypt(value: object) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(value), "utf8"),
    cipher.final(),
  ]);
  return [iv, cipher.getAuthTag(), ciphertext]
    .map((part) => part.toString("base64url"))
    .join(".");
}

function decrypt<T>(value: string | undefined): T | null {
  if (!value) return null;
  try {
    const [ivValue, tagValue, ciphertextValue] = value.split(".");
    if (!ivValue || !tagValue || !ciphertextValue) return null;
    const decipher = createDecipheriv(
      "aes-256-gcm",
      encryptionKey(),
      Buffer.from(ivValue, "base64url"),
    );
    decipher.setAuthTag(Buffer.from(tagValue, "base64url"));
    const plaintext = Buffer.concat([
      decipher.update(Buffer.from(ciphertextValue, "base64url")),
      decipher.final(),
    ]).toString("utf8");
    return JSON.parse(plaintext) as T;
  } catch {
    return null;
  }
}

export function encodeSession(session: AuthenticatedSession) {
  return encrypt(session);
}

export function decodeSession(value: string | undefined): AuthenticatedSession | null {
  const parsed = decrypt<Partial<AuthenticatedSession>>(value);
  if (
    !parsed ||
    typeof parsed.actorId !== "string" ||
    typeof parsed.displayName !== "string" ||
    !isUserRole(parsed.role) ||
    (parsed.mode !== "demo" && parsed.mode !== "oidc") ||
    typeof parsed.expiresAt !== "number" ||
    parsed.expiresAt <= Math.floor(Date.now() / 1000)
  ) return null;
  return parsed as AuthenticatedSession;
}

export function encodeOidcTransaction(transaction: OidcTransaction) {
  return encrypt(transaction);
}

export function decodeOidcTransaction(value: string | undefined): OidcTransaction | null {
  const parsed = decrypt<Partial<OidcTransaction>>(value);
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

export async function getSession() {
  return decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
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
