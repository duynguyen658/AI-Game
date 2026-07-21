import { describe, expect, it } from "vitest";
import { buildUpstreamHeaders } from "@/lib/bff/headers";

const browserHeaders = new Headers({
  accept: "application/json",
  authorization: "Bearer browser-controlled-token",
  cookie: "provider-key=secret",
  "content-type": "application/json",
  "x-actor-id": "attacker",
  "x-actor-role": "admin",
  "x-forwarded-for": "203.0.113.4",
});

describe("BFF upstream header policy", () => {
  it("uses trusted demo identity and strips browser credentials", () => {
    const headers = buildUpstreamHeaders(browserHeaders, "correlation-1", {
      mode: "demo",
      actorId: "trusted-demo-user",
      role: "marketing",
    });
    expect(headers.get("x-actor-id")).toBe("trusted-demo-user");
    expect(headers.get("x-actor-role")).toBe("marketing");
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("x-forwarded-for")).toBeNull();
  });

  it("forwards only server-side Bearer identity in OIDC mode", () => {
    const headers = buildUpstreamHeaders(browserHeaders, "correlation-2", {
      mode: "oidc",
      accessToken: "server-side-token",
    });
    expect(headers.get("authorization")).toBe("Bearer server-side-token");
    expect(headers.get("x-actor-id")).toBeNull();
    expect(headers.get("x-actor-role")).toBeNull();
    expect(headers.get("x-correlation-id")).toBe("correlation-2");
  });
});
