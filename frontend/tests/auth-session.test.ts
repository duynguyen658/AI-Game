import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: vi.fn() }));

import {
  decodeSession,
  encodeSession,
  isAuthenticatedSession,
  type AuthenticatedSession,
  type DemoSession,
} from "@/lib/auth/session";
import {
  AuthCookieSizeError,
  encodedCookieBytes,
  getOidcSessionStore,
} from "@/lib/auth/session-store";
import { sessionCookieMaxAge } from "@/lib/auth/adapter";

const now = 2_000_000_000;

function oidcSession(tokenLength = 32): AuthenticatedSession {
  return {
    actor: { id: "user-1", role: "manager", displayName: "Test User" },
    accessToken: "a".repeat(tokenLength),
    refreshToken: "r".repeat(tokenLength),
    idToken: "i".repeat(tokenLength),
    accessTokenExpiresAt: now + 60,
    sessionExpiresAt: now + 36_000,
    createdAt: now,
    provider: "oidc",
    sessionVersion: 1,
  };
}

describe("OIDC session model", () => {
  beforeEach(() => {
    vi.stubEnv("SESSION_SECRET", "unit-test-session-secret-at-least-32-characters");
    vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "unit-test-oidc-encryption-key-at-least-32-characters");
    vi.stubEnv("OIDC_SESSION_STORAGE", "cookie");
    vi.stubEnv("AUTH_COOKIE_MAX_BYTES", "3800");
  });

  it("keeps access-token and absolute session expiry independent", () => {
    const session = oidcSession();
    session.accessTokenExpiresAt = now - 1;
    expect(isAuthenticatedSession(session)).toBe(true);
    expect(session.sessionExpiresAt).toBeGreaterThan(now);
    expect(sessionCookieMaxAge(session.sessionExpiresAt, now)).toBe(36_000);
    expect(sessionCookieMaxAge(now - 1, now)).toBe(0);
  });

  it("rejects expired demo sessions and old shared-expiry cookies", () => {
    const active: DemoSession = {
      actorId: "demo-user",
      displayName: "Demo User",
      role: "marketing",
      mode: "demo",
      createdAt: now - 10,
      sessionExpiresAt: now + 10,
    };
    expect(decodeSession(encodeSession(active), now)?.actorId).toBe("demo-user");
    expect(decodeSession(encodeSession({ ...active, sessionExpiresAt: now }), now)).toBeNull();

    const oldCookie = encodeSession({ ...active, sessionExpiresAt: undefined } as unknown as DemoSession);
    expect(decodeSession(oldCookie, now)).toBeNull();
  });

  it.each([
    ["small", 32],
    ["medium JWT", 500],
    ["large claim set", 850],
  ])("accepts a %s encrypted fixture under the configured limit", async (_label, length) => {
    const created = await getOidcSessionStore().createSession(oidcSession(length));
    expect(encodedCookieBytes(created.cookieValue)).toBeLessThanOrEqual(3800);
  });

  it("rejects an oversized access, refresh, and ID token combination", async () => {
    await expect(getOidcSessionStore().createSession(oidcSession(1600))).rejects.toBeInstanceOf(
      AuthCookieSizeError,
    );
  });

  it("rejects stale cookie-mode compare-and-swap updates", async () => {
    const store = getOidcSessionStore();
    const created = await store.createSession(oidcSession());
    const result = await store.compareAndSwapRefresh(created.cookieValue, 99, {
      ...created.session,
      sessionVersion: 2,
    });
    expect(result.outcome).toBe("VERSION_CONFLICT");
  });
});
