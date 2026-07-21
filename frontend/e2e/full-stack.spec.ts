import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIResponse, type Browser, type Page } from "@playwright/test";

test.skip(process.env.E2E_FULL_STACK !== "1", "requires docker-compose.demo.yml");

const campaignPayload = (campaignId: string) => ({
  campaign_id: campaignId,
  game_name: "Cyber Legends",
  genre: "Action RPG",
  target_audience: "18-30",
  market: "Vietnam",
  platforms: ["Facebook", "TikTok"],
  campaign_objective: "Drive launch registrations",
  tone: "Confident cyberpunk action",
  launch_date: "2026-08-15",
  promotion: "Launch reward",
  raw_brief: "Deterministic M8 full-stack campaign",
});

async function login(page: Page, actorId: string, role: "marketing" | "reviewer" | "manager") {
  await page.goto("/login");
  await page.getByLabel("Display name").fill(actorId);
  await page.getByLabel("Demo actor ID").fill(actorId);
  await page.getByLabel("Role").selectOption(role);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

async function loginContext(browser: Browser, actorId: string, role: "marketing" | "reviewer" | "manager") {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, actorId, role);
  return { context, page };
}

async function responseJson(response: APIResponse, status: number) {
  const body = await response.text();
  expect(response.status(), body).toBe(status);
  return JSON.parse(body) as Record<string, unknown>;
}

async function pollJob(page: Page, jobId: string) {
  let finalStatus = "";
  await expect.poll(async () => {
    const response = await page.request.get(`/api/backend/jobs/${jobId}/status`);
    if (!response.ok()) return response.status().toString();
    finalStatus = (await response.json()).status as string;
    return finalStatus;
  }, { timeout: 90_000, intervals: [500, 1000, 2000] }).toMatch(/SUCCEEDED|FAILED|DEAD_LETTER/);
  return finalStatus;
}

async function pollMedia(page: Page, assetId: string) {
  let finalStatus = "";
  await expect.poll(async () => {
    const response = await page.request.get(`/api/backend/media/assets/${assetId}`);
    if (!response.ok()) return response.status().toString();
    finalStatus = (await response.json()).status as string;
    return finalStatus;
  }, { timeout: 90_000, intervals: [500, 1000, 2000] }).toMatch(
    /READY_FOR_REVIEW|APPROVED|REJECTED|FAILED|CANCELLED/,
  );
  return finalStatus;
}

async function createEvaluationFixture(page: Page) {
  const stamp = Date.now().toString(36);
  const template = await responseJson(await page.request.post("/api/backend/prompt-templates", {
    data: {
      name: `M8 E2E ${stamp}`,
      slug: `m8-e2e-${stamp}`,
      agent_name: "BRIEF_ANALYST",
      task_type: "m8_e2e",
      description: "Deterministic full-stack prompt fixture",
      input_schema: { type: "object" },
      output_schema: { type: "object" },
    },
  }), 201);
  const templateId = template.prompt_template_id as string;
  const versionPayload = (label: string) => ({
    system_prompt: `Return a safe deterministic result for ${label}.`,
    user_prompt_template: "Campaign context: {context}",
    variables: { context: { type: "string" } },
    change_summary: `${label} fixture`,
    model_requirements: { structured_output: true },
  });
  const control = await responseJson(await page.request.post(
    `/api/backend/prompt-templates/${templateId}/versions`,
    { data: versionPayload("control") },
  ), 201);
  const candidate = await responseJson(await page.request.post(
    `/api/backend/prompt-templates/${templateId}/versions`,
    { data: versionPayload("candidate") },
  ), 201);
  const dataset = await responseJson(await page.request.post("/api/backend/evaluations/datasets", {
    data: {
      name: `M8 E2E ${stamp}`,
      version: stamp,
      description: "Deterministic browser fixture",
      cases: [{
        name: "safe launch case",
        campaign_input: { context: "Cyber Legends launch" },
        actual_output: null,
        system_config: {},
        expected: { response: "safe" },
        thresholds: {},
        enabled: true,
      }],
    },
  }), 201);
  return {
    templateId,
    controlVersionId: control.prompt_version_id as string,
    candidateVersionId: candidate.prompt_version_id as string,
    datasetId: dataset.dataset_id as string,
  };
}

