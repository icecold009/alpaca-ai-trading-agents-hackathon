import { expect, test } from "@playwright/test";

test("runs five consecutive recorded workstation rehearsals", async ({ browser }) => {
  for (let run = 1; run <= 5; run += 1) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeVisible();
    await page.getByRole("button", { name: /Opportunities/ }).click();
    await expect(page.getByText("Jury odds vs. market hurdle")).toBeVisible();
    await page.getByRole("button", { name: "Provider failure" }).click();
    await expect(page.getByText("Provider unavailable — abstain")).toBeVisible();
    console.info(JSON.stringify({ run, timestamp: new Date().toISOString() }));
    await context.close();
  }
});
