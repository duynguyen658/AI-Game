import { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import type { AuthenticatedSession } from "@/lib/auth/session";
import { closeOidcSessionPool, getOidcSessionStore, sessionIdHash } from "@/lib/auth/session-store";

const enabled = process.env.RUN_POSTGRES_OIDC_TESTS === "1";
const databaseUrl = (process.env.FRONTEND_DATABASE_URL ?? process.env.DATABASE_URL ?? "")
  .replace(/^postgresql\+asyncpg:/, "postgresql:");

function session(overrides: Partial<AuthenticatedSession> = {}): AuthenticatedSession {
  const now = Math.floor(Date.now() / 1000);
  return {
    actor: { id: "postgres-user", role: "admin", displayName: "Postgres User" },
    accessToken: "access-token-plaintext-marker",
    refreshToken: "refresh-token-plaintext-marker",
    idToken: "id-token-plaintext-marker",
    accessTokenExpiresAt: now + 60,
    sessionExpiresAt: now + 3600,
    createdAt: now,
    provider: "oidc",
    sessionVersion: 1,
    ...overrides,
  };
}

describe.skipIf(!enabled)("PostgreSQL opaque OIDC sessions", () => {
  const database = new Pool({ connectionString: databaseUrl });

  beforeAll(async () => {
    vi.stubEnv("OIDC_SESSION_STORAGE", "postgres");
    vi.stubEnv("FRONTEND_DATABASE_URL", databaseUrl);
    vi.stubEnv("OIDC_SESSION_ENCRYPTION_KEY", "postgres-integration-encryption-key-at-least-32-characters");
    vi.stubEnv("AUTH_COOKIE_MAX_BYTES", "3800");
    await database.query("DELETE FROM frontend_oidc_sessions");
  });

  afterAll(async () => {
    await database.query("DELETE FROM frontend_oidc_sessions");
    await closeOidcSessionPool();
    await database.end();
  });

  it("stores only a hash of the opaque cookie and encrypted token payload", async () => {
    const created = await getOidcSessionStore().createSession(session());
    expect(created.cookieValue).not.toContain("token");
    const row = await database.query<{ session_id_hash: string; encrypted_payload: string }>(
      "SELECT session_id_hash, encrypted_payload FROM frontend_oidc_sessions WHERE session_id_hash = $1",
      [sessionIdHash(created.cookieValue)],
    );
    expect(row.rows[0]?.session_id_hash).toBe(sessionIdHash(created.cookieValue));
    expect(row.rows[0]?.encrypted_payload).not.toContain("plaintext-marker");
  });

  it("allows one refresh claimant and rejects stale updates", async () => {
    const store = getOidcSessionStore();
    const created = await store.createSession(session());
    const claims = await Promise.all([
      store.claimRefresh(created.cookieValue, 1, "a".repeat(64)),
      store.claimRefresh(created.cookieValue, 1, "b".repeat(64)),
    ]);
    expect(claims.filter(Boolean)).toHaveLength(1);
    const owner = claims[0] ? "a".repeat(64) : "b".repeat(64);
    const refreshed = { ...created.session, accessToken: "access-token-new", sessionVersion: 2 };
    expect((await store.compareAndSwapRefresh(created.cookieValue, 1, refreshed, owner)).outcome)
      .toBe("UPDATED");
    expect((await store.compareAndSwapRefresh(created.cookieValue, 1, refreshed, owner)).outcome)
      .toBe("VERSION_CONFLICT");
  });

  it("denies revoked sessions and deletes expired records in bounded batches", async () => {
    const store = getOidcSessionStore();
    const active = await store.createSession(session());
    expect(await store.revokeSession(active.cookieValue)).toBe("UPDATED");
    expect((await store.readSession(active.cookieValue)).outcome).toBe("REVOKED");

    const old = Math.floor(Date.now() / 1000) - 3600;
    await store.createSession(session({ createdAt: old - 60, sessionExpiresAt: old }));
    expect(await store.deleteExpiredSessions(10)).toBeGreaterThanOrEqual(1);
  });
});