async function createAndCompleteImage(page: Page, label: string) {
  const asset = await responseJson(await page.request.post("/api/backend/media/images", {
    headers: { "x-idempotency-key": `m8-e2e-${label}-${Date.now()}` },
    data: {
      campaign_id: null,
      workflow_id: null,
      task_type: "campaign_image",
      prompt: `Safe Cyber Legends campaign image for ${label}`,
      negative_prompt: "No text or watermark",
      width: 512,
      height: 512,
    },
  }), 202);
  const assetId = asset.media_asset_id as string;
  expect(await pollMedia(page, assetId)).toBe("READY_FOR_REVIEW");
  return assetId;
}

test("real BFF connects to API and enforces campaign resource isolation", async ({ browser }) => {
  const userA = await loginContext(browser, "e2e-user-a", "marketing");
  const live = await userA.page.request.get("/api/backend/live");
  expect(live.status()).toBe(200);
  expect((await live.json()).status).toBe("alive");

  const campaignId = `CL-E2E-${Date.now()}`;
  const campaign = await userA.page.request.post("/api/backend/campaigns", {
    data: campaignPayload(campaignId),
  });
  expect(campaign.status()).toBe(201);
  const workflow = await userA.page.request.post(
    `/api/backend/workflows/campaigns/${campaignId}`,
  );
  expect(workflow.status()).toBe(201);
  const workflowId = (await workflow.json()).workflow_id as string;
  const queued = await userA.page.request.post(`/api/backend/workflows/${workflowId}/run`);
  expect(queued.status()).toBe(202);
  const jobId = (await queued.json()).job_id as string;
  await pollJob(userA.page, jobId);

  const userB = await loginContext(browser, "e2e-user-b", "marketing");
  for (const path of [
    `/campaigns/${campaignId}`,
    `/workflows/${workflowId}`,
    `/jobs/${jobId}/status`,
    `/operations/campaigns/${campaignId}/timeline`,
  ]) {
    expect((await userB.page.request.get(`/api/backend${path}`)).status()).toBe(403);
  }
  const manager = await loginContext(browser, "e2e-manager", "manager");
  expect((await manager.page.request.get(`/api/backend/campaigns/${campaignId}`)).status()).toBe(200);
  expect((await manager.page.request.get(`/api/backend/jobs/${jobId}`)).status()).toBe(200);
  const completedWorkflow = await responseJson(await manager.page.request.get(
    `/api/backend/workflows/${workflowId}`,
  ), 200);
  const approval = await responseJson(await manager.page.request.post("/api/backend/approvals", {
    data: {
      campaign_id: campaignId,
      workflow_id: workflowId,
      decision: "APPROVE",
      feedback: "Approved by deterministic M8 E2E",
      expected_version: completedWorkflow.version as number,
    },
  }), 201);
  expect(approval.decision).toBe("APPROVE");

  await manager.page.goto("/operations/jobs");
  await expect(manager.page.locator("main h1")).toBeVisible();
  const accessibility = await new AxeBuilder({ page: manager.page }).analyze();
  expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);

  await Promise.all([userA.context.close(), userB.context.close(), manager.context.close()]);
});

test("real BFF streams bounded CSV and document uploads", async ({ page }) => {
  await login(page, "e2e-upload-user", "marketing");
  const csv = await page.request.post("/api/backend/data-analysis/tasks", {
    multipart: { file: { name: "metrics.csv", mimeType: "text/csv", buffer: Buffer.from("name,value\nalpha,4\nbeta,7\n") } },
  });
  expect(csv.status()).toBe(202);
  const csvTask = await csv.json();
  await pollJob(page, csvTask.job_id);
  expect((await page.request.get(`/api/backend/data-analysis/tasks/${csvTask.task_run_id}`)).status()).toBe(200);
  expect((await page.request.post(`/api/backend/task-runs/${csvTask.task_run_id}/feedback`, {
    data: {
      rating: 5,
      helpfulness: 5,
      accuracy: 5,
      ease_of_use: 5,
      would_use_again: true,
      output_accepted: true,
      accepted_without_editing: true,
      editing_minutes: 0,
      rework_count: 0,
      comment: "Deterministic E2E feedback",
    },
  })).status()).toBe(200);

  const document = await page.request.post("/api/backend/document-processing/tasks", {
    multipart: { file: { name: "brief.txt", mimeType: "text/plain", buffer: Buffer.from("Cyber Legends launch brief with one clear objective.") } },
  });
  expect(document.status()).toBe(202);
  const documentTask = await document.json();
  await pollJob(page, documentTask.job_id);
  expect((await page.request.get(`/api/backend/document-processing/tasks/${documentTask.task_run_id}/result`)).status()).toBe(200);
});

