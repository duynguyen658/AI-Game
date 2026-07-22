import "server-only";

import { z } from "zod";

export type AuthMode = "demo" | "oidc";
export type OidcSessionStorage = "cookie" | "postgres";

const positiveInteger = z.coerce.number().int().positive();

function boundedInteger(name: string, fallback: string, minimum: number, maximum: number) {
  const value = positiveInteger.parse(process.env[name] ?? fallback);
  if (value < minimum || value > maximum) {
    throw new Error(`${name} must be between ${minimum} and ${maximum}`);
  }
  return value;
}

export function requireServerEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export function getAuthMode(): AuthMode {
  const value = process.env.AUTH_MODE?.trim();
  if (value === "demo" || value === "oidc") return value;
  if (process.env.NODE_ENV === "production") {
    throw new Error("AUTH_MODE must be set to demo or oidc");
  }
  return "demo";
}

export function getBackendApiUrl(): string {
  const configured = process.env.BACKEND_API_URL?.trim();
  if (!configured) {
    if (process.env.NODE_ENV !== "production") {
      return "http://127.0.0.1:8000";
    }
    throw new Error("BACKEND_API_URL is required");
  }
  const url = new URL(configured);
  const explicitDemoRuntime =
    process.env.AUTH_MODE === "demo" && process.env.ALLOW_PRODUCTION_DEMO === "true";
  if (
    process.env.NODE_ENV === "production" &&
    !explicitDemoRuntime &&
    ["localhost", "127.0.0.1", "::1"].includes(url.hostname)
  ) {
    throw new Error("BACKEND_API_URL must not use localhost in production");
  }
  return url.toString();
}

export function getBodyLimits() {
  return {
    json: positiveInteger.parse(process.env.BFF_MAX_BODY_BYTES ?? "1048576"),
    upload: positiveInteger.parse(process.env.BFF_MAX_UPLOAD_BYTES ?? "5242880"),
  };
}

export function getOidcSessionConfig() {
  const sessionMaxAgeSeconds = boundedInteger(
    "OIDC_SESSION_MAX_AGE_SECONDS",
    "36000",
    process.env.NODE_ENV === "production" ? 3600 : 30,
    43200,
  );
  const refreshSkewSeconds = boundedInteger("OIDC_REFRESH_SKEW_SECONDS", "90", 1, 600);
  if (refreshSkewSeconds >= sessionMaxAgeSeconds) {
    throw new Error("OIDC_REFRESH_SKEW_SECONDS must be shorter than the session lifetime");
  }
  const idleValue = process.env.OIDC_SESSION_IDLE_TIMEOUT_SECONDS?.trim();
  const idleTimeoutSeconds = idleValue
    ? boundedInteger("OIDC_SESSION_IDLE_TIMEOUT_SECONDS", idleValue, 60, sessionMaxAgeSeconds)
    : undefined;
  const cookieMaxBytes = boundedInteger("AUTH_COOKIE_MAX_BYTES", "3800", 512, 4096);
  const configuredStorage = process.env.OIDC_SESSION_STORAGE?.trim();
  const storage: OidcSessionStorage = configuredStorage
    ? z.enum(["cookie", "postgres"]).parse(configuredStorage)
    : process.env.NODE_ENV === "production" ? "postgres" : "cookie";
  if (idleTimeoutSeconds && storage !== "postgres") {
    throw new Error("OIDC_SESSION_IDLE_TIMEOUT_SECONDS requires PostgreSQL session storage");
  }
  const testIssuerEnabled = process.env.OIDC_TEST_ISSUER_ENABLED === "true";
  if (process.env.NODE_ENV === "production" && testIssuerEnabled) {
    throw new Error("OIDC_TEST_ISSUER_ENABLED must be false in production");
  }
  return {
    sessionMaxAgeSeconds,
    refreshSkewSeconds,
    idleTimeoutSeconds,
    cookieMaxBytes,
    storage,
    testIssuerEnabled,
  };
}

export function getFrontendDatabaseUrl() {
  const value = process.env.FRONTEND_DATABASE_URL ?? process.env.DATABASE_URL;
  if (!value?.trim()) throw new Error("FRONTEND_DATABASE_URL is required for PostgreSQL OIDC sessions");
  return value.trim().replace(/^postgresql\+asyncpg:/, "postgresql:");
}

export function validateServerEnv() {
  getBackendApiUrl();
  const mode = getAuthMode();
  requireServerEnv("SESSION_SECRET");
  if (mode === "demo") {
    if (process.env.DEMO_AUTH_ENABLED !== "true") {
      throw new Error("DEMO_AUTH_ENABLED=true is required in demo mode");
    }
    if (process.env.NODE_ENV === "production" && process.env.ALLOW_PRODUCTION_DEMO !== "true") {
      throw new Error("Demo authentication is disabled for production deployments");
    }
  } else {
    requireServerEnv("OIDC_ISSUER");
    requireServerEnv("OIDC_CLIENT_ID");
    requireServerEnv("OIDC_CLIENT_SECRET");
    requireServerEnv("OIDC_REDIRECT_URI");
    const session = getOidcSessionConfig();
    const encryptionKey = requireServerEnv("OIDC_SESSION_ENCRYPTION_KEY");
    if (encryptionKey.length < 32) {
      throw new Error("OIDC_SESSION_ENCRYPTION_KEY must be at least 32 characters");
    }
    if (session.storage === "postgres") getFrontendDatabaseUrl();
  }
  getBodyLimits();
  return mode;
}
