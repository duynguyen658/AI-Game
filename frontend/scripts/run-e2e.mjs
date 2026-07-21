import { spawn } from "node:child_process";

const port = process.env.E2E_PORT ?? "43130";
const baseURL = `http://127.0.0.1:${port}`;
const environment = {
  ...process.env,
  PORT: port,
  HOSTNAME: "127.0.0.1",
  DEMO_AUTH_ENABLED: "true",
  DEMO_SESSION_SECRET: process.env.DEMO_SESSION_SECRET ?? "playwright-session-secret-at-least-32-characters",
};
const server = spawn(process.execPath, [".next/standalone/server.js"], { env: environment, stdio: ["ignore", "pipe", "pipe"] });
server.stdout.pipe(process.stdout);
server.stderr.pipe(process.stderr);

async function waitForServer() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${baseURL}/login`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Timed out waiting for the standalone frontend server");
}

function runPlaywright() {
  const cli = "node_modules/@playwright/test/cli.js";
  const child = spawn(process.execPath, [cli, "test", ...process.argv.slice(2)], {
    env: { ...process.env, PLAYWRIGHT_EXTERNAL_SERVER: "1", PLAYWRIGHT_BASE_URL: baseURL },
    stdio: "inherit",
  });
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 1));
  });
}

let exitCode = 1;
try {
  await waitForServer();
  exitCode = await runPlaywright();
} finally {
  server.kill();
}
process.exitCode = exitCode;
