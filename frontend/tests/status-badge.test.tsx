import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/data-display/status-badge";

describe("StatusBadge", () => {
  it("renders explicit text in addition to status color", () => {
    render(<StatusBadge status="PENDING_APPROVAL" />);
    expect(screen.getByText("PENDING APPROVAL")).toBeVisible();
  });
});
