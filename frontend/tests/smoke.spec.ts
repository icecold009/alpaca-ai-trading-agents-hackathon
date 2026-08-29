import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("replays both accessible recorded cases with the network disabled", async ({
  context,
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle("RiskCourt");
  await expect(page.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeVisible();
  await expect(page.getByText("Verdict: resize")).toBeVisible();

  await context.setOffline(true);
  await page.getByRole("button", { name: /SPY jury cannot clear/i }).click();
  await expect(page.getByText("Verdict: veto")).toBeVisible();
  await expect(page.getByText(/No approval artifact/i)).toBeVisible();
  await page.getByRole("button", { name: /SPY jury edge clears/i }).click();
  await expect(page.getByText("Verdict: resize")).toBeVisible();
  await expect(page.getByText("+$25.00")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  expect(results.violations).toEqual([]);
});
