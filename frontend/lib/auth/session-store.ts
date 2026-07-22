import "server-only";

import { createHash, randomBytes } from "node:crypto";
import { Pool, type PoolClient } from "pg";
import { getFrontendDatabaseUrl, getOidcSessionConfig } from "@/lib/env/server";
import { seal, unseal } from "./crypto";
import { isAuthenticatedSession, type AuthenticatedSession } from "./session";

export type SessionMutationOutcome = "CREATED" | "UPDATED" | "NOT_FOUND" | "VERSION_CONFLICT" | "EXPIRED" | "REVOKED";
export type StoredSession = { cookieValue: string; session: AuthenticatedSession };
export type SessionReadResult =
  | ({ outcome: "FOUND" } & StoredSession)
  | { outcome: "NOT_FOUND" | "EXPIRED" | "REVOKED" };

export interface OidcSessionStore {
  createSession(session: AuthenticatedSession): Promise<{ outcome: "CREATED" } & StoredSession>;
  readSession(cookieValue: string | undefined): Promise<SessionReadResult>;
  claimRefresh(cookieValue: string, expectedVersion: number, ownerHash: string): Promise<boolean>;
  compareAndSwapRefresh(
    cookieValue: string,
    expectedVersion: number,
    session: AuthenticatedSession,
    ownerHash?: string,
  ): Promise<({ outcome: "UPDATED" } & StoredSession) | { outcome: Exclude<SessionMutationOutcome, "CREATED" | "UPDATED"> }>;
  revokeSession(cookieValue: string): Promise<SessionMutationOutcome>;
  deleteExpiredSessions(limit?: number): Promise<number>;
}

export class AuthCookieSizeError extends Error {
  readonly code = "OIDC_SESSION_SIZE_REJECTED";
  constructor(readonly encodedBytes: number, readonly limit: number) {
    super("Authentication session exceeds the configured cookie limit");
  }
}

export function encodedCookieBytes(value: string) {
  return Buffer.byteLength(value, "utf8");
}

export function assertCookieSize(value: string) {
  const bytes = encodedCookieBytes(value);
  const limit = getOidcSessionConfig().cookieMaxBytes;
  if (bytes > limit) throw new AuthCookieSizeError(bytes, limit);
  return bytes;
}

