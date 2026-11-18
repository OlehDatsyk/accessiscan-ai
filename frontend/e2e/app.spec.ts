import { expect, test } from "@playwright/test";
import { expectNoA11yViolations, FIXTURE, registerUser } from "./helpers";

test("login and registration pages are accessible and validate input", async ({ page }) => {
  await page.goto("/login");
  await expectNoA11yViolations(page, "login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Enter your e-mail address")).toBeVisible();
  await expect(page.getByLabel(/^E-mail address/)).toHaveAttribute("aria-invalid", "true");
  await page.goto("/register");
  await expectNoA11yViolations(page, "register");
  await page.getByLabel(/^Password/).fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Use at least 10 characters")).toBeVisible();
});

test("full audit workflow with a real scan, keyboard access and axe checks on every page", async ({ page }) => {
  const user = await registerUser(page);
  await expectNoA11yViolations(page, "empty dashboard");

  // The skip link is the first focusable element.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

  // Add a website (the local fixture site with known violations).
  await page.goto("/websites");
  await page.getByRole("button", { name: "Add website" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Add website" });
  await expect(dialog).toBeVisible();
  await expectNoA11yViolations(page, "add website dialog");
  await dialog.getByLabel(/^Name/).fill("Fixture shop");
  await dialog.getByLabel(/^URL/).fill(`${FIXTURE}/violations.html`);
  await dialog.getByRole("button", { name: "Add website" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Fixture shop" })).toBeVisible();
  await expectNoA11yViolations(page, "website detail");

  // The SSRF guard is visible in the UI: a cloud metadata address is refused.
  await page.goto("/websites");
  await page.getByRole("button", { name: "Add website" }).first().click();
  const d2 = page.getByRole("dialog", { name: "Add website" });
  await d2.getByLabel(/^Name/).fill("Internal");
  await d2.getByLabel(/^URL/).fill("http://169.254.169.254/latest/meta-data/");
  await d2.getByRole("button", { name: "Add website" }).click();
  await expect(d2.getByRole("alert")).toContainText(/private, local or reserved/);
  await page.keyboard.press("Escape");
  await expect(d2).toBeHidden();

  // Run a real scan.
  await page.goto("/scans/new");
  await expect(page.getByRole("heading", { level: 1, name: "New scan" })).toBeVisible();
  await expectNoA11yViolations(page, "new scan");
  await page.getByRole("button", { name: "Start scan" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Scan results: Fixture shop/ })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Reports" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("tab", { name: /Issues/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Images must have alternative text/ }).first()).toBeVisible();
  await expectNoA11yViolations(page, "scan results");

  // Tabs: keyboard navigation and other panels.
  await page.getByRole("tab", { name: /Issues/ }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: /Pages/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: /Manual review/ }).click();
  await expect(page.getByRole("heading", { name: "All functionality is keyboard operable" })).toBeVisible();
  await expectNoA11yViolations(page, "manual review tab");
  await page.getByRole("button", { name: "How is this calculated?" }).click();
  await expect(page.getByRole("dialog", { name: "How the score is calculated" })).toBeVisible();
  await expectNoA11yViolations(page, "methodology dialog");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "How is this calculated?" })).toBeFocused();

  // Filter issues by severity.
  await page.getByRole("tab", { name: /Issues/ }).click();
  await page.getByLabel(/^Critical/).check();
  await expect(page.getByRole("status").filter({ hasText: /issues? found/ })).toBeVisible();

  // Issue detail: built-in guidance, AI unavailable state, status and notes.
  await page.getByRole("link", { name: /Images must have alternative text/ }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: /Images must have alternative text/ })).toBeVisible();
  await expect(page.getByText("Built-in guidance (not AI)")).toBeVisible();
  await expect(page.getByRole("button", { name: "Get AI suggestion" })).toBeDisabled();
  await expectNoA11yViolations(page, "issue detail");
  await page.getByRole("combobox", { name: "Status" }).selectOption("ignored");
  await page.getByRole("button", { name: "Update status" }).click();
  await expect(page.getByText("Enter a reason for ignoring this issue")).toBeVisible();
  await page.getByLabel(/Reason for ignoring/).fill("Decorative tracking pixel");
  await page.getByRole("button", { name: "Update status" }).click();
  await expect(page.getByText("Status updated.")).toBeVisible();
  await page.getByLabel("Add a note").fill("Checked with design team");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Checked with design team")).toBeVisible();

  // Report generation downloads a real PDF.
  await page.getByRole("link", { name: "Back to scan results" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF report" }).click();
  expect((await download).suggestedFilename()).toMatch(/^accessiscan-fixture-shop-.*\.pdf$/);

  // Every other page renders and is accessible.
  const pages: [string, string][] = [
    ["/", "Dashboard"],
    ["/issues", "Issues"],
    ["/scans", "Scan results"],
    ["/reports", "Reports"],
    ["/monitoring", "Monitoring"],
    ["/assistant", "AI accessibility assistant"],
    ["/contrast", "Contrast checker"],
    ["/compare", "Compare scans"],
    ["/settings", "Settings"],
    ["/does-not-exist", "Page not found"],
  ];
  for (const [path, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeAttached();
    await page.waitForLoadState("networkidle");
    await expectNoA11yViolations(page, path);
  }

  // Sign out and back in.
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel(/^E-mail address/).fill(user.email);
  await page.getByLabel(/^Password/).fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
});

test("contrast checker calculates WCAG results", async ({ page }) => {
  await registerUser(page);
  await page.goto("/contrast");
  const fg = page.getByLabel("Text (foreground) colour");
  await fg.fill("#777777");
  await page.getByLabel("Background colour", { exact: true }).fill("#ffffff");
  await expect(page.getByText("4.47:1")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "WCAG AA – normal text" })).toContainText("Fail");
  await expect(page.getByRole("listitem").filter({ hasText: "WCAG AA – large text" })).toContainText("Pass");
  await fg.fill("not-a-colour");
  await expect(page.getByText("Enter a valid HEX or rgb() colour").first()).toBeVisible();
  await fg.fill("#000");
  await expect(page.getByText("21.00:1")).toBeVisible();
  await expectNoA11yViolations(page, "contrast checker");
});

test("reduced motion is respected", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/login");
  const duration = await page.evaluate(() => {
    const el = document.createElement("div");
    el.className = "animate-spin";
    document.body.appendChild(el);
    return getComputedStyle(el).animationDuration;
  });
  expect(["0.01ms", "1e-05s", "0s"]).toContain(duration);
  await context.close();
});
