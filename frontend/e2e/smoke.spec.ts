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

    // Logout returns to the signed-out shell
    await page.click("#nav-signout");
    await expect(page.locator("#nav-signin")).toBeVisible({ timeout: 10_000 });
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
