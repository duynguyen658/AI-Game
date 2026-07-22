import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { getOidcSessionConfig, validateServerEnv } from "@/lib/env/server";

afterEach(() => vi.unstubAllEnvs());

function productionOidcEnv() {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("AUTH_MODE", "oidc");
  vi.stubEnv("BACKEND_API_URL", "https://api.internal.test");
  vi.stubEnv("SESSION_SECRET", "production-cookie-secret-at-least-32-characters");
  vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "production-payload-key-at-least-32-characters");
  vi.stubEnv("OIDC_ISSUER", "https://issuer.test");
  vi.stubEnv("OIDC_CLIENT_ID", "client");
  vi.stubEnv("OIDC_CLIENT_SECRET", "client-secret");
  vi.stubEnv("OIDC_REDIRECT_URI", "https://app.test/api/auth/callback");
  vi.stubEnv("FRONTEND_DATABASE_URL", "postgresql://user:password@db/session");
  vi.stubEnv("OIDC_TEST_ISSUER_ENABLED", "false");
}

describe("OIDC session environment", () => {
  it("defaults production to bounded PostgreSQL sessions", () => {
    productionOidcEnv();
    expect(getOidcSessionConfig()).toMatchObject({
      storage: "postgres",
      sessionMaxAgeSeconds: 36_000,
      refreshSkewSeconds: 90,
      cookieMaxBytes: 3800,
    });
    expect(validateServerEnv()).toBe("oidc");
  });

  it("rejects weak keys, test issuers, and unlimited lifetimes in production", () => {
    productionOidcEnv();
    vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "weak");
    expect(() => validateServerEnv()).toThrow("at least 32 characters");

    productionOidcEnv();
    vi.stubEnv("OIDC_TEST_ISSUER_ENABLED", "true");
    expect(() => validateServerEnv()).toThrow("must be false in production");

    productionOidcEnv();
    vi.stubEnv("OIDC_SESSION_MAX_AGE_SECONDS", "999999");
    expect(() => validateServerEnv()).toThrow("must be between");
  });

  it("rejects invalid limits and cookie-mode idle timeout", () => {
    vi.stubEnv("NODE_ENV", "test");
    vi.stubEnv("OIDC_SESSION_STORAGE", "cookie");
    vi.stubEnv("OIDC_SESSION_IDLE_TIMEOUT_SECONDS", "300");
    expect(() => getOidcSessionConfig()).toThrow("requires PostgreSQL");

    vi.stubEnv("OIDC_SESSION_IDLE_TIMEOUT_SECONDS", "");
    vi.stubEnv("AUTH_COOKIE_MAX_BYTES", "10000");
    expect(() => getOidcSessionConfig()).toThrow("AUTH_COOKIE_MAX_BYTES");
  });
});
