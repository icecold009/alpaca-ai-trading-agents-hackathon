import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const python = process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const e2eStateDirectory = join(tmpdir(), `riskcourt-e2e-${process.pid}`);

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5206",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: [
    {
      command: `"${python}" -m tests.fixtures.e2e_server`,
      cwd: "../backend",
      url: "http://127.0.0.1:8000/healthz",
      timeout: 30_000,
      reuseExistingServer: false,
      env: { RISKCOURT_E2E_STATE_DIR: e2eStateDirectory },
    },
    {
      command:
        "node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5206 --strictPort",
      url: "http://127.0.0.1:5206",
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
