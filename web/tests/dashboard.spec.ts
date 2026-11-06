// Browser tests over the built static export (run `npm run build` first).
// Expectations come from the committed bundle, so they hold on any refresh day,
// including one where the briefing is null.
import { test, expect, type Page } from "@playwright/test";
import rawBundle from "../public/data/anchor.json";
import {
  heldByClass,
  presentClasses,
  rollup,
  sectorsFor,
  trendWindow,
} from "../src/lib/dashboard";
import { fmtDate } from "../src/lib/format";
import type { AnchorBundle } from "../src/lib/types";

const bundle = rawBundle as unknown as AnchorBundle;
const asOf = bundle.as_of_calendar.as_of_date;

function daysAfterAsOf(days: number): Date {
  const [y, m, d] = asOf.split("-").map(Number);
  return new Date(y, m - 1, d + days, 12);
}

const horizonButton = (page: Page, name: string) =>
  page
    .getByRole("group", { name: "Return horizon" })
    .getByRole("button", { name });

const filterGroup = (page: Page) =>
  page.getByRole("group", { name: "Filter by asset class" });

async function pathPointCount(page: Page, selector: string): Promise<number> {
  const d = await page.locator(selector).first().getAttribute("d");
  return (d ?? "").match(/[ML]/g)?.length ?? 0;
}

test.describe("masthead", () => {
  test("headlines the regime and shows the as-of date and the portfolio", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      bundle.macro_regime.regime_summary,
    );
    const masthead = page.locator("[data-masthead]");
    await expect(masthead).toContainText(fmtDate(asOf));
    await expect(masthead).toContainText("Demo portfolio");
  });

  test("names the page and carries the anchor icon", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Anchor — Morning Briefing");
    await expect(page.locator('link[rel="icon"]')).toHaveAttribute(
      "href",
      /icon\.svg/,
    );
  });
});

test.describe("horizon", () => {
  test("defaults to 1 Month, then 1 Year re-sorts the sectors", async ({ page }) => {
    await page.goto("/");
    await expect(horizonButton(page, "1 Month")).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("[data-sector-row]").first()).toHaveAttribute(
      "data-sector-row",
      sectorsFor(bundle, "1m")[0].etf_ticker,
    );

    await horizonButton(page, "1 Year").click();
    await expect(horizonButton(page, "1 Year")).toHaveAttribute("aria-pressed", "true");
    await expect(horizonButton(page, "1 Month")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("[data-sector-row]").first()).toHaveAttribute(
      "data-sector-row",
      sectorsFor(bundle, "1y")[0].etf_ticker,
    );
  });

  test("drives holding returns, comparisons and rollup text", async ({ page }) => {
    const holding = bundle.portfolio_composition.find(
      (p) =>
        p.return_1m_pct !== null &&
        p.return_1y_pct !== null &&
        bundle.holdings_benchmarks.some((r) => r.holding_ticker === p.ticker),
    );
    expect(holding).toBeDefined();
    const bench = bundle.holdings_benchmarks.find(
      (r) => r.holding_ticker === holding!.ticker,
    )!;
    const row = page.locator(`[data-holding-row="${holding!.ticker}"]`);

    await page.goto("/");
    await expect(row).toContainText(`${Math.abs(holding!.return_1m_pct!).toFixed(2)}%`);
    await expect(row).toContainText(`${Math.abs(bench.relative_1m_pp!).toFixed(2)} pp`);

    await horizonButton(page, "1 Year").click();
    await expect(row).toContainText(`${Math.abs(holding!.return_1y_pct!).toFixed(2)}%`);
    await expect(row).toContainText(`${Math.abs(bench.relative_1y_pp!).toFixed(2)} pp`);

    const rollup1y = rollup(bundle, "1y")[0];
    await expect(page.locator(`[data-rollup="${rollup1y.axis}"]`)).toContainText(
      `${rollup1y.ahead} ahead · ${rollup1y.behind} behind · ${rollup1y.in_line} in line`,
    );
  });

  test("windows sparklines to the horizon; macro sparklines hold their full series", async ({
    page,
  }) => {
    const etf = bundle.sector_performance[0].etf_ticker;
    const sectorSpark = `[data-sector-row="${etf}"] svg path`;
    const macroPaths = page.locator("[data-macro-col] svg path");

    await page.goto("/");
    expect(await pathPointCount(page, sectorSpark)).toBe(
      trendWindow(bundle, etf, "1m").length,
    );
    const macroBefore = await macroPaths.evaluateAll((els) =>
      els.map((e) => e.getAttribute("d")),
    );

    await horizonButton(page, "YTD").click();
    await expect(horizonButton(page, "YTD")).toHaveAttribute("aria-pressed", "true");
    expect(await pathPointCount(page, sectorSpark)).toBe(
      trendWindow(bundle, etf, "ytd").length,
    );
    expect(
      await macroPaths.evaluateAll((els) => els.map((e) => e.getAttribute("d"))),
    ).toEqual(macroBefore);
  });
});

