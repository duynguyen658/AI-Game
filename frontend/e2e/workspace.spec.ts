import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const impact = { completed_tasks: 12, total_minutes_saved: "284.5", average_automation_rate: "0.72", technical_success_rate: "0.92", human_acceptance_rate: "0.81", first_pass_acceptance_rate: "0.68", revision_rate: "0.19", error_rate: "0.08", user_satisfaction: "4.3", would_use_again_rate: "0.86", total_estimated_cost: "7.42", series: [] };
const summary = { application_version: "m8-demo", jobs: { RUNNING: 2, SUCCEEDED: 31 }, alerts: { OPEN: 1 }, workflows: { COMPLETED: 12 }, actions: {}, evaluations: {}, outbox: { PUBLISHED: 40 }, fresh_workers: 1, generated_at: "2026-07-21T00:00:00Z" };
const ids = {
  workflow: "11111111-1111-4111-8111-111111111111",
  job: "22222222-2222-4222-8222-222222222222",
  task: "33333333-3333-4333-8333-333333333333",
  media: "44444444-4444-4444-8444-444444444444",
  experiment: "55555555-5555-4555-8555-555555555555",
  template: "66666666-6666-4666-8666-666666666666",
  control: "77777777-7777-4777-8777-777777777777",
  candidate: "88888888-8888-4888-8888-888888888888",
  dataset: "99999999-9999-4999-8999-999999999999",
};

