import "server-only";

import { createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import * as oidc from "openid-client";
import { getAuthMode, getOidcSessionConfig, requireServerEnv } from "@/lib/env/server";
import { isUserRole } from "./types";
import {
  decodeOidcTransaction,
  decodeSession,
  encodeOidcTransaction,
  OIDC_TRANSACTION_COOKIE,
  SESSION_COOKIE,
  sessionCookieOptions,
  toPublicSession,
  type AuthenticatedSession,
  type OidcTransaction,
  type PublicSession,
} from "./session";
import { AuthCookieSizeError, getOidcSessionStore, type StoredSession } from "./session-store";
import { recordOidcEvent } from "./observability";

export type OidcAuthErrorCode =
  | "OIDC_REFRESH_INVALID_GRANT"
  | "OIDC_REFRESH_UNAVAILABLE"
  | "OIDC_REFRESH_MALFORMED_RESPONSE"
  | "OIDC_SESSION_EXPIRED"
  | "OIDC_REAUTHENTICATION_REQUIRED";

export type AccessTokenResolution =
  | { status: "valid" | "refreshed"; accessToken: string; session: AuthenticatedSession }
  | { status: "authentication_required"; errorCode: OidcAuthErrorCode };

export interface AuthAdapter {
  createLoginRequest(): Promise<URL>;
  handleCallback(request: Request): Promise<AuthenticatedSession>;
  getServerSession(): Promise<PublicSession | null>;
  getAccessToken(): Promise<AccessTokenResolution>;
  logout(): Promise<URL | null>;
}

export function sessionCookieMaxAge(sessionExpiresAt: number, now = Math.floor(Date.now() / 1000)) {
  return Math.max(sessionExpiresAt - now, 0);
}

async function setSessionCookie(cookieValue: string, sessionExpiresAt: number) {
  const maxAge = sessionCookieMaxAge(sessionExpiresAt);
  (await cookies()).set(SESSION_COOKIE, cookieValue, { ...sessionCookieOptions, maxAge });
}

async function clearAuthCookies() {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
  store.set(OIDC_TRANSACTION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
}

export class DemoAuthAdapter implements AuthAdapter {
  async createLoginRequest(): Promise<URL> {
    throw new Error("Demo mode uses the explicit demo session endpoint");
  }
  async handleCallback(): Promise<AuthenticatedSession> {
    throw new Error("OIDC callback is unavailable in demo mode");
  }
  async getServerSession() {
    const session = decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
    return session;
  }
  async getAccessToken(): Promise<AccessTokenResolution> {
    return { status: "authentication_required", errorCode: "OIDC_REAUTHENTICATION_REQUIRED" };
  }
  async logout() {
    await clearAuthCookies();
    return null;
  }
}

let oidcConfiguration: Promise<oidc.Configuration> | undefined;

function configuration() {
  const issuer = new URL(requireServerEnv("OIDC_ISSUER"));
  const options = getOidcSessionConfig().testIssuerEnabled
    ? { execute: [oidc.allowInsecureRequests] }
    : undefined;
  oidcConfiguration ??= oidc.discovery(
    issuer,
    requireServerEnv("OIDC_CLIENT_ID"),
    requireServerEnv("OIDC_CLIENT_SECRET"),
    undefined,
    options,
  ).then((config) => {
    config.timeout = 10;
    return config;
  });
  return oidcConfiguration;
}

function oidcUser(claims: Record<string, unknown>): AuthenticatedSession["actor"] {
  const actorId = claims.sub;
  const roleClaim = process.env.OIDC_ROLE_CLAIM?.trim() || "role";
  const role = claims[roleClaim];
  const displayName = claims.name ?? claims.preferred_username ?? claims.email ?? actorId;
  if (typeof actorId !== "string" || !isUserRole(role) || typeof displayName !== "string") {
    throw new Error("OIDC identity is missing a supported subject, role, or display name");
  }
  return {
    id: actorId,
    role,
    displayName,
    email: typeof claims.email === "string" ? claims.email : undefined,
  };
}

function invalidGrant(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const candidate = error as Record<string, unknown>;
  return candidate.error === "invalid_grant" || candidate.code === "OAUTH_INVALID_GRANT" ||
    (candidate.cause !== undefined && invalidGrant(candidate.cause));
}

export async function getValidAccessToken(
  session: AuthenticatedSession,
): Promise<AccessTokenResolution> {
  const now = Math.floor(Date.now() / 1000);
  const { refreshSkewSeconds } = getOidcSessionConfig();
  if (session.sessionExpiresAt <= now) {
    return { status: "authentication_required", errorCode: "OIDC_SESSION_EXPIRED" };
  }
  if (session.accessTokenExpiresAt > now + refreshSkewSeconds) {
    return { status: "valid", accessToken: session.accessToken, session };
  }
  if (!session.refreshToken) {
    return { status: "authentication_required", errorCode: "OIDC_REAUTHENTICATION_REQUIRED" };
  }
  try {
    const tokens = await oidc.refreshTokenGrant(await configuration(), session.refreshToken);
    const expiresIn = tokens.expiresIn();
    if (
      typeof tokens.access_token !== "string" || !tokens.access_token ||
      typeof expiresIn !== "number" || !Number.isFinite(expiresIn) || expiresIn <= 0 ||
      (tokens.token_type && tokens.token_type.toLowerCase() !== "bearer")
    ) {
      return { status: "authentication_required", errorCode: "OIDC_REFRESH_MALFORMED_RESPONSE" };
    }
    if (tokens.id_token && !tokens.claims()) {
      return { status: "authentication_required", errorCode: "OIDC_REFRESH_MALFORMED_RESPONSE" };
    }
    const refreshed: AuthenticatedSession = {
      ...session,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token ?? session.refreshToken,
      idToken: tokens.id_token ?? session.idToken,
      accessTokenExpiresAt: now + expiresIn,
      refreshedAt: now,
      sessionVersion: session.sessionVersion + 1,
    };
    return { status: "refreshed", accessToken: refreshed.accessToken, session: refreshed };
  } catch (error) {
    return {
      status: "authentication_required",
      errorCode: invalidGrant(error) ? "OIDC_REFRESH_INVALID_GRANT" : "OIDC_REFRESH_UNAVAILABLE",
    };
  }
}

type RefreshResult = AccessTokenResolution & { cookieValue?: string };
const refreshFlights = new Map<string, Promise<RefreshResult>>();
const REFRESH_WAIT_ATTEMPTS = 150;
const REFRESH_WAIT_INTERVAL_MS = 100;

function flightKey(cookieValue: string) {
  return createHash("sha256").update(cookieValue).digest("hex");
}

async function revoke(cookieValue: string, errorCode: OidcAuthErrorCode) {
  await getOidcSessionStore().revokeSession(cookieValue).catch(() => "NOT_FOUND");
  await clearAuthCookies();
  recordOidcEvent(errorCode === "OIDC_SESSION_EXPIRED" ? "oidc_session_expired" : "oidc_session_revoked", { errorCode });
}

async function refreshStoredSession(cookieValue: string): Promise<RefreshResult> {
  const storage = getOidcSessionStore();
  const current = await storage.readSession(cookieValue);
  if (current.outcome !== "FOUND") {
    return {
      status: "authentication_required",
      errorCode: current.outcome === "EXPIRED" ? "OIDC_SESSION_EXPIRED" : "OIDC_REAUTHENTICATION_REQUIRED",
    };
  }
  const ownerHash = randomBytes(32).toString("hex");
  const claimed = await storage.claimRefresh(cookieValue, current.session.sessionVersion, ownerHash);
  if (!claimed) {
    for (let attempt = 0; attempt < REFRESH_WAIT_ATTEMPTS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, REFRESH_WAIT_INTERVAL_MS));
      const winner = await storage.readSession(cookieValue);
      if (winner.outcome !== "FOUND") {
        return {
          status: "authentication_required",
          errorCode: winner.outcome === "EXPIRED" ? "OIDC_SESSION_EXPIRED" : "OIDC_REAUTHENTICATION_REQUIRED",
        };
      }
      if (winner.session.sessionVersion > current.session.sessionVersion) {
        return {
          status: "refreshed",
          accessToken: winner.session.accessToken,
          session: winner.session,
          cookieValue,
        };
      }
    }
    return { status: "authentication_required", errorCode: "OIDC_REFRESH_UNAVAILABLE" };
  }
  const resolution = await getValidAccessToken(current.session);
  if (resolution.status !== "refreshed") return resolution;
  const updated = await storage.compareAndSwapRefresh(
    cookieValue,
    current.session.sessionVersion,
    resolution.session,
    ownerHash,
  );
  if (updated.outcome === "UPDATED") {
    recordOidcEvent("oidc_access_token_refreshed", { storage: getOidcSessionConfig().storage });
    return { ...resolution, cookieValue: updated.cookieValue };
  }
  if (updated.outcome === "VERSION_CONFLICT") {
    recordOidcEvent("oidc_refresh_version_conflict", { storage: getOidcSessionConfig().storage });
    const winner = await storage.readSession(cookieValue);
    if (winner.outcome === "FOUND" && winner.session.sessionVersion > current.session.sessionVersion) {
      return { status: "refreshed", accessToken: winner.session.accessToken, session: winner.session, cookieValue };
    }
  }
  return { status: "authentication_required", errorCode: "OIDC_REAUTHENTICATION_REQUIRED" };
}

