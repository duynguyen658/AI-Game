import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const cookieJar = new Map<string, string>();
const setCookie = vi.fn((name: string, value: string) => {
  if (value) cookieJar.set(name, value);
  else cookieJar.delete(name);
});

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) => cookieJar.has(name) ? { value: cookieJar.get(name) } : undefined,
    set: setCookie,
  })),
}));

vi.mock("openid-client", () => ({
  discovery: vi.fn(async () => ({})),
  refreshTokenGrant: vi.fn(),
  authorizationCodeGrant: vi.fn(),
  randomPKCECodeVerifier: vi.fn(() => "verifier"),
  randomState: vi.fn(() => "state"),
  randomNonce: vi.fn(() => "nonce"),
  calculatePKCECodeChallenge: vi.fn(async () => "challenge"),
  buildAuthorizationUrl: vi.fn(() => new URL("https://issuer.test/authorize")),
}));

import * as oidc from "openid-client";
import { getValidAccessToken, OidcAuthAdapter } from "@/lib/auth/adapter";
import { SESSION_COOKIE, type AuthenticatedSession } from "@/lib/auth/session";
import { getOidcSessionStore } from "@/lib/auth/session-store";

function session(overrides: Partial<AuthenticatedSession> = {}): AuthenticatedSession {
  const now = Math.floor(Date.now() / 1000);
  return {
    actor: { id: "user-1", role: "manager", displayName: "Test User" },
    accessToken: "access-old",
    refreshToken: "refresh-old",
    idToken: "id-old",
    accessTokenExpiresAt: now - 1,
    sessionExpiresAt: now + 3600,
    createdAt: now - 100,
    provider: "oidc",
    sessionVersion: 1,
    ...overrides,
  };
}

function tokenResponse(replacement: string | undefined = "refresh-new"): {
  access_token: string;
  refresh_token: string | undefined;
  id_token: string;
  token_type: string;
  expiresIn: () => number;
  claims: () => { sub: string };
} {
  return {
    access_token: "access-new",
    refresh_token: replacement,
    id_token: "id-new",
    token_type: "Bearer",
    expiresIn: () => 120,
    claims: () => ({ sub: "user-1" }),
  };
}

describe("OIDC access-token resolution", () => {
  beforeEach(() => {
    cookieJar.clear();
    setCookie.mockClear();
    vi.clearAllMocks();
    vi.stubEnv("AUTH_MODE", "oidc");
    vi.stubEnv("OIDC_ISSUER", "https://issuer.test");
    vi.stubEnv("OIDC_CLIENT_ID", "client");
    vi.stubEnv("OIDC_CLIENT_SECRET", "client-secret");
    vi.stubEnv("OIDC_REDIRECT_URI", "https://app.test/api/auth/callback");
    vi.stubEnv("SESSION_SECRET", "unit-test-session-secret-at-least-32-characters");
    vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "unit-test-oidc-encryption-key-at-least-32-characters");
    vi.stubEnv("OIDC_SESSION_STORAGE", "cookie");
    vi.stubEnv("OIDC_REFRESH_SKEW_SECONDS", "90");
  });

  it("returns a token that is valid beyond refresh skew", async () => {
    const active = session({ accessTokenExpiresAt: Math.floor(Date.now() / 1000) + 120 });
    const result = await getValidAccessToken(active);
    expect(result.status).toBe("valid");
    expect(oidc.refreshTokenGrant).not.toHaveBeenCalled();
  });

  it("refreshes after access-token expiry and persists rotation semantics", async () => {
    vi.mocked(oidc.refreshTokenGrant).mockResolvedValue(tokenResponse() as never);
    const result = await getValidAccessToken(session());
    expect(result.status).toBe("refreshed");
    if (result.status !== "authentication_required") {
      expect(result.session.refreshToken).toBe("refresh-new");
      expect(result.session.sessionVersion).toBe(2);
    }
  });

  it("retains the previous refresh token when the provider omits rotation", async () => {
    const withoutRotation = tokenResponse();
    withoutRotation.refresh_token = undefined;
    vi.mocked(oidc.refreshTokenGrant).mockResolvedValue(withoutRotation as never);
    const result = await getValidAccessToken(session());
    expect(result.status).toBe("refreshed");
    if (result.status === "refreshed") expect(result.session.refreshToken).toBe("refresh-old");
  });

  it.each([
    ["missing refresh token", session({ refreshToken: undefined }), "OIDC_REAUTHENTICATION_REQUIRED"],
    ["absolute expiry", session({ sessionExpiresAt: 1 }), "OIDC_SESSION_EXPIRED"],
  ])("requires authentication for %s", async (_label, input, code) => {
    const result = await getValidAccessToken(input);
    expect(result).toEqual({ status: "authentication_required", errorCode: code });
  });

  it("maps invalid_grant without exposing the provider response", async () => {
    vi.mocked(oidc.refreshTokenGrant).mockRejectedValue({ error: "invalid_grant", body: "secret" });
    expect(await getValidAccessToken(session())).toEqual({
      status: "authentication_required",
      errorCode: "OIDC_REFRESH_INVALID_GRANT",
    });
  });

  it("maps provider unavailability and malformed responses", async () => {
    vi.mocked(oidc.refreshTokenGrant).mockRejectedValueOnce(new TypeError("network unavailable"));
    expect(await getValidAccessToken(session())).toMatchObject({ errorCode: "OIDC_REFRESH_UNAVAILABLE" });
    vi.mocked(oidc.refreshTokenGrant).mockResolvedValueOnce({
      ...tokenResponse(),
      expiresIn: () => undefined,
    } as never);
    expect(await getValidAccessToken(session())).toMatchObject({ errorCode: "OIDC_REFRESH_MALFORMED_RESPONSE" });
  });

  it.each([2, 5])("single-flights %i simultaneous refresh requests", async (callers) => {
    const store = getOidcSessionStore();
    const created = await store.createSession(session());
    cookieJar.set(SESSION_COOKIE, created.cookieValue);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    vi.mocked(oidc.refreshTokenGrant).mockImplementation(async () => {
      await gate;
      return tokenResponse() as never;
    });
    const requests = Array.from({ length: callers }, () => new OidcAuthAdapter().getAccessToken());
    release();
    const results = await Promise.all(requests);
    expect(oidc.refreshTokenGrant).toHaveBeenCalledTimes(1);
    expect(results.every((result) => result.status === "refreshed" && result.accessToken === "access-new"))
      .toBe(true);
  });
});
