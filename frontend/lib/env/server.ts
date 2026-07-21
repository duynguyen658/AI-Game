import "server-only";

import { z } from "zod";

export type AuthMode = "demo" | "oidc";

const positiveInteger = z.coerce.number().int().positive();

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
  }
  getBodyLimits();
  return mode;
}
