import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("opens the personal workstation and exercises the recorded decision flow", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle("RiskCourt");
  await expect(page.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeVisible();
  await expect(page.getByText("Recorded mode", { exact: true })).toBeVisible();
  await expect(page.getByText("Trade less.")).toBeVisible();

  await page.getByRole("button", { name: /Opportunities/ }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "Find the next defensible setup." }),
  ).toBeVisible();
  await expect(page.getByText("Jury odds vs. market hurdle")).toBeVisible();

  await page.getByRole("button", { name: /SPY jury cannot clear/i }).click();
  await page.getByRole("button", { name: "Confirm veto" }).click();
  await expect(page.getByText("Trade vetoed — no order sent")).toBeVisible();
  await expect(page.getByText(/No approval artifact/i)).toBeVisible();

  await page.getByRole("button", { name: "Market closed" }).click();
  await expect(page.getByText("Market closed — no order sent")).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});
