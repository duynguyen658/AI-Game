import { describe, expect, it } from "vitest";
import { shouldUseSecureCookies } from "@/lib/auth/cookie-policy";

describe("session cookie policy", () => {
  it("keeps production OIDC cookies secure", () => {
    expect(shouldUseSecureCookies("production", "oidc", false)).toBe(true);
    expect(shouldUseSecureCookies("production", "oidc", true)).toBe(true);
  });

  it("allows HTTP only for an explicitly enabled production demo", () => {
    expect(shouldUseSecureCookies("production", "demo", false)).toBe(true);
    expect(shouldUseSecureCookies("production", "demo", true)).toBe(false);
    expect(shouldUseSecureCookies("development", "demo", false)).toBe(false);
  });
});
