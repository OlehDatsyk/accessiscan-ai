/**
 * Captures README screenshots from the real running application (local fixture site, real scans).
 * Skipped unless SCREENSHOTS=1:  SCREENSHOTS=1 npx playwright test screenshots --project=desktop
 */
import { expect, test } from "@playwright/test";
import path from "node:path";
import { FIXTURE, registerUser } from "./helpers";

const OUT = path.join("..", "docs", "screenshots");
test.skip(!process.env.SCREENSHOTS, "Set SCREENSHOTS=1 to capture README screenshots");
test.use({ viewport: { width: 1440, height: 900 } });

test("capture screenshots", async ({ page }) => {
  test.setTimeout(240_000);
  await registerUser(page);

  const addSite = async (name: string, url: string) => {
    await page.goto("/websites");
    await page.getByRole("button", { name: "Add website" }).first().click();
    const d = page.getByRole("dialog", { name: "Add website" });
    await d.getByLabel(/^Name/).fill(name);
    await d.getByLabel(/^URL/).fill(url);
    await d.getByLabel("Description").fill("Local fixture site used for the screenshots (known accessibility defects).");
    await d.getByRole("button", { name: "Add website" }).click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  };
  const scan = async (mode?: "crawl") => {
    await page.getByRole("main").getByRole("link", { name: "New scan" }).click();
    if (mode === "crawl") {
      await page.getByLabel("Limited crawl").check();
      await page.getByLabel("Maximum pages").fill("4");
    }
    await page.getByRole("button", { name: "Start scan" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Reports" })).toBeVisible({ timeout: 120_000 });
  };

  await addSite("Demo storefront", `${FIXTURE}/violations.html`);
  await scan();
  await page.getByRole("link", { name: /Images must have alternative text/ }).first().click();
  await page.getByRole("combobox", { name: "Status" }).selectOption("marked_fixed");
  await page.getByRole("button", { name: "Update status" }).click();
  await page.goto("/websites");
  await page.getByRole("link", { name: "Demo storefront", exact: true }).click();
  await scan();
  await page.screenshot({ path: path.join(OUT, "scan-results.png"), fullPage: false });

  await page.getByRole("link", { name: /Images must have alternative text/ }).first().click();
  await expect(page.getByText("Built-in guidance (not AI)")).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "issue-detail.png") });

  await addSite("Docs portal", `${FIXTURE}/index.html`);
  await scan("crawl");
  await page.getByRole("tab", { name: /Pages/ }).click();
  await page.screenshot({ path: path.join(OUT, "crawl-pages.png") });

  await page.goto("/");
  await expect(page.getByText("Total scans")).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "dashboard.png") });

  await page.goto("/issues");
  await expect(page.getByRole("status").filter({ hasText: /issues? found/ })).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "issues.png") });

  await page.goto("/scans");
  const rows = page.getByRole("link", { name: "Demo storefront" });
  await rows.first().click();
  await page.getByRole("link", { name: "Compare with previous" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Compare scans" })).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "compare.png") });

  await page.goto("/contrast");
  await page.getByLabel("Text (foreground) colour").fill("#8a94a6");
  await page.screenshot({ path: path.join(OUT, "contrast-checker.png") });

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "login.png") });
});