test.describe("sections", () => {
  test("4 macro columns, 11 sector rows, one holding row per position", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator("[data-macro-col]")).toHaveCount(4);
    await expect(page.locator("[data-sector-row]")).toHaveCount(11);
    await expect(page.locator("[data-holding-row]")).toHaveCount(
      bundle.portfolio_composition.length,
    );
  });

  test("reads macro, then sectors, then holdings", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 2 })).toHaveText([
      "Macro environment",
      "Sectors",
      "Holdings",
    ]);
  });

  test("holding rows name benchmarks, roots, unbenchmarked and import-valued rows", async ({
    page,
  }) => {
    await page.goto("/");
    for (const p of bundle.portfolio_composition) {
      const row = page.locator(`[data-holding-row="${p.ticker}"]`);
      const rows = bundle.holdings_benchmarks.filter(
        (r) => r.holding_ticker === p.ticker,
      );
      for (const r of rows) {
        await expect(row).toContainText(`vs ${r.benchmark_etf}`);
      }
      if (rows.length === 0) {
        await expect(row).toContainText(
          p.is_root ? "Market reference point" : "Not benchmarked",
        );
      }
      if (p.valuation_source === "source") {
        await expect(row).toContainText("import-valued");
      }
    }
  });

  test("the first benchmark axis is overlaid on the holding sparkline", async ({
    page,
  }) => {
    await page.goto("/");
    const benchmarked = bundle.holdings_benchmarks[0].holding_ticker;
    await expect(
      page.locator(`[data-holding-row="${benchmarked}"] svg path`),
    ).toHaveCount(2);
    const root = bundle.portfolio_composition.find((p) => p.is_root);
    if (root) {
      await expect(
        page.locator(`[data-holding-row="${root.ticker}"] svg path`),
      ).toHaveCount(1);
    }
  });

  test("marks are hidden from assistive tech and null values read as a dash", async ({
    page,
  }) => {
    await page.goto("/");
    const svgs = page.locator("[data-dashboard] svg");
    expect(await svgs.count()).toBeGreaterThan(0);
    expect(
      await svgs.evaluateAll((els) =>
        els.every((e) => e.getAttribute("aria-hidden") === "true"),
      ),
    ).toBe(true);

    for (const name of ["1 Month", "YTD", "1 Year"]) {
      await horizonButton(page, name).click();
      const text = await page.locator("[data-dashboard]").innerText();
      expect(text).not.toMatch(/\b(NaN|undefined|null)\b/);
    }

    const unpriced = bundle.portfolio_composition.find((p) => p.return_1m_pct === null);
    if (unpriced) {
      await horizonButton(page, "1 Month").click();
      await expect(
        page.locator(`[data-holding-row="${unpriced.ticker}"]`),
      ).toContainText("—");
    }
  });

  test("controls meet the 34px minimum height", async ({ page }) => {
    await page.goto("/");
    const buttons = page.locator("[data-dashboard] button");
    const heights = await buttons.evaluateAll((els) =>
      els.map((e) => e.getBoundingClientRect().height),
    );
    expect(heights.length).toBeGreaterThan(0);
    for (const h of heights) expect(h).toBeGreaterThanOrEqual(34);
  });
});