export function sessionIdHash(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

function encodePayload(session: AuthenticatedSession) {
  return seal(session, "OIDC_SESSION_ENCRYPTION_KEY");
}

function decodePayload(value: string) {
  const session = unseal<AuthenticatedSession>(value, "OIDC_SESSION_ENCRYPTION_KEY");
  return isAuthenticatedSession(session) ? session : null;
}

class CookieOidcSessionStore implements OidcSessionStore {
  async createSession(session: AuthenticatedSession) {
    const cookieValue = encodePayload(session);
    assertCookieSize(cookieValue);
    return { outcome: "CREATED" as const, cookieValue, session };
  }

  async readSession(cookieValue: string | undefined): Promise<SessionReadResult> {
    if (!cookieValue) return { outcome: "NOT_FOUND" };
    const session = decodePayload(cookieValue);
    if (!session) return { outcome: "NOT_FOUND" };
    if (session.sessionExpiresAt <= Math.floor(Date.now() / 1000)) return { outcome: "EXPIRED" };
    return { outcome: "FOUND", cookieValue, session };
  }

  async claimRefresh() { return true; }

  async compareAndSwapRefresh(cookieValue: string, expectedVersion: number, session: AuthenticatedSession) {
    const current = await this.readSession(cookieValue);
    if (current.outcome !== "FOUND") return { outcome: current.outcome };
    if (current.session.sessionVersion !== expectedVersion) return { outcome: "VERSION_CONFLICT" as const };
    const updatedCookieValue = encodePayload(session);
    assertCookieSize(updatedCookieValue);
    return { outcome: "UPDATED" as const, cookieValue: updatedCookieValue, session };
  }

  async revokeSession() { return "UPDATED" as const; }
  async deleteExpiredSessions() { return 0; }
}

let pool: Pool | undefined;

function databasePool() {
  pool ??= new Pool({ connectionString: getFrontendDatabaseUrl(), max: 10, idleTimeoutMillis: 30_000 });
  return pool;
}

async function withClient<T>(operation: (client: PoolClient) => Promise<T>) {
  const client = await databasePool().connect();
  try { return await operation(client); } finally { client.release(); }
}

type SessionRow = {
  encrypted_payload: string;
  session_version: number;
  session_expires_at: Date;
  updated_at: Date;
  revoked_at: Date | null;
};

class PostgresOidcSessionStore implements OidcSessionStore {
  async createSession(session: AuthenticatedSession) {
    const cookieValue = randomBytes(32).toString("base64url");
    assertCookieSize(cookieValue);
    await withClient((client) => client.query(
      `INSERT INTO frontend_oidc_sessions
       (session_id_hash, encrypted_payload, actor_id, actor_role, access_token_expires_at,
        session_expires_at, created_at, updated_at, last_refreshed_at, session_version)
       VALUES ($1, $2, $3, $4, to_timestamp($5), to_timestamp($6), to_timestamp($7), now(), NULL, $8)`,
      [sessionIdHash(cookieValue), encodePayload(session), session.actor.id, session.actor.role,
       session.accessTokenExpiresAt, session.sessionExpiresAt, session.createdAt, session.sessionVersion],
    ));
    return { outcome: "CREATED" as const, cookieValue, session };
  }

  async readSession(cookieValue: string | undefined): Promise<SessionReadResult> {
    if (!cookieValue || encodedCookieBytes(cookieValue) > 256) return { outcome: "NOT_FOUND" };
    const result = await databasePool().query<SessionRow>(
      `SELECT encrypted_payload, session_version, session_expires_at, updated_at, revoked_at
       FROM frontend_oidc_sessions WHERE session_id_hash = $1`,
      [sessionIdHash(cookieValue)],
    );
    const row = result.rows[0];
    if (!row) return { outcome: "NOT_FOUND" };
    if (row.revoked_at) return { outcome: "REVOKED" };
    if (row.session_expires_at.getTime() <= Date.now()) return { outcome: "EXPIRED" };
    const idleTimeout = getOidcSessionConfig().idleTimeoutSeconds;
    if (idleTimeout && row.updated_at.getTime() <= Date.now() - idleTimeout * 1000) {
      return { outcome: "EXPIRED" };
    }
    const session = decodePayload(row.encrypted_payload);
    if (!session || session.sessionVersion !== row.session_version) return { outcome: "NOT_FOUND" };
    if (idleTimeout) {
      await databasePool().query(
        `UPDATE frontend_oidc_sessions SET updated_at = now()
         WHERE session_id_hash = $1 AND session_version = $2 AND revoked_at IS NULL`,
        [sessionIdHash(cookieValue), session.sessionVersion],
      );
    }
    return { outcome: "FOUND", cookieValue, session };
  }

  async claimRefresh(cookieValue: string, expectedVersion: number, ownerHash: string) {
    const result = await databasePool().query(
      `UPDATE frontend_oidc_sessions
       SET refresh_owner_hash = $1, refresh_started_at = now(), updated_at = now()
       WHERE session_id_hash = $2 AND session_version = $3 AND revoked_at IS NULL
         AND session_expires_at > now()
         AND (refresh_owner_hash IS NULL OR refresh_started_at < now() - interval '20 seconds')`,
      [ownerHash, sessionIdHash(cookieValue), expectedVersion],
    );
    return result.rowCount === 1;
  }

  async compareAndSwapRefresh(
    cookieValue: string,
    expectedVersion: number,
    session: AuthenticatedSession,
    ownerHash?: string,
  ) {
    const result = await databasePool().query<{ encrypted_payload: string }>(
      `UPDATE frontend_oidc_sessions
       SET encrypted_payload = $1, access_token_expires_at = to_timestamp($2),
           updated_at = now(), last_refreshed_at = to_timestamp($3), session_version = $4,
           refresh_owner_hash = NULL, refresh_started_at = NULL
       WHERE session_id_hash = $5 AND session_version = $6 AND revoked_at IS NULL
         AND session_expires_at > now() AND refresh_owner_hash = $7
       RETURNING encrypted_payload`,
      [encodePayload(session), session.accessTokenExpiresAt, session.refreshedAt,
       session.sessionVersion, sessionIdHash(cookieValue), expectedVersion, ownerHash],
    );
    if (result.rowCount === 1) return { outcome: "UPDATED" as const, cookieValue, session };
    const current = await this.readSession(cookieValue);
    if (current.outcome === "FOUND") return { outcome: "VERSION_CONFLICT" as const };
    return { outcome: current.outcome };
  }

  async revokeSession(cookieValue: string) {
    const result = await databasePool().query(
      `UPDATE frontend_oidc_sessions SET revoked_at = COALESCE(revoked_at, now()), updated_at = now()
       WHERE session_id_hash = $1 AND revoked_at IS NULL`,
      [sessionIdHash(cookieValue)],
    );
    return result.rowCount === 1 ? "UPDATED" : "NOT_FOUND";
  }

  async deleteExpiredSessions(limit = 500) {
    const boundedLimit = Math.max(1, Math.min(limit, 1000));
    const result = await databasePool().query(
      `DELETE FROM frontend_oidc_sessions WHERE session_id_hash IN (
         SELECT session_id_hash FROM frontend_oidc_sessions
         WHERE session_expires_at <= now() OR revoked_at < now() - interval '24 hours'
         ORDER BY session_expires_at LIMIT $1
       )`,
      [boundedLimit],
    );
    return result.rowCount ?? 0;
  }
}

let cookieStore: OidcSessionStore | undefined;
let postgresStore: OidcSessionStore | undefined;

export function getOidcSessionStore(): OidcSessionStore {
  if (getOidcSessionConfig().storage === "postgres") {
    return postgresStore ??= new PostgresOidcSessionStore();
  }
  return cookieStore ??= new CookieOidcSessionStore();
}

export async function closeOidcSessionPool() {
  if (pool) await pool.end();
  pool = undefined;
  postgresStore = undefined;
}
