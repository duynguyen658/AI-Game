import "server-only";

import { cookies } from "next/headers";
import * as oidc from "openid-client";
import { isUserRole, type SessionUser } from "./types";
import {
  decodeOidcTransaction,
  decodeSession,
  encodeOidcTransaction,
  encodeSession,
  OIDC_TRANSACTION_COOKIE,
  SESSION_COOKIE,
  sessionCookieOptions,
  type AuthenticatedSession,
  type OidcTransaction,
} from "./session";
import { getAuthMode, requireServerEnv } from "@/lib/env/server";

export interface AuthAdapter {
  createLoginRequest(): Promise<URL>;
  handleCallback(request: Request): Promise<AuthenticatedSession>;
  getServerSession(): Promise<AuthenticatedSession | null>;
  getAccessToken(): Promise<string | null>;
  logout(): Promise<URL | null>;
}

function setSessionCookie(session: AuthenticatedSession) {
  return cookies().then((store) => store.set(SESSION_COOKIE, encodeSession(session), {
    ...sessionCookieOptions,
    maxAge: Math.max(session.expiresAt - Math.floor(Date.now() / 1000), 0),
  }));
}

function clearAuthCookies() {
  return cookies().then((store) => {
    store.set(SESSION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
    store.set(OIDC_TRANSACTION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
  });
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
    return session?.mode === "demo" ? session : null;
  }

  async getAccessToken() {
    return null;
  }

  async logout() {
    await clearAuthCookies();
    return null;
  }
}

let oidcConfiguration: Promise<oidc.Configuration> | undefined;

function configuration() {
  oidcConfiguration ??= oidc.discovery(
    new URL(requireServerEnv("OIDC_ISSUER")),
    requireServerEnv("OIDC_CLIENT_ID"),
    requireServerEnv("OIDC_CLIENT_SECRET"),
  );
  return oidcConfiguration;
}

function oidcUser(claims: Record<string, unknown>): SessionUser {
  const actorId = claims.sub;
  const roleClaim = process.env.OIDC_ROLE_CLAIM?.trim() || "role";
  const role = claims[roleClaim];
  const displayName = claims.name ?? claims.preferred_username ?? claims.email ?? actorId;
  if (typeof actorId !== "string" || !isUserRole(role) || typeof displayName !== "string") {
    throw new Error("OIDC identity is missing a supported subject, role, or display name");
  }
  return { actorId, role, displayName };
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
    (await cookies()).set(
      OIDC_TRANSACTION_COOKIE,
      encodeOidcTransaction(transaction),
      { ...sessionCookieOptions, maxAge: 600 },
    );
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
    const store = await cookies();
    const transaction = decodeOidcTransaction(store.get(OIDC_TRANSACTION_COOKIE)?.value);
    if (!transaction) throw new Error("OIDC login transaction is missing or expired");
    const tokens = await oidc.authorizationCodeGrant(
      await configuration(),
      request,
      {
        pkceCodeVerifier: transaction.codeVerifier,
        expectedState: transaction.state,
        expectedNonce: transaction.nonce,
      },
      { redirect_uri: requireServerEnv("OIDC_REDIRECT_URI") },
    );
    const claims = tokens.claims();
    if (!claims || !tokens.access_token) throw new Error("OIDC provider returned no identity or access token");
    const expiresAt = Math.floor(Date.now() / 1000) + (tokens.expiresIn() ?? 300);
    const session: AuthenticatedSession = {
      ...oidcUser(claims),
      mode: "oidc",
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      idToken: tokens.id_token,
      expiresAt,
    };
    await setSessionCookie(session);
    store.set(OIDC_TRANSACTION_COOKIE, "", { ...sessionCookieOptions, maxAge: 0 });
    return session;
  }

  async getServerSession() {
    const session = decodeSession((await cookies()).get(SESSION_COOKIE)?.value);
    return session?.mode === "oidc" ? session : null;
  }

  async getAccessToken() {
    const session = await this.getServerSession();
    if (!session?.accessToken) return null;
    if (session.expiresAt > Math.floor(Date.now() / 1000) + 30) return session.accessToken;
    if (!session.refreshToken) return null;
    const tokens = await oidc.refreshTokenGrant(await configuration(), session.refreshToken);
    const refreshed: AuthenticatedSession = {
      ...session,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token ?? session.refreshToken,
      idToken: tokens.id_token ?? session.idToken,
      expiresAt: Math.floor(Date.now() / 1000) + (tokens.expiresIn() ?? 300),
    };
    await setSessionCookie(refreshed);
    return refreshed.accessToken ?? null;
  }

  async logout() {
    const session = await this.getServerSession();
    const metadata = (await configuration()).serverMetadata();
    await clearAuthCookies();
    if (!metadata.end_session_endpoint) return null;
    const url = new URL(metadata.end_session_endpoint);
    if (session?.idToken) url.searchParams.set("id_token_hint", session.idToken);
    const postLogout = process.env.OIDC_POST_LOGOUT_REDIRECT_URI;
    if (postLogout) url.searchParams.set("post_logout_redirect_uri", postLogout);
    return url;
  }
}

export function getAuthAdapter(): AuthAdapter {
  return getAuthMode() === "oidc" ? new OidcAuthAdapter() : new DemoAuthAdapter();
}
