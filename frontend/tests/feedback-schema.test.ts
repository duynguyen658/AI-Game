import { describe, expect, it } from "vitest";
import { feedbackSchema } from "@/components/forms/feedback-form";

const base = { output_accepted: "yes" as const, accepted_without_editing: false, editing_minutes: 2, rework_count: 0, rating: 4, helpfulness: 4, accuracy: 4, ease_of_use: 4, would_use_again: true };

describe("feedbackSchema", () => {
  it("accepts ordinary edited feedback", () => expect(feedbackSchema.safeParse(base).success).toBe(true));
  it("enforces accepted-without-editing invariants", () => expect(feedbackSchema.safeParse({ ...base, output_accepted: "no", accepted_without_editing: true }).success).toBe(false));
});
