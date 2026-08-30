import { expect, test } from "@playwright/test";

test("runs five consecutive recorded golden-demo rehearsals", async ({ browser }) => {
  const timestamps: string[] = [];

  for (let run = 1; run <= 5; run += 1) {
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "RiskCourt" })).toBeVisible();
    await expect(page.getByText("Verdict: resize")).toBeVisible();

    await page.getByRole("button", { name: /SPY jury cannot clear/i }).click();
    await expect(page.getByText("Verdict: veto")).toBeVisible();
    await expect(page.getByText(/No approval artifact/i)).toBeVisible();

    await page.getByRole("button", { name: "Market closed" }).click();
    await expect(page.getByRole("status")).toContainText("Market closed — no order sent");
    await expect(page.getByRole("status")).toContainText(
      "Fresh quotes are required before a paper order can be considered.",
    );

    await page.getByRole("button", { name: "Provider failure" }).click();
    await expect(page.getByRole("status")).toContainText("Provider unavailable — abstain");
    await expect(page.getByRole("status")).toContainText(
      "A timeout or malformed response never reaches the execution boundary.",
    );

    timestamps.push(new Date().toISOString());
    await context.close();
    console.info(JSON.stringify({ run, timestamp: timestamps.at(-1) }));
  }

  expect(timestamps).toHaveLength(5);
});
