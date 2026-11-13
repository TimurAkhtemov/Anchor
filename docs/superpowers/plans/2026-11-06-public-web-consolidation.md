# Anchor Public Web Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Streamlit with one Next.js "Morning paper" app, public and private, with an unattended weekday public refresh and real tickers kept off GitHub.

**Architecture:** Each world gets its own market-data bronze dataset. Exporters write one static JSON bundle per world. The same Next.js static export renders either bundle: the public one is committed and deployed by Vercel, and the private one is built under gitignored `var/` and served on localhost. GitHub Actions is a thin trigger over a testable Python script.

**Tech Stack:** Python 3.12, BigQuery, dbt (fusion locally, core 1.11 in CI), Next.js 16 static export, Playwright, GitHub Actions, Vercel, Anthropic SDK, local Ollama.

**Spec:** `docs/superpowers/specs/2026-11-06-public-web-consolidation-design.md`

**Visual reference:** tab B of `/Users/timurakhtemov/Programming/personal/Anchor/.superpowers/brainstorm/25995-1793967885/content/layouts.html`. It is a working mockup, so read its markup and CSS for layout. This path is in the main checkout, not a worktree.

## Global Constraints

- Real holdings or tickers may reach only SnapTrade, BigQuery, Yahoo, and local Ollama. Never a commit, public build, GitHub-hosted runner, public Actions log, Vercel, or the Claude API.
- Work in a git worktree on `feat/public-web`. The nightly private job runs from the main checkout and must not change until merge.
- Commit messages end with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01DPA2bSdAWvmCmx84iFecaQ`
- PR bodies end with: `🤖 Generated with [Claude Code](https://claude.com/claude-code)` and `https://claude.ai/code/session_01DPA2bSdAWvmCmx84iFecaQ`
- Read `web/AGENTS.md` and the relevant guide in `web/node_modules/next/dist/docs/` before writing code in `web/`.
- Read the `claude-api` skill before touching the Anthropic call.
- Run dbt from inside `transformation/`, never with `--project-dir` under fusion.
- Ollama is shared with a meeting recorder: use only `qwen3.6:35b`, and load no other model.
- Staleness threshold: 4 days. Settle cutoff: 21:30 ET.
- **STOP gates:** steps marked 🛑 need Timur. Never run a destructive BigQuery action, a push, or a merge without their go-ahead at that step.

## Review Focus

1. A holding or sector has a null return for a horizon: it shows "—", sorts last, and draws no sparkline rather than crashing or showing `NaN`. Task 6.
2. The bundle has `briefing: null`: `/` shows deterministic regime lines and no guided-reading link, and `/reading/` still builds with a pointer back. Tasks 6, 7, 8.
3. Every asset-class filter is switched off: the holdings area says nothing is selected and offers a way back, rather than going blank. Task 7.
4. The Anthropic call fails, or credits run out, mid-refresh: fresh numbers still publish, without narration. Task 9.
5. The private web build fails or is interrupted: the last good private site keeps serving, and `git status` stays clean. Task 11.

---

### Task 1: Yahoo reachability gate

Everything after this depends on it.

**Files:**
- Create: `scripts/probe_yahoo.py`, `.github/workflows/yahoo-probe.yml`

**Interfaces:**
- Produces: `public_tickers() -> set[str]` in `scripts/probe_yahoo.py`, the union of `transformation/seeds/benchmark_etfs.csv` and the tickers in `data/sample_portfolio.csv`, read from files only.

- [ ] **Step 0: Commit the design and this plan** as the first commit on `feat/public-web`.
- [ ] **Step 1: Write the probe.** No BigQuery import and no `ingestion.ingest_yfinance` import. For every ticker in `public_tickers()` fetch `yf.Ticker(t).history(period="5d")` and `.info`, plus `.news` for three tickers. Print one line per ticker. Exit non-zero if more than 10% return no price rows.
- [ ] **Step 2: Write the workflow.** Trigger: `push` to branch `probe/yahoo` only. Python 3.12, `pip install yfinance pandas`, no secrets, run the probe.
- [ ] **Step 3: 🛑 Push and read the result.** `git push origin HEAD:probe/yahoo`, then `gh run watch`.
  - Expected: exit 0 with prices, including mutual funds (`FXAIX`, `FXNAX`).
  - If it fails: stop and bring Timur the options. Do not start Task 2.
- [ ] **Step 4: Remove the probe.** Delete `.github/workflows/yahoo-probe.yml` and the remote branch. Keep `scripts/probe_yahoo.py` as a diagnostic. Commit: `chore(ops): Yahoo reachability probe`.

### Task 2: Regime boundary fix

**Files:**
- Modify: `transformation/macros/three_way_state.sql`, `transformation/models/marts/macro_regime.sql:37-39`
- Create: `transformation/tests/assert_regime_boundary_states.sql`

**Interfaces:**
- Produces: `three_way_state(delta_expr, threshold, label_up, label_down, label_mid, inclusive=false)`. `macro_indicators.direction` and `sector_performance.rate_comovement_label` keep their current behavior.

- [ ] **Step 1: Write the failing singular test.** A singular test on a literal table works on both dbt engines without mocks. Select rows where the macro output differs from `expected`:

| delta | threshold | inclusive | expected |
|---|---|---|---|
| 0.25 / -0.25 | 0.25 | true | up / down |
| 0.30 / -0.30 | 0.3 | true | up / down |
| 0.20 / -0.20 | 0.2 | true | up / down |
| 0.19 / -0.19 | 0.2 | true | mid / mid |
| 0.20 | 0.2 | false | mid |
| 0 | 0 | false | mid |

- [ ] **Step 2: Verify it fails.** From `transformation/`: `dbt test --select assert_regime_boundary_states`. Expected: FAIL, with the macro's unknown `inclusive` argument or mismatched rows.
- [ ] **Step 3: Implement.** Add `inclusive`, using `>=`/`<=` when true. Update the header comment. Pass `inclusive=true` from the three `macro_regime` calls.
- [ ] **Step 4: Verify.** `dbt build --select macro_regime macro_indicators sector_performance assert_regime_boundary_states` in the dev sandbox. Expected: PASS, and `labor_state` reads `tightening` while the delta stays exactly -0.20.
- [ ] **Step 5: Commit.** `fix(dbt): a move of exactly the threshold counts as a regime change`.

### Task 3: Separate market data per world

**Files:**
- Modify: `ingestion/ingest_yfinance.py`, `transformation/models/staging/yfinance/_src_yfinance.yml`, `scripts/private_daily.py` (the `market_prices` step), `tests/test_private_daily.py`
- Create: `tests/ingestion/test_yfinance_universe.py`

**Interfaces:**
- Produces: `DATASET_BY_WORLD = {"demo": "raw_yfinance", "real": "raw_yfinance_private"}`; `resolve_universe(bq_client, world: str = "demo") -> list[str]`; `ingest_yfinance(bq_client, world: str = "demo") -> dict`; CLI `python ingestion/ingest_yfinance.py --world demo|real` (default demo). Dagster's existing `ingest_yfinance(client)` call therefore stays demo-only.

- [ ] **Step 1: Write failing tests**, using a fake client that records query strings:
  - `test_demo_universe_never_queries_real_holdings`: no recorded query contains `holdings_real`.
  - `test_real_universe_reads_only_real_holdings`: queries `holdings_real`, not `holdings_demo`, and includes the seed ETFs.
  - `test_unknown_world_raises`: `ValueError`.
  - `test_ticker_list_is_never_logged`: with `caplog`, the resolved tickers do not appear in any log record.
  - `test_private_market_step_uses_real_world`: the `market_prices` step in `build_steps` contains `--world real`.
- [ ] **Step 2: Verify they fail.** `python -m pytest tests/ingestion/test_yfinance_universe.py tests/test_private_daily.py -q`.
- [ ] **Step 3: Implement.** `_held_tickers` takes the world and reads only that world's table. Replace the log line at `ingest_yfinance.py:123` with a count. Use the world's dataset throughout `ingest_yfinance`. Pass `--world real` from `private_daily.py`.
- [ ] **Step 4: Point the dbt source.** In `_src_yfinance.yml`: `schema: "{{ 'raw_yfinance_private' if var('holdings_source', 'demo') == 'real' else 'raw_yfinance' }}"`. Then `dbt parse` under fusion and dbt-core (`dbt-bigquery~=1.11` in a throwaway venv), and `dbt compile --target prod-private --vars '{holdings_source: real}' --select stg_yfinance__prices`. Expected: compiled SQL reads `raw_yfinance_private`.
- [ ] **Step 5: Run the tests.** Expected: PASS. Commit: `feat(ingestion): separate market data per world; never log tickers`.

### Task 4: Narrower public credential

**Files:**
- Create: `scripts/check_public_credential.py`, `docs/public_refresh_operations.md`, `tests/test_check_public_credential.py`

**Interfaces:**
- Produces: `check(client) -> list[str]`, returning the problems found. It requires `permission denied` on `raw_holdings.holdings_real`, `raw_holdings.fund_classifications_real`, `raw_yfinance_private`, and `anchor_marts_private`, and successful reads on `raw_holdings.holdings_demo`, `raw_yfinance`, `raw_fred`, `anchor_marts`.

- [ ] **Step 1: Test `check`** with a fake client: all denials correct returns `[]`; a readable `holdings_real` is reported; `NotFound` on a private table counts as not proven and is reported.
- [ ] **Step 2: Implement** the script, reading `GOOGLE_APPLICATION_CREDENTIALS` and exiting non-zero on problems.
- [ ] **Step 3: Write the runbook section.** `gcloud` isn't installed, so use Cloud Console steps. Create `anchor-public-refresh` with:
  - Project: `BigQuery Job User`.
  - `BigQuery Data Editor` on datasets `raw_yfinance`, `raw_fred`, `anchor`, `anchor_staging`, `anchor_intermediate`, `anchor_marts`, `anchor_seeds`, `anchor_snapshots`, `dbt_ci`.
  - `BigQuery Data Viewer` **on table** `raw_holdings.holdings_demo` only. That dataset also holds the real tables, so never grant at dataset level.
- [ ] **Step 4: 🛑 Timur creates the account** and downloads the key outside the repo. Then run `GOOGLE_APPLICATION_CREDENTIALS=<key> python scripts/check_public_credential.py`. Expected: exit 0. Any denial that blocks dbt surfaces in Task 12's first run, so record grant changes in the runbook.
- [ ] **Step 5: Commit.** `feat(ops): verify the public credential cannot read private data`. The GitHub secret swap happens in Task 12.

### Task 5: Briefing guard, current model call, and bake-off

**Files:**
- Modify: `app/briefing.py`, `app/generate_briefing.py`, `tests/app/test_briefing.py`

**Interfaces:**
- Produces:
  - `find_forward_looking(text: str) -> list[str]`, called from `validate_steps`.
  - `generate(portfolio, provider, client, *, skip_news=False, dry_run=False) -> dict`. `dry_run` skips the write and adds `"steps"` to the result.
  - CLI `generate_briefing.py --dry-run --out <path>`.
  - `DEFAULT_MODEL = "qwen3.6:35b"`, `DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"` until Timur picks.

- [ ] **Step 1: Write failing tests:**
  - `test_validate_steps_rejects_prediction`: a step containing "will provide a near-term catalyst" produces an error naming that step.
  - `test_validate_steps_rejects_recommendation`: "investors should buy" is rejected.
  - `test_forward_look_ignores_sell_off`: "a sell-off in energy" is not flagged.
  - `test_september_briefing_flags_only_the_apple_step`: frozen fixture of the steps from today's `anchor.json`; only step 6 is flagged. This pattern was already tried against that briefing and flagged only step 6.
  - `test_generate_retries_once_on_validation_failure`: fake provider, bad then good output, two calls, one write.
  - `test_generate_fails_after_second_invalid`: `ValidationError`, no write.
  - `test_dry_run_does_not_write`.
- [ ] **Step 2: Verify they fail.** `python -m pytest tests/app/test_briefing.py -q`.
- [ ] **Step 3: Implement.** Case-insensitive word-boundary phrases: `will`, `won't`, `going to`, `expected to`, `likely to`, `poised to`, `set to`, `should|could|may` + `rise|fall|continue|benefit|help|provide`, `buy`, `sell` (not `sell-off`), `trim`, `recommend*`. Retry only on `ValidationError`, not on API errors.
- [ ] **Step 4: Update `AnthropicProvider` per the skill.** Keep streaming and structured output, and set `output_config.effort` to `medium` alongside `format`. Remove the Opus 4.8 comments. Existing `is_local` and privacy tests must still pass.
- [ ] **Step 5: Run the tests and commit.** `feat(briefing): enforce no predictions, retry once, support dry runs`.
- [ ] **Step 6: 🛑 Bake-off.** Timur creates the Anthropic key, in its own Console workspace with a spend limit, and sets it in their shell only, never `.env`. Run with `ANCHOR_BRIEFING_PROVIDER=anthropic` and `--dry-run --out`, once each with `ANCHOR_BRIEFING_CLOUD_MODEL=claude-sonnet-5-5` and `claude-haiku-5-5`. Show Timur both narrations plus token usage and actual cost. He picks.
- [ ] **Step 7: Set the chosen default.** If Sonnet, add `fallbacks: "default"` with beta `server-side-fallback-2026-07-01` per the skill, and tell Timur. Haiku has no server-side fallback, so a refusal becomes a briefing failure. Commit.

### Task 6: Bundle export, validation, and dashboard selectors

**Files:**
- Create: `app/bundle_validation.py`, `tests/app/test_bundle_validation.py`, `web/src/lib/bundle.ts`, `web/src/lib/dashboard.ts`, `web/tests/dashboard-selectors.spec.ts`
- Modify: `app/export_web.py`, `tests/app/test_web_privacy.py`, `web/src/lib/types.ts`, `web/src/lib/resolve.ts`, `web/src/app/page.tsx`, `web/src/app/text/page.tsx`, `web/next.config.ts`

**Interfaces:**
- Produces, Python:
  - `export_web(client, out_path=BUNDLE_PATH, portfolio="demo") -> dict[str, int]`. Adds `portfolio`, `macro_trend: {key: [[date, value]]}`, and `ticker_trend: {ticker: [[date, close]]}`. `briefing` is `None` when the row is missing or its `as_of_date` differs from `as_of_calendar.as_of_date`. Raises `BundlePrivacyError`, defined in `app/export_web.py`.
  - `validate_bundle(bundle: dict, today: date | None = None) -> dict[str, int]` raising `BundleValidationError`. Moves `allowed_tickers`, `TICKER_COLUMNS`, and `MAX_SETTLED_AGE_DAYS = 4` from `snapshot_validation.py`, and adds trend keys to the ticker check.
- Produces, TypeScript:
  - `loadBundle(): AnchorBundle` reads `process.env.ANCHOR_BUNDLE_PATH ?? public/data/anchor.json` with `fs` at build time.
  - `AnchorBundle` gains `portfolio`, `macro_trend`, `ticker_trend`, and `briefing: Briefing | null`.
  - `type ReturnHorizon = "1m" | "ytd" | "1y"`.
  - In `dashboard.ts`: `sectorsFor(b, h)`, `trendWindow(b, ticker, h)`, `benchmarksFor(b, ticker)`, `allocation(b)`, `presentClasses(b)`, `heldByClass(b, cls)`, `rollup(b, h)`, `staleness(asOf: string, today: Date): { stale: boolean; days: number }`, `railContent(b): { kind: "narration"; text: string } | { kind: "regime"; summary: string; states: [string, string][] }`.

- [ ] **Step 1: Write failing Python tests:**
  - `test_real_portfolio_refuses_public_path`: `export_web(fake, BUNDLE_PATH, portfolio="real")` raises `BundlePrivacyError` before any query.
  - `test_real_portfolio_requires_var_dir`: any path outside repo `var/` raises.
  - `test_real_reads_private_dataset`.
  - `test_stale_briefing_exports_null`; `test_missing_briefing_table_exports_null`.
  - `test_validate_bundle_rejects_private_ticker`, including one only in `ticker_trend`.
  - `test_validate_bundle_rejects_stale_date` at 5 days; accepts 4.
  - `test_validate_bundle_accepts_null_briefing`.
  - `test_web_bundle_contains_only_demo_and_benchmark_tickers` also covers trends and tolerates a null briefing.
- [ ] **Step 2: Verify they fail, implement, verify they pass.** `python -m pytest tests/app -q`.
- [ ] **Step 3: Refresh the bundle** with `make export-web` from the local credential, so trends exist for the web work. Confirm `tests/app/test_web_privacy.py` passes, then commit the bundle.
- [ ] **Step 4: Write failing selector tests**, with small inline fixtures rather than the live bundle:
  - `sectorsFor` sorts descending for the horizon, with null returns last.
  - `trendWindow` starts at `as_of_calendar.date_<h>` and returns `[]` for an unknown ticker.
  - `rollup` counts `label_<h>` per axis and omits empty axes.
  - `presentClasses` keeps canonical order and lists only classes held.
  - `staleness`: 4 days not stale, 5 days stale.
  - `railContent` returns narration when a briefing exists, and the regime summary with its three states when `briefing` is null.
- [ ] **Step 5: Implement.** Set `trailingSlash: true` in `next.config.ts` so `/text/` and `/reading/` work on any static server. `page.tsx` and `text/page.tsx` use `loadBundle()`. `buildTourModel` is only called with a non-null briefing.
- [ ] **Step 6: Verify.** `cd web && npm run build && npm run typecheck && npm run test:e2e`. Update the `/text` path in `web/tests/tour.spec.ts` to `/text/`. Commit: `feat(web): trends in the bundle, bundle validation, dashboard selectors`.

### Task 7: The Morning paper dashboard

**Files:**
- Create: `web/src/components/dashboard/Dashboard.tsx` (client boundary, owns horizon and filter state), `Masthead.tsx`, `MacroSection.tsx`, `SectorsSection.tsx`, `HoldingsSection.tsx`, `marks/Sparkline.tsx`, `marks/DivergingBar.tsx`; `web/src/lib/guide.ts`; `web/src/app/reading/page.tsx`; `web/src/app/icon.svg`; `web/tests/dashboard.spec.ts`
- Modify: `web/src/app/page.tsx`, `web/src/app/layout.tsx`, `web/tests/tour.spec.ts`

**Interfaces:**
- Consumes: `dashboard.ts` and `loadBundle()` from Task 6; the `globals.css` tokens as they are.
- Produces: the dashboard at `/`, the tour at `/reading/`.

- [ ] **Step 1: Write failing browser tests in `dashboard.spec.ts`:**
  - h1 contains `macro_regime.regime_summary`; masthead shows the formatted as-of date and "Demo portfolio".
  - Clicking "1 Year" sets `aria-pressed="true"` and makes the first sector row match `sectorsFor(bundle, "1y")[0].etf_ticker`.
  - 4 macro columns, 11 sector rows, and one holding row per `portfolio_composition` row.
  - Clearing "Equities" removes that group's rows; clearing every class shows "No asset classes selected" with a reset control.
  - `page.clock.setFixedTime` 5 days past the as-of date shows "Data through"; the as-of date itself does not.
  - At 375px wide, `scrollWidth <= innerWidth`.
  - A "guided reading" link goes to `/reading/`.
- [ ] **Step 2: Verify they fail.** `cd web && npm run build && npx playwright test dashboard`.
- [ ] **Step 3: Build the components from mockup tab B**, using its layout and values. Requirements the mockup doesn't fully show:
  - `guide.ts` holds the full Quick Guide text from `app/app.py:150-175` and the per-card `help` text from `app/app.py:90-104`, shown in the "How to read this" disclosure.
  - Horizon drives everything except macro sparklines.
  - Null values show "—", with no `NaN`.
  - Controls use `aria-pressed` and a 34px minimum height; sparklines are `aria-hidden`.
  - Server-render the 1 Month view, so the page has content before hydration.
- [ ] **Step 4: Handle the two conditional states.** The stale notice is computed in the browser, after hydration only, to avoid a server/client mismatch. `briefing: null` shows `regime_summary` with the three states in the rail, in place of narration, and hides the guided-reading link.
- [ ] **Step 5: Move the tour.** `/reading/` renders `<Tour>` from `loadBundle()`. If the briefing is null it renders a short note linking to `/`. Set page metadata titles, and add an anchor `icon.svg`. Update `tour.spec.ts` to `/reading/`.
- [ ] **Step 6: Verify.** `npm run build && npm run typecheck && npm run lint && npm run test:e2e`. Expected: PASS.
- [ ] **Step 7: Look at it.** Screenshot `/` at 1360px and 390px and compare with the mockup. Check all three horizons and open the disclosure. Commit: `feat(web): Morning paper dashboard at /, tour moves to /reading/`.

### Task 8: Tighten the guided reading

**Files:**
- Modify: `web/src/components/tour/SceneShell.tsx`, `web/src/components/tour/scenes/HeroScene.tsx`, `CodaScene.tsx`, `web/src/lib/resolve.ts` (only if needed), `web/tests/tour.spec.ts`

**Interfaces:**
- Consumes: `bundle.portfolio` for the demo/private label.

- [ ] **Step 1: Write a failing test.** In `tour.spec.ts`, assert the document's total height is under `(steps + 2) * 0.8 * innerHeight`, and that a link back to `/` is visible on the coda. Keep the existing spotlight test.
- [ ] **Step 2: Implement.** Reduce sentinel and scene height from `100svh` to `70svh` and top-align the sticky content so scenes stop floating in empty space. Replace the hard-coded "demo portfolio" in `HeroScene` with the label from `bundle.portfolio`. Add the coda link back to the dashboard. The `-45%` observer margins should still fire, so confirm with the spotlight test.
- [ ] **Step 3: Verify.** `npm run build && npm run test:e2e`. Scroll through in a browser at both widths, and also build once with `ANCHOR_BUNDLE_PATH` pointing at a copy with `briefing: null` to confirm `/` and `/reading/` render. Commit: `fix(web): remove the tour's empty gaps; link back to the dashboard`.

### Task 9: Public refresh script and workflow

**Files:**
- Create: `scripts/public_refresh.py`, `tests/test_public_refresh.py`, `.github/workflows/public-refresh.yml`
- Modify: `Makefile` (add `public-refresh`; `refresh` calls it), `docs/public_refresh_operations.md`

**Interfaces:**
- Consumes: `export_web`, `validate_bundle`, `ingest_yfinance` default world, `generate_briefing.py`.
- Produces:
  - `should_generate_briefing(mart_as_of: str, bundle: dict | None) -> bool`.
  - `refresh(client, bundle_path, run_briefing, today=None) -> RefreshResult`, where `RefreshResult(changed: bool, as_of: str, briefing_status: "generated" | "reused" | "failed")`.
  - Writes `changed=true|false` to `$GITHUB_OUTPUT`.

- [ ] **Step 1: Write failing tests**, with fakes:
  - `test_new_date_generates_briefing`.
  - `test_same_date_with_briefing_spends_nothing`: `run_briefing` not called, bundle unchanged, `changed=False`.
  - `test_same_date_without_briefing_retries`.
  - `test_briefing_failure_still_publishes_numbers`: `run_briefing` raises, bundle is written with `briefing: None`, `changed=True`, status `failed`.
  - `test_validation_failure_writes_nothing`: bundle file unchanged and the error propagates.
  - `test_export_failure_keeps_old_bundle`: write to a temp file, then rename only after validation.
- [ ] **Step 2: Verify they fail, implement, verify they pass.** `python -m pytest tests/test_public_refresh.py -q`.
- [ ] **Step 3: Write the workflow.**
  - Triggers: `schedule: '45 2 * * 2-6'` (21:45 EST / 22:45 EDT, Mon–Fri evenings) and `workflow_dispatch` with input `publish` (boolean, default true).
  - `permissions: contents: write`, with a concurrency group.
  - Job env: `DBT_PROFILES_DIR=orchestration/dbt_profiles`, `BQ_SA_KEY`, `FRED_API_KEY`, `ANTHROPIC_API_KEY`, `ANCHOR_BRIEFING_PROVIDER=anthropic`, `GOOGLE_APPLICATION_CREDENTIALS=/tmp/anchor-bq-key.json`.
  - Steps: checkout, Python 3.12, install as `ci.yml` does, write key via env, `make ingest`, `make build-prod DBT=dbt`, `make public-refresh`, Node 22 with `npm ci`, `npm run build`, install Chromium, `npm run test:e2e`.
  - Commit only when `changed=true` and `publish` is true: `git add web/public/data/anchor.json` alone, message `chore(data): refresh public bundle to <as_of>`, and no force.
- [ ] **Step 4: Add a guard test.** `test_workflow_never_touches_real_world`: parse the YAML and assert no `--world real`, `SNAPTRADE`, `holdings_real`, or `prod-private` anywhere.
- [ ] **Step 5: Commit.** `feat(ops): weekday public refresh on GitHub Actions`. It can't run until Task 12.

### Task 10: Retire Streamlit and the parquet snapshot; move Dagster to the bundle

**Files:**
- Delete: `app/app.py`, `app/ui.py`, `app/trends.py`, `app/data.py`, `.streamlit/`, `app/export_snapshot.py`, `app/snapshot_validation.py`, `app/snapshot_publication.py`, `app/snapshot/`, `.github/workflows/dagster-plus-deploy.yml`, `dagster_cloud.yaml`, `tests/app/test_trends.py`, `tests/app/test_snapshot_validation.py`, `tests/app/test_snapshot_privacy.py`, `tests/orchestration/test_publication.py`
- Modify: `orchestration/anchor_orchestration/snapshot.py` (rename `web_bundle.py`), `definitions.py`, `tests/orchestration/test_definitions.py`, `tests/app/test_web_privacy.py`, `app/requirements.txt`, `Makefile`, `transformation/models/marts/_exposures.yml`

**Interfaces:**
- Consumes: `export_web`, `validate_bundle`.
- Produces: Dagster asset `web_bundle`, deps as `snapshot_parquet` had, plus the same `DEMO_REFRESH_SELECTION` scope. The schedule stays stopped by default.

- [ ] **Step 1: Check for other callers before deleting.** `git grep -nE "from app\.|import data\b|app/data|trends|export_snapshot|snapshot_validation|snapshot_publication|app/snapshot"`. `app/briefing.py` must not depend on any deleted file. Resolve each hit.
- [ ] **Step 2: Update the failing test first.** `test_definitions.py` expects `web_bundle` and no `publish_snapshot`.
- [ ] **Step 3: Implement.** Move `_allowed_tickers` use in `test_web_privacy.py` to `bundle_validation.allowed_tickers`. Remove `streamlit` and `altair` from `app/requirements.txt`. Remove `snapshot`, `run-real`, `run-demo`; add `dev-web`. Replace the `streamlit_dashboard` exposure with a `web_dashboard` exposure, with the URL filled in at Task 12, depending on the same marts plus `macro_trend` and `ticker_trend`.
- [ ] **Step 4: Verify.** `python -m pytest tests/ -q`, `python -m compileall -q app ingestion orchestration`, and `dbt parse`. Expected: PASS. Then load Definitions locally, as CI's pytest does. Commit: `refactor: retire Streamlit and the parquet snapshot; Dagster serves the bundle`.

### Task 11: The real portfolio on the same app

**Files:**
- Create: `scripts/private_web.py`, `tests/test_private_web.py`
- Modify: `scripts/private_daily.py`, `scripts/private_services.py`, `web/next.config.ts`, `tests/test_private_daily.py`, `tests/test_private_services.py`, `docs/private_daily_operations.md`

**Interfaces:**
- Produces:
  - `Step(name, command, cwd=None, soft: bool = False)`.
  - A status state `"degraded"`, with `last_success_at` still updated.
  - `build_private_site(bundle_path: Path, root: Path = var/private_web) -> Path`, building to `root/build-<ts>` and atomically repointing the symlink `root/current`, keeping the previous target on failure.
  - The dashboard LaunchAgent runs `venv/bin/python -m http.server 8501 --bind 127.0.0.1 --directory var/private_web/current`.

- [ ] **Step 1: Write failing tests:**
  - `test_steps_order`: `snaptrade_holdings`, `fred`, `market_prices`, `private_marts`, `private_briefing` (soft), `private_bundle`, `private_site`.
  - `test_soft_failure_marks_degraded_and_continues`; `test_hard_failure_stops_and_marks_failed`.
  - `test_failed_build_keeps_current_symlink`.
  - `test_dashboard_binds_loopback_only`: the plist has `--bind`, `127.0.0.1`, `8501`, and no `streamlit`.
  - `test_build_paths_stay_under_var`: `next build` env points dist output under `var/`.
- [ ] **Step 2: Verify they fail.** `python -m pytest tests/test_private_web.py tests/test_private_daily.py tests/test_private_services.py -q`.
- [ ] **Step 3: Implement.**
  - The site build must not write real data into `web/.next` or `web/out`. Read the `distDir` doc in `web/node_modules/next/dist/docs/` first. Use `ANCHOR_DIST_DIR`, or build from a copy of `web/` under `var/` if `distDir` cannot leave the project.
  - The private bundle path is `var/private_web/anchor.json`.
  - Resolve `npm` at install time, since LaunchAgents have a minimal `PATH`.
  - Update the privacy section of `docs/private_daily_operations.md`.
- [ ] **Step 4: Verify the privacy property.** With the demo bundle copied to `var/`, run `build_private_site`. Expected: `git status --porcelain` is unchanged and `web/out` and `web/.next` mtimes are unchanged. Commit: `feat(private): real portfolio runs on the web app, served on loopback`.

These tests prove the code. The live private run happens at merge in Task 12.

### Task 12: Go live

Each 🛑 is Timur's call. Sequence matters: the private job must stop writing real tickers to the shared tables before they are purged.

- [ ] **Step 1: 🛑 PR and merge.** Push `feat/public-web`, open a PR, confirm CI is green, merge. Nightly private runs now use their own market tables. Warn Timur first: merging removes `app/app.py`, so the Streamlit link shows an error from here until he deletes that app, and steps 1–8 should happen in one sitting.
- [ ] **Step 2: Fix the private model locally.** Change only the `ANCHOR_BRIEFING_MODEL` line in `.env` to `qwen3.6:35b`, without printing the file. Run `make bootstrap-private`, `make install-private-services`, `make refresh-private`. Expected: `make private-status` shows `success` or `degraded`, and `http://127.0.0.1:8501` shows the app labeled Private with current data. If SnapTrade, marts, or FRED fail, debug those separately.
- [ ] **Step 3: Clean public tables, audit first.** Run `make ingest` so `raw_yfinance` is demo-only. Then write and run read-only `scripts/audit_public_tables.py`: scan every table in the public datasets for columns in `TICKER_COLUMNS`, and report tickers outside `allowed_tickers()` per table. Also write local-only `scripts/scan_for_private_tickers.py <paths or --git-history>`: it reads real tickers from `raw_holdings.holdings_real`, searches for whole-word matches outside `allowed_tickers()`, and reports counts and file paths, never the tickers themselves. Common-word tickers need care.
- [ ] **Step 4: 🛑 Show Timur the audit.** On their go-ahead: `dbt build --select stg_yfinance__prices --full-refresh --target prod`, drop `anchor_snapshots.snap_yfinance_tickers`, `dbt snapshot --target prod`, `dbt build --target prod`. This resets the ticker metadata change history. Re-run the audit. Expected: no offenders.
- [ ] **Step 5: 🛑 Swap secrets.** Timur runs `gh secret set BQ_SA_KEY < <new key>` and `gh secret set ANTHROPIC_API_KEY`. Re-run CI on `main`. Expected: green, or adjust grants per the runbook.
- [ ] **Step 6: Trial run.** `gh workflow run public-refresh.yml -f publish=false`. Expected: green. Save the log with `gh run view --log` under `var/` and run `scan_for_private_tickers.py` on it. Expected: no matches.
- [ ] **Step 7: 🛑 Connect Vercel.** Timur imports the repo with root directory `web/` and the default address, and gives me the URL.
- [ ] **Step 8: Publish.** `gh workflow run public-refresh.yml -f publish=true`. Confirm one commit touching only the bundle, a Vercel deploy, and the live page showing the new as-of date, in a browser at both widths.
- [ ] **Step 9: Confirm the unattended run.** After the next scheduled time, confirm a run happened on its own. Do not call it finished before this.

### Task 13: Docs, claims, and leak scan

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `AGENTS.md`, `handoff.md`, `docs/architecture.md`, `docs/setup.md`, `docs/dagster_serverless_operations.md`, `docs/private_daily_operations.md`, `web/README.md`, `transformation/models/marts/_exposures.yml`, `site/index.html`, `.gitignore`

- [ ] **Step 1: Run the leak scan.** `scripts/scan_for_private_tickers.py` over all tracked files, including `site/index.html`, and with `--git-history`. 🛑 If anything is found, stop and show Timur privately.
- [ ] **Step 2: Update the docs.**
  - README: pitch, new live link, stack, removed limitation about the hand-triggered refresh, roadmap, and a clear note that Dagster is kept as a local learning graph while GitHub Actions runs production.
  - `CLAUDE.md`: Streamlit commands, briefing scope, data seam.
  - `docs/dagster_serverless_operations.md`: mark as historical.
  - `site/index.html`: regenerate with `dbt docs generate --static --target prod`, since its lineage still shows Streamlit, then re-run the leak scan on it.
  - `.gitignore`: add `.superpowers/`.
- [ ] **Step 3: Update the repo homepage.** `gh repo edit --homepage <vercel url>` and the exposure URL.
- [ ] **Step 4: Refresh `docs/images/anchor-dashboard.png`** with a real screenshot of the new site.
- [ ] **Step 5: Verify.** `python -m pytest tests/ -q`, `git grep -il streamlit` returns only intended history notes, and every README link opens. Commit, PR, 🛑 merge.
- [ ] **Step 6: 🛑 Timur finishes up.** Update the resume with the wording in the spec, then delete the Streamlit Cloud app. Afterward, confirm the old URL no longer serves the app and that nothing in the repo links to it.
