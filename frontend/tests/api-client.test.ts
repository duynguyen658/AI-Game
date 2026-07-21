import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { apiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { server } from "./support/server";

describe("apiRequest", () => {
  it("returns typed JSON through the BFF path", async () => {
    server.use(http.get("*/api/backend/health", () => HttpResponse.json({ status: "healthy" })));
    await expect(apiRequest<{ status: string }>("/health")).resolves.toEqual({ status: "healthy" });
  });

  it("normalizes safe backend errors and correlation IDs", async () => {
    server.use(http.get("*/api/backend/jobs", () => HttpResponse.json({ error: { code: "FORBIDDEN", message: "Insufficient role" } }, { status: 403, headers: { "x-correlation-id": "test-correlation" } })));
    const error = await apiRequest("/jobs").catch((value) => value);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "FORBIDDEN", message: "Insufficient role", correlationId: "test-correlation" });
  });
});
