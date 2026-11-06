// Browser smoke over the built static export (run `npm run build` first —
// the webServer serves out/, it does not build).
import { test, expect } from "@playwright/test";
import rawBundle from "../public/data/anchor.json";
import type { AnchorBundle } from "../src/lib/types";

const bundle = rawBundle as unknown as AnchorBundle;

test("tour renders, carries every script step, and spotlights on scroll", async ({
  page,
}) => {
  test.skip(!bundle.briefing, "the tour needs a briefing");
  await page.goto("/reading/");
  await expect(page).toHaveTitle("Anchor — Guided Reading");

  // 1. Renders: the masthead headline is the regime sentence.
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    bundle.macro_regime.regime_summary,
  );

  // 2. Every tour step is present as a scroll sentinel — the page binds the
  //    script generically, whatever its length.
  await expect(page.locator("[data-step-sentinel]")).toHaveCount(
    bundle.briefing!.steps.length,
  );

  // 3. The first spotlight fires on scroll: center step 2's sentinel
  //    (the indicator step) in the viewport, then exactly one macro card is
  //    active and the rail has advanced with it.
  await page
    .locator('[data-step-sentinel="2"]')
    .evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expect(
    page.locator('[data-scene="macro"] [data-active="true"]'),
  ).toHaveCount(1);
  await expect(page.locator("[data-active-step]")).toHaveAttribute(
    "data-active-step",
    "2",
  );
});

test("without a briefing the reading route points back to the dashboard", async ({
  page,
}) => {
  test.skip(!!bundle.briefing, "only applies when the briefing is null");
  await page.goto("/reading/");
  await expect(page.locator("[data-step-sentinel]")).toHaveCount(0);
  await expect(page.locator('main a[href="/"]')).toBeVisible();
});

test("the plain-text fallback carries the assembled briefing", async ({
  page,
}) => {
  test.skip(!bundle.briefing, "the plain-text edition needs a briefing");
  await page.goto("/text/");
  await expect(
    page.getByText(bundle.briefing!.briefing_md.split("\n\n")[0].slice(0, 60)),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /guided tour/i })).toHaveAttribute(
    "href",
    "/reading/",
  );
});
