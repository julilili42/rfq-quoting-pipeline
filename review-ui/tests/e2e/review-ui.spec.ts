import { expect, test } from "@playwright/test";

import { ids, mockReviewApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockReviewApi(page);
});

test("opens a review from the dashboard and shows extracted position data", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Anfragen/i })).toBeVisible();
  await expect(page.getByText("Preisanfrage 2026-50422")).toBeVisible();

  await page.getByText("Preisanfrage 2026-50422").click();

  await expect(page).toHaveURL(new RegExp(`/reviews/${ids.review}/positions$`));
  await expect(page.getByRole("heading", { name: /Positionen/i })).toBeVisible();
  await page.getByRole("button", { name: /Pos 1 001GLP108015/i }).click();
  await expect(page.getByText(/exakt/i).first()).toBeVisible();
});

test("blocks approval when a position has no master-data match", async ({ page }) => {
  await page.goto(`/reviews/${ids.blockedReview}/approval`);

  await expect(page.getByText(/Freigabe blockiert/i)).toBeVisible();
  await expect(page.getByText(/kein Stammdaten-Treffer/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Freigeben" })).toBeDisabled();
});

test("leaves fullscreen comparison with Escape", async ({ page }) => {
  await page.goto(`/reviews/${ids.review}/approval`);

  await page.getByRole("button", { name: "Vollbild" }).click();
  await expect(page).toHaveURL(/focus=1/);
  await expect(page.getByRole("button", { name: "Vollbild verlassen" })).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page).toHaveURL(new RegExp(`/reviews/${ids.review}/approval$`));
  await expect(page.getByRole("button", { name: "Vollbild" })).toBeVisible();
});

test("finalizes an approved draft and shows the final offer state", async ({ page }) => {
  await page.goto(`/reviews/${ids.review}/approval`);

  await expect(page.getByText(/Bereit zur Freigabe/i)).toBeVisible();
  const summary = page.locator("section[aria-labelledby='approval-summary-heading']");
  await expect(summary.getByText("Abschluss-Check")).toBeVisible();
  await expect(summary.getByText(/2\.447,50/).first()).toBeVisible();
  await page.getByPlaceholder("Vor- und Nachname").fill("Demo User");
  await page.getByRole("button", { name: "Freigeben" }).click();

  await expect(page.getByText(/Angebot freigegeben/i)).toBeVisible();
  await expect(page.getByText("Angebot_demo_FINAL.pdf")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Finales Angebot" })).toBeVisible();
});