export class OidcAuthAdapter implements AuthAdapter {
  async createLoginRequest() {
    const config = await configuration();
    const codeVerifier = oidc.randomPKCECodeVerifier();
    const transaction: OidcTransaction = {
      codeVerifier,
      state: oidc.randomState(),
      nonce: oidc.randomNonce(),
      expiresAt: Math.floor(Date.now() / 1000) + 600,
    };
    (await cookies()).set(OIDC_TRANSACTION_COOKIE, encodeOidcTransaction(transaction), {
      ...sessionCookieOptions,
      maxAge: 600,
    });
    recordOidcEvent("oidc_login_started");
    return oidc.buildAuthorizationUrl(config, {
      redirect_uri: requireServerEnv("OIDC_REDIRECT_URI"),
      scope: process.env.OIDC_SCOPE?.trim() || "openid profile email",
      code_challenge: await oidc.calculatePKCECodeChallenge(codeVerifier),
      code_challenge_method: "S256",
      state: transaction.state,
      nonce: transaction.nonce,
    });
  }

  async handleCallback(request: Request) {
    const cookieStore = await cookies();
    const transaction = decodeOidcTransaction(cookieStore.get(OIDC_TRANSACTION_COOKIE)?.value);
    cookieStore.set(OIDC_TRANSACTION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
    if (!transaction) throw new Error("OIDC login transaction is missing or expired");
    const callbackUrl = new URL(requireServerEnv("OIDC_REDIRECT_URI"));
    callbackUrl.search = new URL(request.url).search;
    const tokens = await oidc.authorizationCodeGrant(
      await configuration(),
      callbackUrl,
      {
        pkceCodeVerifier: transaction.codeVerifier,
        expectedState: transaction.state,
        expectedNonce: transaction.nonce,
      },
    );
    const claims = tokens.claims();
    const expiresIn = tokens.expiresIn();
    if (!claims || !tokens.access_token || !expiresIn || expiresIn <= 0) {
      throw new Error("OIDC provider returned an invalid identity or access token");
    }
    const now = Math.floor(Date.now() / 1000);
    const session: AuthenticatedSession = {
      actor: oidcUser(claims),
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      idToken: tokens.id_token,
      accessTokenExpiresAt: now + expiresIn,
      sessionExpiresAt: now + getOidcSessionConfig().sessionMaxAgeSeconds,
      createdAt: now,
      provider: "oidc",
      sessionVersion: 1,
    };
    try {
      const created = await getOidcSessionStore().createSession(session);
      await setSessionCookie(created.cookieValue, session.sessionExpiresAt);
    } catch (error) {
      if (error instanceof AuthCookieSizeError) {
        recordOidcEvent("oidc_session_size_rejected", { storage: getOidcSessionConfig().storage });
      }
      throw error;
    }
    recordOidcEvent("oidc_login_completed", { storage: getOidcSessionConfig().storage });
    return session;
  }

  async getServerSession() {
    const stored = await getOidcSessionStore().readSession((await cookies()).get(SESSION_COOKIE)?.value);
    return stored.outcome === "FOUND" ? toPublicSession(stored.session) : null;
  }

  async getAccessToken(): Promise<AccessTokenResolution> {
    const cookieValue = (await cookies()).get(SESSION_COOKIE)?.value;
    if (!cookieValue) return { status: "authentication_required", errorCode: "OIDC_REAUTHENTICATION_REQUIRED" };
    const initial = await getOidcSessionStore().readSession(cookieValue);
    if (initial.outcome !== "FOUND") {
      const errorCode = initial.outcome === "EXPIRED" ? "OIDC_SESSION_EXPIRED" : "OIDC_REAUTHENTICATION_REQUIRED";
      await revoke(cookieValue, errorCode);
      return { status: "authentication_required", errorCode };
    }
    const now = Math.floor(Date.now() / 1000);
    if (initial.session.sessionExpiresAt <= now) {
      await revoke(cookieValue, "OIDC_SESSION_EXPIRED");
      return { status: "authentication_required", errorCode: "OIDC_SESSION_EXPIRED" };
    }
    if (initial.session.accessTokenExpiresAt > now + getOidcSessionConfig().refreshSkewSeconds) {
      return { status: "valid", accessToken: initial.session.accessToken, session: initial.session };
    }
    if (!initial.session.refreshToken) {
      await revoke(cookieValue, "OIDC_REAUTHENTICATION_REQUIRED");
      return { status: "authentication_required", errorCode: "OIDC_REAUTHENTICATION_REQUIRED" };
    }

    const key = flightKey(cookieValue);
    let flight = refreshFlights.get(key);
    if (!flight) {
      flight = refreshStoredSession(cookieValue).finally(() => refreshFlights.delete(key));
      refreshFlights.set(key, flight);
    }
    const result = await flight;
    if (result.status !== "authentication_required") {
      if (result.status === "refreshed") {
        await setSessionCookie(result.cookieValue ?? cookieValue, result.session.sessionExpiresAt);
      }
      return result;
    }
    await revoke(cookieValue, result.errorCode);
    recordOidcEvent("oidc_refresh_failed", { errorCode: result.errorCode });
    return result;
  }

  async logout() {
    const cookieValue = (await cookies()).get(SESSION_COOKIE)?.value;
    let session: StoredSession | undefined;
    if (cookieValue) {
      const loaded = await getOidcSessionStore().readSession(cookieValue);
      if (loaded.outcome === "FOUND") session = loaded;
      await getOidcSessionStore().revokeSession(cookieValue).catch(() => "NOT_FOUND");
      recordOidcEvent("oidc_session_revoked");
    }
    await clearAuthCookies();
    let metadata: oidc.ServerMetadata;
    try { metadata = (await configuration()).serverMetadata(); } catch { return null; }
    if (!metadata.end_session_endpoint) return null;
    const url = new URL(metadata.end_session_endpoint);
    if (session?.session.idToken) url.searchParams.set("id_token_hint", session.session.idToken);
    const postLogout = process.env.OIDC_POST_LOGOUT_REDIRECT_URI;
    if (postLogout) url.searchParams.set("post_logout_redirect_uri", postLogout);
    return url;
  }
}

export function getAuthAdapter(): AuthAdapter {
  return getAuthMode() === "oidc" ? new OidcAuthAdapter() : new DemoAuthAdapter();
}
