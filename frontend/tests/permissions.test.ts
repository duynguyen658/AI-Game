import { describe, expect, it } from "vitest";
import { canAccessPath } from "@/lib/auth/permissions";

describe("canAccessPath", () => {
  it("keeps operator surfaces unavailable to marketing", () => {
    expect(canAccessPath("marketing", "/operations/jobs")).toBe(false);
    expect(canAccessPath("marketing", "/provider-comparisons/new")).toBe(false);
  });
  it("allows reviewers to govern prompts but not operate jobs", () => {
    expect(canAccessPath("reviewer", "/prompts/template-1")).toBe(true);
    expect(canAccessPath("reviewer", "/operations/jobs")).toBe(false);
  });
  it("allows managers to access operational routes", () => expect(canAccessPath("manager", "/operations/health")).toBe(true));
});
