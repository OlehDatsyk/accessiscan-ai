/**
 * End-to-end tests: the real FastAPI backend (fresh SQLite DB, embedded scan worker), a local fixture
 * website with known accessibility defects, and the production frontend build served by `vite preview`.
 * No external website is contacted.
 */
import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const isWin = process.platform === "win32";
const python = process.env.E2E_PYTHON ?? path.join("..", "backend", ".venv", isWin ? "Scripts/python.exe" : "bin/python");
const backendPython = process.env.E2E_PYTHON ?? path.join(".venv", isWin ? "Scripts/python.exe" : "bin/python");
const dbFile = path.join(os.tmpdir(), `accessiscan-e2e-${Date.now()}.db`).replace(/\\/g, "/");
const FIXTURE_PORT = 8765;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /responsive\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /responsive\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `"${python}" -m http.server ${FIXTURE_PORT} --bind 127.0.0.1 --directory ../backend/tests/fixtures_site`,
      url: `http://127.0.0.1:${FIXTURE_PORT}/accessible.html`,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `"${backendPython}" -m alembic upgrade head && "${backendPython}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: "../backend",
      url: "http://127.0.0.1:8001/health/ready",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ENVIRONMENT: "development",
        DATABASE_URL: `sqlite:///${dbFile}`,
        SECRET_KEY: "e2e-only-secret-key-0123456789-abcdefghijklmnop",
        SCANNER_ALLOW_HOSTS: `127.0.0.1:${FIXTURE_PORT}`,
        RUN_EMBEDDED_WORKER: "true",
        WORKER_POLL_SECONDS: "0.5",
        SCAN_CRAWL_DELAY_MS: "0",
        AI_PROVIDER: "none",
        CORS_ORIGINS: "http://127.0.0.1:4173",
        SCAN_USER_HOURLY_LIMIT: "100",
      },
    },
    {
      command: "npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173/login",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: { VITE_DEV_API_PROXY: "http://127.0.0.1:8001" },
    },
  ],
});
