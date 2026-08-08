import { test, expect, type Page } from "@playwright/test";
import { makeUniqueFixture } from "./lib/png";

/**
 * DenoiseX smoke test — the single happy-path journey.
 *
 * register -> upload -> poll to COMPLETED -> 4 outputs render -> download
 * URLs present -> gallery shows outputs -> logout.
 *
 * Runs against a LIVE stack: gateway (uvicorn :8000) + worker + Docker infra
 * must already be up (see e2e/README.md). This is intentionally small: no
 * auth-failure, rate-limit, or validation edge cases live here.
 *
 * The upload fixture is a fresh random PNG per run so it always exercises the
 * processing pipeline (the backend dedups identical bytes per organization).
 */

const NAME = "E2E Tester";
// Reuse a persistent account when provided (avoids the 3/day register cap on
// repeated runs); otherwise derive a fresh throwaway account.
const EMAIL = process.env.E2E_EMAIL ?? `e2e-${Date.now()}@example.com`;
const PASSWORD = process.env.E2E_PASSWORD ?? "E2E-Password-123";

const OUTPUT_TYPES = ["original", "noise-map", "unet", "enhanced"] as const;

test.describe.serial("DenoiseX smoke", () => {
  test("register/login -> upload -> poll -> results -> gallery -> logout", async ({ page }) => {
    await signInOrRegister(page);

    await uploadAndWaitForResults(page);

    // 4 outputs render (presigned URLs resolved) + download links present
    for (const type of OUTPUT_TYPES) {
      await expect(page.locator(`#output-${type}`)).toBeVisible();
    }
    for (const type of OUTPUT_TYPES) {
      const download = page.locator(`#download-${type}`);
      await expect(download).toBeVisible();
      const href = await download.getAttribute("href");
      expect(href).toContain("http");
    }

    // Gallery lists the scan and shows outputs when expanded
    await page.click("#nav-gallery");
    await expect(page).toHaveURL(/\/gallery/);
    const expand = page.locator("button[id^='expand-']").first();
    await expect(expand).toBeVisible({ timeout: 20_000 });
    await expand.click();
    await expect(page.locator("#output-enhanced")).toBeVisible({ timeout: 20_000 });

    // Logout returns to the signed-out shell (sign out lives in the user menu)
    await page.click("#nav-user-menu");
    await page.click("#nav-signout");
    await expect(page.locator("#nav-signin")).toBeVisible({ timeout: 10_000 });
  });

  test("dashboard + status matrix + feedback/about links", async ({ page }) => {
    await signIn(page);

    // Dashboard: infra + worker + model + queue cards and dependency matrix
    await page.click("#nav-dashboard");
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("#dashboard-refresh")).toBeVisible();
    await expect(page.getByText("Worker", { exact: true })).toBeVisible();
    await expect(page.getByText("Model", { exact: true })).toBeVisible();
    await expect(page.getByText("Queue Depth", { exact: true })).toBeVisible();
    await expect(page.getByText("PostgreSQL")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Object Storage (MinIO)")).toBeVisible();

    // Status: full infra matrix (worker/model/queue/build only render when the
    // authorized /health/infra payload arrives, not the public ready probe)
    await page.click("#nav-status");
    await expect(page).toHaveURL(/\/status/);
    await expect(page.locator("#status-refresh")).toBeVisible();
    await expect(page.getByText("All systems operational")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Worker & Model")).toBeVisible();
    await expect(page.getByText("Worker Alive")).toBeVisible();
    await expect(page.getByText("Last Heartbeat")).toBeVisible();
    await expect(page.getByText("Inference Queue")).toBeVisible();
    await expect(page.getByText("inference.worker")).toBeVisible();
    await expect(page.getByText("Build", { exact: true })).toBeVisible();
    await expect(page.getByText("Git SHA")).toBeVisible();
    await page.click("#status-refresh");
    await expect(page.locator("#status-refresh")).toBeEnabled();

    // Feedback: GitHub issue + mailto destinations
    await page.click("#nav-feedback");
    await expect(page).toHaveURL(/\/feedback/);
    await expect(page.locator("#feedback-github")).toBeVisible();
    await expect(
      page.locator('a[href*="github.com/Reckz69/medical-xray/issues/new"]')
    ).toBeVisible();
    await expect(page.locator("#feedback-mail")).toBeVisible();
    await expect(page.locator('a[href^="mailto:"]')).toBeVisible();

    // About: model version + license
    await page.click("#nav-about");
    await expect(page).toHaveURL(/\/about/);
    await expect(page.getByText("Model Version")).toBeVisible();
    await expect(page.getByText("MIT License")).toBeVisible();
  });

  test("soft-delete a scan from the gallery", async ({ page }) => {
    await signIn(page);
    await page.click("#nav-gallery");
    await expect(page).toHaveURL(/\/gallery/);

    // Delete the first scan: confirm button appears, then the scan disappears
    const del = page.locator('button[id^="delete-"]').first();
    await expect(del).toBeVisible({ timeout: 30_000 });
    const scanId = (await del.getAttribute("id"))!.replace("delete-", "");
    await del.click();
    const confirm = page.locator(`#delete-confirm-${scanId}`);
    await expect(confirm).toBeVisible();
    await confirm.click();
    await expect(confirm).toBeHidden({ timeout: 20_000 });
    await expect(page.locator(`#expand-${scanId}`)).toBeHidden({ timeout: 20_000 });
  });

  test("status page is auth-gated when signed out", async ({ page }) => {
    await page.goto("/status");
    await expect(page.locator("#go-signin")).toBeVisible();
  });
});

/**
 * Try login first (persistent account), fall back to registering a fresh one.
 * Signups are capped at 3/day/IP, so the smoke test prefers an existing user.
 */
async function signInOrRegister(page: Page) {
  await page.goto("/signin");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("#signin-submit");

  const loggedIn = await page
    .waitForURL(/\/denoise/, { timeout: 8_000 })
    .then(() => true)
    .catch(() => false);
  if (loggedIn) return;

  await page.goto("/signin");
  await page.click("#show-register");
  await page.fill("#name", NAME);
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("#register-submit");
  await expect(page).toHaveURL(/\/denoise/, { timeout: 15_000 });
}

async function uploadAndWaitForResults(page: Page) {
  const fixture = makeUniqueFixture();
  await page.setInputFiles("#file-input", fixture);
  await expect(page.locator("#process-btn")).toBeVisible();
  await page.click("#process-btn");

  // Polling finishes only when the worker reaches COMPLETED. Generous timeout
  // to cover a cold model load on CPU.
  await expect(page.locator("#output-enhanced")).toBeVisible({ timeout: 300_000 });
}

/** Sign in to the shared E2E account. Fails fast if the account does not exist. */
async function signIn(page: Page) {
  await page.goto("/signin");
  await page.fill("#email", EMAIL);
  await page.fill("#password", PASSWORD);
  await page.click("#signin-submit");
  await expect(page).toHaveURL(/\/denoise/, { timeout: 15_000 });
}