test("real prompt experiment and provider comparison persist worker results", async ({ browser }) => {
  const manager = await loginContext(browser, "e2e-ai-manager", "manager");
  const fixture = await createEvaluationFixture(manager.page);
  const experiment = await responseJson(await manager.page.request.post("/api/backend/prompt-experiments", {
    data: {
      prompt_template_id: fixture.templateId,
      control_version_id: fixture.controlVersionId,
      candidate_version_id: fixture.candidateVersionId,
      evaluation_dataset_id: fixture.datasetId,
      provider: "mock",
      model: "mock-applied-ai",
      sample_size: 1,
      execution_settings: {},
    },
  }), 201);
  const experimentId = experiment.experiment_id as string;
  const runningExperiment = await responseJson(await manager.page.request.post(
    `/api/backend/prompt-experiments/${experimentId}/run`, { data: {} },
  ), 202);
  await pollJob(manager.page, runningExperiment.job_id as string);
  const completedExperiment = await responseJson(await manager.page.request.get(
    `/api/backend/prompt-experiments/${experimentId}`,
  ), 200);
  expect(completedExperiment.status).toBe("COMPLETED");
  const experimentResults = await manager.page.request.get(
    `/api/backend/prompt-experiments/${experimentId}/results`,
  );
  expect((await experimentResults.json()).length).toBe(2);

  const comparison = await responseJson(await manager.page.request.post("/api/backend/provider-comparisons", {
    data: {
      prompt_version_id: fixture.controlVersionId,
      dataset_id: fixture.datasetId,
      providers: ["mock", "gemini"],
      model_by_provider: { mock: "mock-applied-ai", gemini: "demo-failure" },
      sample_size: 1,
      execution_settings: {},
    },
  }), 201);
  const comparisonId = comparison.comparison_id as string;
  const runningComparison = await responseJson(await manager.page.request.post(
    `/api/backend/provider-comparisons/${comparisonId}/run`, { data: {} },
  ), 202);
  await pollJob(manager.page, runningComparison.job_id as string);
  const completedComparison = await responseJson(await manager.page.request.get(
    `/api/backend/provider-comparisons/${comparisonId}`,
  ), 200);
  expect(completedComparison.status).toBe("COMPLETED");
  const comparisonResults = await manager.page.request.get(
    `/api/backend/provider-comparisons/${comparisonId}/results`,
  );
  expect(new Set((await comparisonResults.json()).map((row: { status: string }) => row.status))).toEqual(
    new Set(["COMPLETED", "FAILED"]),
  );
  await manager.page.goto(`/prompt-experiments/${experimentId}`);
  await expect(manager.page.locator("main h1")).toBeVisible();
  await manager.page.goto(`/provider-comparisons/${comparisonId}`);
  await expect(manager.page.locator("main h1")).toBeVisible();
  await manager.context.close();
});

