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
  authorizationCodeGrant: vi.fn(),
  refreshTokenGrant: vi.fn(),
  allowInsecureRequests: vi.fn(),
  randomPKCECodeVerifier: vi.fn(),
  randomState: vi.fn(),
  randomNonce: vi.fn(),
  calculatePKCECodeChallenge: vi.fn(),
  buildAuthorizationUrl: vi.fn(),
}));

import * as oidc from "openid-client";
import { OidcAuthAdapter } from "@/lib/auth/adapter";
import {
  encodeOidcTransaction,
  OIDC_TRANSACTION_COOKIE,
  SESSION_COOKIE,
} from "@/lib/auth/session";

function installTransaction() {
  cookieJar.set(OIDC_TRANSACTION_COOKIE, encodeOidcTransaction({
    state: "expected-state",
    nonce: "expected-nonce",
    codeVerifier: "expected-verifier",
    expiresAt: Math.floor(Date.now() / 1000) + 60,
  }));
}

function tokenResponse() {
  return {
    access_token: "access-token",
    refresh_token: "refresh-token",
    id_token: "id-token",
    token_type: "Bearer",
    expiresIn: () => 300,
    claims: () => ({ sub: "user-1", role: "manager", name: "Test User" }),
  };
}

describe("OIDC callback security boundary", () => {
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
    installTransaction();
  });

  it("uses canonical callback URI and passes PKCE, state, and nonce checks", async () => {
    vi.mocked(oidc.authorizationCodeGrant).mockResolvedValue(tokenResponse() as never);
    await new OidcAuthAdapter().handleCallback(
      new Request("https://untrusted-host.test/api/auth/callback?code=code&state=expected-state"),
    );
    const [, callback, checks] = vi.mocked(oidc.authorizationCodeGrant).mock.calls[0]!;
    expect(callback.toString()).toBe(
      "https://app.test/api/auth/callback?code=code&state=expected-state",
    );
    expect(checks).toMatchObject({
      pkceCodeVerifier: "expected-verifier",
      expectedState: "expected-state",
      expectedNonce: "expected-nonce",
    });
    expect(cookieJar.has(SESSION_COOKIE)).toBe(true);
    expect(cookieJar.has(OIDC_TRANSACTION_COOKIE)).toBe(false);
  });

  it("consumes the callback transaction before exchange to block replay", async () => {
    vi.mocked(oidc.authorizationCodeGrant).mockResolvedValue(tokenResponse() as never);
    const adapter = new OidcAuthAdapter();
    const request = new Request("https://app.test/api/auth/callback?code=code&state=expected-state");
    await adapter.handleCallback(request);
    await expect(adapter.handleCallback(request)).rejects.toThrow(
      "OIDC login transaction is missing or expired",
    );
    expect(oidc.authorizationCodeGrant).toHaveBeenCalledTimes(1);
  });

  it.each([
    "state mismatch",
    "nonce mismatch",
    "PKCE mismatch",
    "issuer mismatch",
    "audience mismatch",
    "expired ID token",
  ])("does not create a session when validation reports %s", async (reason) => {
    vi.mocked(oidc.authorizationCodeGrant).mockRejectedValue(new Error(reason));
    await expect(new OidcAuthAdapter().handleCallback(
      new Request("https://app.test/api/auth/callback?code=bad&state=bad"),
    )).rejects.toThrow(reason);
    expect(cookieJar.has(SESSION_COOKIE)).toBe(false);
    expect(cookieJar.has(OIDC_TRANSACTION_COOKIE)).toBe(false);
  });
});
