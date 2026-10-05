import { expect, test } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const apiOrigin = "http://127.0.0.1:8000";

test("runs the local paper workstation lifecycle against a fake broker API", async ({
  page,
}, testInfo) => {
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const reset = await page.request.post(`${apiOrigin}/__test/reset`);
  expect(reset.ok()).toBeTruthy();
  await page.goto("/");
  await expect(page).toHaveTitle("RiskCourt");
  await expect(page.getByText("Local API connected", { exact: true })).toBeVisible();
  await expect(page.getByText("Paper mode", { exact: true })).toBeVisible();
  const navigation = await page
    .getByRole("navigation", { name: "Primary navigation" })
    .evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return {
        right: bounds.right,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        viewportWidth: element.ownerDocument.documentElement.clientWidth,
      };
    });
  expect(navigation.right).toBeLessThanOrEqual(navigation.viewportWidth + 1);
  expect(navigation.scrollWidth).toBeLessThanOrEqual(navigation.clientWidth + 1);

  const firstScanResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/scans") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Scan now" }).click();
  const firstScanResponse = await firstScanResponsePromise;
  expect(firstScanResponse.status()).toBe(200);
  const firstScan = await firstScanResponse.json();
  expect(firstScan.decisions, JSON.stringify(firstScan)).toHaveLength(1);
  await expect(page.getByText("Scan completed. Review the newest opportunity.")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Decision passed deterministic review" }),
  ).toBeVisible();

  const firstDecisionId = firstScan.decisions[0].decision_id as string;
  await page.getByRole("button", { name: "Prepare backend approval" }).click();
  await expect(
    page.getByText("Approval prepared. Review every order field before submitting."),
  ).toBeVisible();

  const veto = await page.request.post(`${apiOrigin}/api/decisions/${firstDecisionId}/veto`);
  expect(veto.status()).toBe(200);
  await page.reload();
  await expect(page.getByText("Local API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Opportunities/ }).click();
  await expect(page.getByRole("heading", { name: "Trade vetoed — no order sent" })).toBeVisible();

  const nextScanResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/api/scans") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Scan now" }).click();
  const nextScanResponse = await nextScanResponsePromise;
  expect(nextScanResponse.status()).toBe(200);
  const nextScan = await nextScanResponse.json();
  expect(nextScan.decisions, JSON.stringify(nextScan)).toHaveLength(1);
  await page.getByRole("button", { name: "Prepare backend approval" }).click();
  await expect(
    page.getByText("Approval prepared. Review every order field before submitting."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm & submit" }).click();
  await expect(page.getByText("Paper order accepted. Portfolio refreshed.")).toBeVisible();

  const entryFill = await page.request.post(`${apiOrigin}/__test/fill-latest-order`);
  expect(await entryFill.json()).toMatchObject({ status: "filled", kind: "entry" });
  await page.reload();
  await expect(page.getByText("Local API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Portfolio" }).click();
  await expect(page.getByRole("button", { name: "Preview exit" })).toBeVisible();
  await page.screenshot({
    path: join(tmpdir(), `riskcourt-${testInfo.project.name}-open-position.png`),
    fullPage: false,
  });

  await page.getByRole("button", { name: "Preview exit" }).click();
  await expect(page.getByText(/Exit preview ready for 1 contract/)).toBeVisible();
  await page.getByRole("button", { name: "Confirm paper exit" }).click();
  await expect(page.getByText("Exit order accepted. Portfolio refreshed.")).toBeVisible();

  const exitFill = await page.request.post(`${apiOrigin}/__test/fill-latest-order`);
  expect(await exitFill.json()).toMatchObject({ status: "filled", kind: "exit" });
  await page.reload();
  await expect(page.getByText("Local API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Portfolio" }).click();
  const closedPositions = page.getByText("Closed positions (1)", { exact: true });
  await expect(closedPositions).toBeVisible();
  await closedPositions.click();
  await expect(page.getByText(/realized.*15\.00/)).toBeVisible();
  await page.screenshot({
    path: join(tmpdir(), `riskcourt-${testInfo.project.name}-closed-position.png`),
    fullPage: false,
  });

  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: /Pause new entries/ }).click();
  await expect(page.getByText("Enabled", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Resume new entries/ }).click();
  await expect(page.getByText("Armed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /QQQ Add to watchlist/ }).click();
  await expect(page.getByText("Watchlist saved by the backend.")).toBeVisible();

  await page.getByRole("button", { name: "Journal" }).click();
  const journalNote = `Playwright lifecycle evidence ${testInfo.project.name}`;
  await page.getByPlaceholder(/Capture the thesis/).fill(journalNote);
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText(journalNote, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Local API connected", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Journal" }).click();
  await expect(page.getByText(journalNote, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("button", { name: /QQQ Monitoring/ })).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