test.describe("asset-class filter", () => {
  test("lists only held classes", async ({ page }) => {
    await page.goto("/");
    await expect(filterGroup(page).getByRole("button")).toHaveCount(
      presentClasses(bundle).length,
    );
  });

  test("clearing Equities removes that group's rows", async ({ page }) => {
    const equities = heldByClass(bundle, "equity");
    await page.goto("/");
    const button = filterGroup(page).getByRole("button", { name: "Equities" });
    await expect(button).toHaveAttribute("aria-pressed", "true");

    await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator("[data-holding-row]")).toHaveCount(
      bundle.portfolio_composition.length - equities.length,
    );
    await expect(
      page.locator(`[data-holding-row="${equities[0].ticker}"]`),
    ).toHaveCount(0);
  });

  test("clearing every class shows a reset that restores the rows", async ({
    page,
  }) => {
    await page.goto("/");
    const buttons = filterGroup(page).getByRole("button");
    const count = await buttons.count();
    for (let i = 0; i < count; i++) await buttons.nth(i).click();

    await expect(page.locator("[data-holding-row]")).toHaveCount(0);
    await expect(page.getByText("No asset classes selected")).toBeVisible();

    await page.getByRole("button", { name: "Show all" }).click();
    await expect(page.locator("[data-holding-row]")).toHaveCount(
      bundle.portfolio_composition.length,
    );
    await expect(page.getByText("No asset classes selected")).toHaveCount(0);
  });
});

test.describe("how to read this", () => {
  test("the disclosure carries the Quick Guide and per-card help", async ({
    page,
  }) => {
    await page.goto("/");
    const guideRule = page.getByText(
      "Fed Funds Rate increased by 0.25 pp or more over 3 months (at least one standard Fed rate hike).",
    );
    const cardHelp = page.getByText(
      "The percentage of the labor force actively seeking work.",
    );
    await expect(guideRule).toBeHidden();

    await page.getByText("How to read this").click();
    await expect(guideRule).toBeVisible();
    await expect(cardHelp).toBeVisible();
  });
});

test.describe("staleness notice", () => {
  test("appears 5 days past the as-of date", async ({ page }) => {
    await page.clock.setFixedTime(daysAfterAsOf(5));
    await page.goto("/");
    await expect(page.getByText(`Data through ${fmtDate(asOf)}`)).toBeVisible();
  });

  test("does not appear on the as-of date or 4 days after it", async ({ page }) => {
    await page.clock.setFixedTime(daysAfterAsOf(0));
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Data through")).toHaveCount(0);

    await page.clock.setFixedTime(daysAfterAsOf(4));
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Data through")).toHaveCount(0);
  });

  test("never ships in the server-rendered HTML", async ({ request }) => {
    const html = await (await request.get("/")).text();
    expect(html).not.toContain("Data through");
  });

  test("hydrates without errors when the notice shows", async ({ page }) => {
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") problems.push(m.text());
    });
    await page.clock.setFixedTime(daysAfterAsOf(5));
    await page.goto("/");
    await expect(page.getByText("Data through")).toBeVisible();
    expect(problems).toEqual([]);
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test("no horizontal scrolling at 375px on any horizon", async ({ page }) => {
    await page.goto("/");
    await page.getByText("How to read this").click();
    for (const name of ["1 Month", "YTD", "1 Year"]) {
      await horizonButton(page, name).click();
      const { scrollWidth, innerWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      expect(scrollWidth).toBeLessThanOrEqual(innerWidth);
    }
  });
});

test.describe("guided reading", () => {
  test("the link follows the briefing", async ({ page }) => {
    await page.goto("/");
    const link = page.getByRole("link", { name: /guided reading/i });
    if (bundle.briefing) {
      await expect(link).toHaveAttribute("href", "/reading/");
      await link.click();
      await expect(page).toHaveURL(/\/reading\/$/);
    } else {
      await expect(link).toHaveCount(0);
    }
  });

  test("the rail carries the narration, or the regime when there is none", async ({
    page,
  }) => {
    await page.goto("/");
    const rail = page.locator("[data-rail]");
    if (bundle.briefing) {
      await expect(rail).toContainText(bundle.briefing.steps[0].narration);
    } else {
      await expect(rail).toContainText(bundle.macro_regime.regime_summary);
      await expect(rail).toContainText(bundle.macro_regime.rates_state);
      await expect(rail).toContainText(bundle.macro_regime.inflation_state);
      await expect(rail).toContainText(bundle.macro_regime.labor_state);
    }
  });
});

test.describe("before hydration", () => {
  test.use({ javaScriptEnabled: false });

  test("the 1 Month view is in the static HTML", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      bundle.macro_regime.regime_summary,
    );
    await expect(page.locator("[data-sector-row]")).toHaveCount(11);
    await expect(page.locator("[data-sector-row]").first()).toHaveAttribute(
      "data-sector-row",
      sectorsFor(bundle, "1m")[0].etf_ticker,
    );
    await expect(page.locator("[data-holding-row]")).toHaveCount(
      bundle.portfolio_composition.length,
    );
  });
});
