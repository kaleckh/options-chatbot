import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function mockReadOnlyDashboardApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());

    if (request.method() !== "GET") {
      await route.fulfill({
        status: 405,
        contentType: "application/json",
        body: JSON.stringify({ error: "E2E smoke tests are read-only." }),
      });
      return;
    }

    const payload = (() => {
      switch (pathname) {
        case "/api/risk-settings":
          return {
            current_settings: {
              account_size: 100_000,
              max_position_pct: 2,
              stop_loss_pct: 25,
            },
          };
        case "/api/positions":
          return {
            positions: [],
            page: { limit: 50, offset: 0, returned: 0 },
          };
        case "/api/backtest/summary":
          return {
            last: null,
            report: null,
            metricTruth: null,
            comparison: null,
          };
        default:
          return {};
      }
    })();

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockReadOnlyDashboardApi(page);
});

test("loads the Trading Desk and supports keyboard navigation to Strategy Lab", async ({ page }) => {
  await page.goto("/");

  const tradingDeskTab = page.getByRole("tab", { name: "Trading Desk" });
  const strategyLabTab = page.getByRole("tab", { name: "Strategy Lab" });

  await expect(page.getByRole("heading", { name: "Trading Desk", exact: true })).toBeVisible();
  await expect(tradingDeskTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("$100,000 account", { exact: false })).toBeVisible();

  await strategyLabTab.focus();
  await strategyLabTab.press("Enter");
  await expect(page.getByRole("heading", { name: "Strategy Lab", exact: true })).toBeVisible();
  await expect(strategyLabTab).toHaveAttribute("aria-selected", "true");

  await strategyLabTab.press("ArrowLeft");
  await expect(page.getByRole("heading", { name: "Trading Desk", exact: true })).toBeVisible();
  await expect(tradingDeskTab).toHaveAttribute("aria-selected", "true");
});

test("has no serious or critical automated accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Trading Desk", exact: true })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  const blockingViolations = results.violations.filter(
    ({ impact }) => impact === "serious" || impact === "critical"
  );

  expect(
    blockingViolations,
    blockingViolations
      .map(({ help, id, impact, nodes }) =>
        `${impact ?? "unknown"}: ${id} - ${help} (${nodes.length} node(s))`
      )
      .join("\n")
  ).toEqual([]);
});

test.describe("mobile navigation", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("opens the menu and switches to Strategy Lab", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Open navigation menu" }).click();
    const navigation = page.getByRole("dialog", { name: "Navigation menu" });
    await expect(navigation).toBeVisible();

    await navigation.getByRole("tab", { name: "Strategy Lab" }).click();
    await expect(navigation).toBeHidden();
    await expect(page.getByRole("heading", { name: "Strategy Lab", exact: true })).toBeVisible();
  });
});
