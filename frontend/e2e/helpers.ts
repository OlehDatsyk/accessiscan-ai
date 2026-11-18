import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const FIXTURE = "http://127.0.0.1:8765";

/** Run axe-core (WCAG 2.2 A/AA + best practices) against the current page and fail on any violation. */
export async function expectNoA11yViolations(page: Page, context: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`,
  );
  expect(summary, `axe violations on ${context}`).toEqual([]);
}

export async function registerUser(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("E2E Tester");
  await page.getByLabel(/^E-mail address/).fill(email);
  await page.getByLabel(/^Password/).fill("E2ePassword123");
  await page.getByLabel(/^Confirm password/).fill("E2ePassword123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  return { email, password: "E2ePassword123" };
}
