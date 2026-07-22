import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import type { AuthenticatedSession } from "@/lib/auth/session";
import { AuthCookieSizeError, encodedCookieBytes, getOidcSessionStore } from "@/lib/auth/session-store";

const limit = 3800;

function fixture(tokenLength: number): AuthenticatedSession {
  const now = Math.floor(Date.now() / 1000);
  return {
    actor: { id: "size-user", role: "manager", displayName: "Cookie Size User" },
    accessToken: "a".repeat(tokenLength),
    refreshToken: "r".repeat(tokenLength),
    idToken: "i".repeat(tokenLength),
    accessTokenExpiresAt: now + 300,
    sessionExpiresAt: now + 36_000,
    createdAt: now,
    provider: "oidc",
    sessionVersion: 1,
  };
}

describe("authentication cookie size report", () => {
  beforeEach(() => {
    vi.stubEnv("OIDC_SESSION_STORAGE", "cookie");
    vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "cookie-size-report-key-at-least-32-characters");
    vi.stubEnv("AUTH_COOKIE_MAX_BYTES", String(limit));
  });

  it("prints byte counts without token values", async () => {
    const store = getOidcSessionStore();
    const small = encodedCookieBytes((await store.createSession(fixture(32))).cookieValue);
    const medium = encodedCookieBytes((await store.createSession(fixture(500))).cookieValue);
    let maximum = medium;
    for (let length = 550; length <= 1200; length += 25) {
      try {
        maximum = encodedCookieBytes((await store.createSession(fixture(length))).cookieValue);
      } catch (error) {
        expect(error).toBeInstanceOf(AuthCookieSizeError);
        break;
      }
    }
    console.info(JSON.stringify({
      fixture: "authentication_cookie_size_bytes",
      small,
      medium,
      maximum_supported_tested: maximum,
      configured_limit: limit,
    }));
    expect(small).toBeLessThan(medium);
    expect(maximum).toBeLessThanOrEqual(limit);
  });
});