test("real media workflows support approve reject storyboard and IDOR", async ({ browser }) => {
  const manager = await loginContext(browser, "e2e-media-manager", "manager");
  const approvedId = await createAndCompleteImage(manager.page, "approve");
  const approved = await responseJson(await manager.page.request.post(
    `/api/backend/media/assets/${approvedId}/approve`,
    { data: { decision: "APPROVE", rating: 5, comment: "Approved in E2E" } },
  ), 200);
  expect(approved.status).toBe("APPROVED");

  const rejectedId = await createAndCompleteImage(manager.page, "reject");
  const rejected = await responseJson(await manager.page.request.post(
    `/api/backend/media/assets/${rejectedId}/reject`,
    { data: { decision: "REJECT", rating: 2, comment: "Rejected in E2E" } },
  ), 200);
  expect(rejected.status).toBe("REJECTED");

  const storyboardAsset = await responseJson(await manager.page.request.post(
    "/api/backend/media/video-storyboards",
    { data: {
      campaign_id: null,
      campaign_brief: "Cyber Legends launch for core action RPG players",
      objective: "Drive pre-registration",
      target_duration_seconds: 30,
      aspect_ratio: "16:9",
    } },
  ), 202);
  const storyboardId = storyboardAsset.media_asset_id as string;
  expect(await pollMedia(manager.page, storyboardId)).toBe("READY_FOR_REVIEW");
  const storyboard = await responseJson(await manager.page.request.get(
    `/api/backend/media/video-storyboards/${storyboardId}`,
  ), 200);
  expect((storyboard.scenes as unknown[]).length).toBeGreaterThan(0);

  const outsider = await loginContext(browser, "e2e-media-outsider", "marketing");
  expect((await outsider.page.request.get(`/api/backend/media/assets/${approvedId}`)).status()).toBe(403);
  expect((await outsider.page.request.get(`/api/backend/media/video-storyboards/${storyboardId}`)).status()).toBe(403);
  await manager.page.goto(`/media/assets/${approvedId}`);
  await expect(manager.page.locator("main h1")).toBeVisible();
  await manager.page.goto(`/media/storyboards/${storyboardId}`);
  await expect(manager.page.locator("main h1")).toBeVisible();
  await Promise.all([manager.context.close(), outsider.context.close()]);
});

test("real operator retries a failed job and acknowledges its alert", async ({ browser }) => {
  const manager = await loginContext(browser, "e2e-operator-manager", "manager");
  const fixture = await createEvaluationFixture(manager.page);
  const experiment = await responseJson(await manager.page.request.post("/api/backend/prompt-experiments", {
    data: {
      prompt_template_id: fixture.templateId,
      control_version_id: fixture.controlVersionId,
      candidate_version_id: fixture.candidateVersionId,
      evaluation_dataset_id: fixture.datasetId,
      provider: "gemini",
      model: "demo-failure",
      sample_size: 1,
      execution_settings: {},
    },
  }), 201);
  const running = await responseJson(await manager.page.request.post(
    `/api/backend/prompt-experiments/${experiment.experiment_id as string}/run`, { data: {} },
  ), 202);
  const jobId = running.job_id as string;
  expect(await pollJob(manager.page, jobId)).toBe("DEAD_LETTER");
  const before = await responseJson(await manager.page.request.get(`/api/backend/jobs/${jobId}`), 200);
  await responseJson(await manager.page.request.post(`/api/backend/jobs/${jobId}/retry`), 200);
  expect(await pollJob(manager.page, jobId)).toBe("DEAD_LETTER");
  const after = await responseJson(await manager.page.request.get(`/api/backend/jobs/${jobId}`), 200);
  expect(after.attempt_count as number).toBeGreaterThan(before.attempt_count as number);

  await responseJson(await manager.page.request.post("/api/backend/operations/alerts/reconcile"), 200);
  const alerts = await manager.page.request.get("/api/backend/alerts?limit=100");
  const alert = (await alerts.json() as Array<Record<string, unknown>>).find(
    (item) => item.resource_type === "job" && item.resource_id === jobId,
  );
  expect(alert).toBeTruthy();
  const acknowledged = await responseJson(await manager.page.request.post(
    `/api/backend/alerts/${alert?.alert_id as string}/acknowledge`,
  ), 200);
  expect(acknowledged.status).toBe("ACKNOWLEDGED");
  expect((await manager.page.request.get("/api/backend/health")).status()).toBe(200);
  expect((await manager.page.request.get("/api/backend/analytics/business-impact")).status()).toBe(200);
  await manager.page.goto("/operations/jobs");
  await expect(manager.page.locator("main h1")).toBeVisible();
  await manager.page.goto("/analytics/business-impact");
  await expect(manager.page.locator("main h1")).toBeVisible();
  await manager.context.close();
});
