import { expect, test } from "@playwright/test";

test.skip(process.env.E2E_OIDC !== "1", "deterministic OIDC stack is not enabled");

test("OIDC session refreshes after token expiry, rotates, and revokes on logout", async ({ page }) => {
  await page.goto("/api/auth/login");
  await expect(page).toHaveURL(/\/dashboard$/);

  const cookies = await page.context().cookies();
  const sessionCookie = cookies.find((cookie) => cookie.name === "cl_session");
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.value).toMatch(/^[A-Za-z0-9_-]{43}$/);

  const initial = await page.request.get("/api/backend/campaigns?limit=1");
  expect(initial.status()).toBe(200);

  await expect.poll(async () => {
    const response = await page.request.get("/api/backend/campaigns?limit=1");
    return response.status();
  }, { timeout: 10_000, intervals: [250, 500, 750] }).toBe(200);

  const issuer = process.env.TEST_OIDC_ISSUER ?? "http://127.0.0.1:43132";
  await expect.poll(async () => {
    const response = await page.request.get(`${issuer}/test/status`);
    return (await response.json()).refresh_count as number;
  }, { timeout: 10_000, intervals: [250, 500, 750] }).toBeGreaterThanOrEqual(1);

  const status = await (await page.request.get(`${issuer}/test/status`)).json();
  expect(status.rotation_count).toBe(status.refresh_count);

  await page.goto("/api/auth/logout");
  await expect(page).toHaveURL(/\/login$/);
  const afterLogout = await page.request.get("/api/backend/campaigns?limit=1");
  expect(afterLogout.status()).toBe(401);
});

test("invalid refresh grant clears authentication and returns a stable 401", async ({ page }) => {
  await page.goto("/api/auth/login");
  await expect(page).toHaveURL(/\/dashboard$/);

  const issuer = process.env.TEST_OIDC_ISSUER ?? "http://127.0.0.1:43132";
  expect((await page.request.post(`${issuer}/test/revoke-refresh`)).status()).toBe(200);

  let failureBody: { code?: string; message?: string } = {};
  await expect.poll(async () => {
    const response = await page.request.get("/api/backend/campaigns?limit=1");
    if (response.status() === 401) failureBody = await response.json();
    return response.status();
  }, { timeout: 10_000, intervals: [250, 500, 750] }).toBe(401);

  expect(failureBody).toMatchObject({
    code: "OIDC_REFRESH_INVALID_GRANT",
    message: "Your session has expired. Please sign in again.",
  });
  expect((await page.context().cookies()).find((cookie) => cookie.name === "cl_session")).toBeUndefined();
});
