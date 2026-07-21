import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const impact = { completed_tasks: 12, total_minutes_saved: "284.5", average_automation_rate: "0.72", technical_success_rate: "0.92", human_acceptance_rate: "0.81", first_pass_acceptance_rate: "0.68", revision_rate: "0.19", error_rate: "0.08", user_satisfaction: "4.3", would_use_again_rate: "0.86", total_estimated_cost: "7.42", series: [] };
const summary = { application_version: "m8-demo", jobs: { RUNNING: 2, SUCCEEDED: 31 }, alerts: { OPEN: 1 }, workflows: { COMPLETED: 12 }, actions: {}, evaluations: {}, outbox: { PUBLISHED: 40 }, fresh_workers: 1, generated_at: "2026-07-21T00:00:00Z" };

async function mockBackend(page: Page) {
  await page.route("**/api/backend/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const body = path.endsWith("/analytics/business-impact") ? impact : path.endsWith("/operations/summary") ? summary : [];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("authentication creates an HttpOnly session and opens the workspace", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const cookie = (await page.context().cookies()).find((item) => item.name === "cl_demo_session");
  expect(cookie?.httpOnly).toBe(true);
});

test("dashboard has no serious accessibility violations", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.getByText("Impact summary")).toBeVisible({ timeout: 30000 });
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
});

test("core routes remain usable when a backend surface is empty", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
  for (const path of ["/campaigns", "/data-analysis", "/documents", "/media", "/prompts", "/prompt-experiments", "/provider-comparisons", "/approvals", "/operations/jobs", "/operations/alerts"]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
  }
});

test("permission-aware routes redirect marketing users", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
  await page.goto("/operations/jobs");
  await expect(page).toHaveURL(/\/forbidden$/);
  await expect(page.getByRole("heading", { name: "Access is not available" })).toBeVisible();
});