const task = { task_run_id: ids.task, workflow_type: "DATA_ANALYSIS", status: "COMPLETED", input_metadata: {}, result: {}, provider: "mock", model: "mock-applied-ai", job_id: ids.job, workflow_id: null, prompt_template_id: ids.template, prompt_version_id: ids.control, prompt_version_number: 1, prompt_content_hash: "fixture", model_configuration_hash: "fixture", application_version: "1.0.0-rc.1", duration_ms: 850, estimated_cost: "0.01", created_by: "visual-manager", error_code: null, error_message: null, created_at: "2026-07-21T00:00:00Z", started_at: "2026-07-21T00:00:01Z", completed_at: "2026-07-21T00:00:02Z" };
const job = { job_id: ids.job, job_type: "DATA_ANALYSIS", status: "SUCCEEDED", priority: 100, payload: { task_run_id: ids.task }, created_by: "visual-manager", idempotency_key: "visual-job", correlation_id: "visual-correlation", attempt_count: 1, max_attempts: 3, available_at: "2026-07-21T00:00:00Z", locked_by: null, locked_at: null, lease_expires_at: null, heartbeat_at: null, cancel_requested_at: null, started_at: "2026-07-21T00:00:01Z", completed_at: "2026-07-21T00:00:02Z", result: { completed: true }, error_code: null, error_message: null, version: 2, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:02Z" };

async function mockBackend(page: Page) {
  await page.route("**/api/backend/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith("/analytics/business-impact")) body = impact;
    else if (path.endsWith("/operations/summary")) body = summary;
    else if (path.endsWith("/campaigns/CL-VISUAL-001")) body = { campaign: { campaign_id: "CL-VISUAL-001", game_name: "Cyber Legends", genre: "Action RPG", target_audience: "Core players aged 18-30", market: "Vietnam", platforms: ["Facebook", "TikTok"], campaign_objective: "Drive launch registrations", tone: "Confident cyberpunk action", launch_date: "2026-08-15", promotion: "Limited launch reward", raw_brief: "Deterministic visual campaign" }, status: "PENDING_APPROVAL", version: 4, retry_count: 0, analysis: { summary: "A focused launch campaign for action RPG players.", main_message: "Register early for limited rewards.", risk_flags: [] }, generated_content: null, quality_review: null, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:02Z" };
    else if (path.endsWith(`/workflows/${ids.workflow}`)) body = { workflow_id: ids.workflow, campaign_id: "CL-VISUAL-001", status: "PENDING_APPROVAL", current_step: "HUMAN_REVIEW", state: {}, current_agent: null, llm_call_count: 3, retry_count: 0, version: 4, started_at: "2026-07-21T00:00:00Z", completed_at: "2026-07-21T00:00:02Z", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:02Z" };
    else if (path.endsWith(`/jobs/${ids.job}/status`)) body = { job_id: ids.job, job_type: "DATA_ANALYSIS", status: "SUCCEEDED", correlation_id: "visual-correlation", attempt_count: 1, max_attempts: 3, cancel_requested: false, result: { completed: true }, error_code: null, error_message: null, created_at: "2026-07-21T00:00:00Z", started_at: "2026-07-21T00:00:01Z", completed_at: "2026-07-21T00:00:02Z", updated_at: "2026-07-21T00:00:02Z" };
    else if (path.includes("/operations/workflows/")) body = [{ event_id: "visual-event", event_type: "WORKFLOW_COMPLETED", resource_type: "workflow", resource_id: ids.workflow, status: "PENDING_APPROVAL", summary: "Content generation completed", metadata: {}, correlation_id: null, occurred_at: "2026-07-21T00:00:02Z" }];
    else if (path.endsWith(`/data-analysis/tasks/${ids.task}/report`)) body = { summary_metrics: { impressions: 120000, clicks: 8400, ctr: "0.07", conversions: 920 }, data_quality: { row_count: 24, missing_value_rate: "0.00", duplicate_row_count: 0 }, explanation: "Launch engagement is healthy and conversion quality remains consistent across channels.", recommendations: ["Increase spend on the highest-converting audience."], limitations: ["The fixture covers one launch window."], anomalies: [] };
    else if (path.endsWith(`/data-analysis/tasks/${ids.task}`) || path.endsWith(`/document-processing/tasks/${ids.task}`)) body = task;
    else if (path.endsWith(`/document-processing/tasks/${ids.task}/result`)) body = { document_type: "MARKETING_BRIEF", confidence: 0.94, executive_summary: "Cyber Legends launches with a focused pre-registration objective and clear ownership.", page_count: 3, character_count: 1840, inconsistencies: [], prompt_injection_warning: false, key_points: ["Launch date is August 15", "Core audience is action RPG players"], action_items: ["Finalize localized calls to action"] };
    else if (path.endsWith(`/media/assets/${ids.media}`)) body = { media_asset_id: ids.media, campaign_id: null, workflow_id: null, task_run_id: ids.task, task_type: "campaign_image", asset_type: "IMAGE", status: "READY_FOR_REVIEW", provider: "mock", model: "mock-image-v1", prompt_version_id: ids.control, prompt_template_id: ids.template, prompt_version_number: 1, prompt_content_hash: "fixture", model_configuration_hash: "fixture", application_version: "1.0.0-rc.1", generation_prompt: "Cyber Legends heroes preparing for a competitive seasonal launch.", negative_prompt: "No text or watermark", storage_uri: null, thumbnail_uri: null, mime_type: "image/png", width: 1024, height: 1024, duration_seconds: null, estimated_cost: "0.02", safety_status: "SAFE", created_by: "visual-manager", created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:02Z", approved_by: null, approved_at: null, rejected_by: null, rejected_at: null, rejection_reason: null, error_code: null, error_message: null, completed_at: "2026-07-21T00:00:02Z" };
    else if (path.endsWith(`/prompt-experiments/${ids.experiment}/results`)) body = [{ case_result_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", evaluation_case_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", prompt_version_id: ids.control, variant: "control", status: "COMPLETED", output: { response: "safe" }, metrics: { quality_score: 0.91 }, error_code: null, error_message: null, created_at: "2026-07-21T00:00:02Z" }];
    else if (path.endsWith(`/prompt-experiments/${ids.experiment}`)) body = { prompt_template_id: ids.template, control_version_id: ids.control, candidate_version_id: ids.candidate, evaluation_dataset_id: ids.dataset, provider: "mock", model: "mock-applied-ai", sample_size: 1, execution_settings: {}, experiment_id: ids.experiment, status: "COMPLETED", job_id: ids.job, dataset_version: "visual-1", model_configuration_hash: "fixture", tool_registry_version: "1", policy_version: "1", application_version: "1.0.0-rc.1", error_code: null, error_message: null, created_by: "visual-manager", started_at: "2026-07-21T00:00:00Z", completed_at: "2026-07-21T00:00:02Z", created_at: "2026-07-21T00:00:00Z", result: { winner: "candidate", decision_reason: "Higher backend quality score" } };
    else if (path.endsWith("/jobs")) body = [job];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function expectNoSeriousAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? "")),
  ).toEqual([]);
}

test("authentication creates an HttpOnly session and opens the workspace", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const cookie = (await page.context().cookies()).find((item) => item.name === "cl_session");
  expect(cookie?.httpOnly).toBe(true);
});

test("dashboard has no serious accessibility violations", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/login");
  await expectNoSeriousAxeViolations(page);
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page.getByText("Impact summary")).toBeVisible({ timeout: 30000 });
  await expectNoSeriousAxeViolations(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
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
    await expectNoSeriousAxeViolations(page);
  }
});

test("primary product visual baselines remain stable", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "desktop visual baseline");
  await mockBackend(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  await expect(page).toHaveScreenshot("login.png", { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.03 });
  await page.getByLabel("Role").selectOption("manager");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  const pages = [
    ["/dashboard", "dashboard.png", "Dashboard"],
    [`/campaigns/CL-VISUAL-001?workflow=${ids.workflow}&job=${ids.job}`, "campaign-detail.png", "Cyber Legends"],
    [`/data-analysis/${ids.task}`, "csv-report.png", "Data analysis report"],
    [`/documents/${ids.task}`, "document-report.png", "Document result"],
    [`/media/assets/${ids.media}`, "media-detail.png", "Media asset"],
    [`/prompt-experiments/${ids.experiment}`, "prompt-experiment.png", "Prompt experiment"],
    ["/analytics/business-impact", "business-impact.png", "Business impact"],
    ["/operations/jobs", "jobs.png", "Jobs console"],
  ] as const;
  for (const [path, snapshot, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 30000 });
    await expectNoSeriousAxeViolations(page);
    await expect(page).toHaveScreenshot(snapshot, { animations: "disabled", fullPage: true, maxDiffPixelRatio: 0.03 });
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
