import { expect, test } from "@playwright/test";
import { expectNoA11yViolations, registerUser } from "./helpers";

test("mobile navigation works and has no horizontal overflow", async ({ page }) => {
  await registerUser(page);
  const menu = page.getByRole("button", { name: "Open navigation menu" });
  await expect(menu).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await menu.click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expectNoA11yViolations(page, "mobile navigation open");
  await page.getByRole("link", { name: "Contrast checker" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Contrast checker" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await expectNoA11yViolations(page, "mobile contrast page");
});
