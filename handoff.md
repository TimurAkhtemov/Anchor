# Anchor — Handoff

_Last updated: 2026-09-18._ The lean "current state + what's next" pointer. The
**`README.md` is the canonical project doc** (pitch, design decisions, limitations,
roadmap); the full inventory is `docs/architecture.md`; commands are `docs/setup.md`;
working style is `CLAUDE.md`. This file holds only what those don't: where things stand
today, operator steps still owed, deviations from the locked designs, and gotchas.

## Where things stand

- **Bronze → silver → gold → serve is built, tested, and green.** CI on `main`
  (2026-09-18): pytest + `dbt build --target ci` + Playwright all pass.
- **Both capstones shipped** (ops layer; "make it real" multi-asset holdings), plus the
  LLM briefing (PRs #5–#7), the immersive web tour (#8), and Daily Note phase ① (#9).
- **Landed 2026-09-18:** private daily ops (#10), Dagster+ Serverless deployment (#12),
  and a web-test fix (#11).
- **Private daily refresh is operating.** LaunchAgents reinstalled from this checkout
  2026-09-18 (Mon–Fri 21:30 ET; the old iCloud-synced `~/Desktop` worktree is removed).
  A manual `refresh --skip-briefing` that day passed `prod-private` 154/154 with data
  as of 2026-09-17 — the first private success since 2026-08-29, after the old
  18:30 Tue–Sat schedule raced mutual-fund NAVs and failed ~13 of 18 runs. The first
  *scheduled* run, and the first with the briefing step, had not yet been observed.
- Serverless is *code-complete but not yet operating* — see the next section.

## Operator steps still owed (user-owned)

1. **Confirm the first scheduled private run** with `make private-status` (expect
   `state: success` and a fresh briefing in the localhost dashboard).
2. **Activate Dagster+ Serverless** per `docs/dagster_serverless_operations.md`. The
   deploy workflow is dormant until repo variable `DAGSTER_CLOUD_ORGANIZATION` (+ secret
   `DAGSTER_CLOUD_API_TOKEN`) is set — runbook step 1.
3. **Vercel connect for `web/`** + the public-URL swap.

## What's next (README roadmap order)

1. Unattended post-close operation — built; blocked only on operator step 2 (Dagster+).
2. Reliable settled EOD data — `docs/ingestion_roadmap.md`, still deferred.
3. Grounded portfolio history — allocation drift, concentration, contribution.
4. **Daily Note phase ② — derived-signal marts** (`portfolio_rate_sensitivity`,
   `holding_attribution`, concentration signals). The next dbt-heavy build; design is
   locked in `docs/briefing_daily_note_design.md`. Phases ③–⑤ follow it.
5. Intent and reflection tools.

Scope decision still in force: the briefing stays **local (Ollama)** until public
deployment; the `AnthropicProvider` is dormant-but-ready and structurally demo-only.

## Lessons from the 2026-09-18 landing (each cost a red build)

- **The settle cutoff is 21:30 ET, not 18:30.** At 18:30 ETFs carry the session's bar
  while mutual funds (FXAIX, FXNAX) don't, so funds are null-priced at the common as-of
  date and `assert_source_valuation_is_intentional` +
  `not_null_holdings_benchmarks_relative_1m_pp` fail — correctly. One constant,
  `SESSION_SETTLED_ET` in `ingestion/ingest_yfinance.py`; the LaunchAgent and the Dagster
  cron must match it. Before the cutoff, ingestion drops today's bars, so a daytime
  `make ingest` is safe and yields yesterday's settled session.
- **launchd `Weekday` is 0/7 = Sunday, 1 = Monday.** `range(2, 7)` was Tue–Sat, and the
  test pinned the same mistake.
- **Pin on frozen fixtures, assert invariants on live data.** `web/tests/resolve.spec.ts`
  pinned exact expectations against the committed bundle, whose briefing is
  LLM-generated; every refresh broke CI. Exact pins now use
  `web/tests/fixtures/anchor-2026-07.json`.
- **CI builds share one `dbt_ci` dataset.** Concurrent runs double-load seeds and fail
  `unique` tests spuriously; the build job now has a cross-ref concurrency group.

## Honest deviations from the locked designs

From `docs/make_it_real_design.md`:
- **SnapTrade became the primary real-data transport** before a real Fidelity export
  ever went through the CSV parser — the CSV real-path is unverified against export drift.
- **Commodity + alt classes were added mid-build** (the real portfolio had both); they
  forced the explicit `valuation_source` split and are display-only in v1.
- **The common as-of calendar is anchored to the benchmark-ETF set**, not the full
  priced universe, so one holding's oddball bar can't move the date for everyone.
- **Classification is an override table, not a pure derivation** — no metadata source
  can classify what a fund holds inside.

## Gotchas

- **dbt-fusion locally, dbt-core in CI.** Run fusion from *inside* `transformation/`
  (`--project-dir` mishandles seed paths). The two engines can't share
  `transformation/dbt_packages/` — keep one engine locally. Fusion's deferral-manifest
  404 and package warnings are harmless.
- **dagster-dbt crashes on fusion's hook nodes** (null `config` on `on-run-start`
  operations); `orchestration/anchor_orchestration/resources.py` strips them from
  Dagster's parsed manifest copy. The Serverless build-time manifest uses dbt-core and
  `orchestration/prepare_manifest.py`.
- **`stg_yfinance__prices` is an incremental merge and never deletes.** If a partial bar
  ever lands, it won't self-heal: `dbt build --select stg_yfinance__prices
  --full-refresh`.
- **Ingestion modes:** FRED/yfinance are `WRITE_TRUNCATE` full refreshes; holdings are
  `WRITE_APPEND` (banks `as_of` history by design).
- **The private refresh log can contain the FRED API key** (a failed request's URL is
  logged verbatim). It stays in gitignored `var/`, but the log sanitizer covers only
  SnapTrade SDK errors today.
- **Streamlit:** restarting the server drops open tabs' connections — hard-refresh.
- The `dbt_timurakhtemov` dev sandbox still holds orphaned dbt-tutorial tables; harmless.

## Design records in `docs/`

`make_it_real_design.md` (built) · `briefing_daily_note_design.md` (active arc) ·
`immersive_briefing_design.md`, `llm_copilot_briefing_design.md` (built) ·
`ingestion_roadmap.md` (deferred) · `holdings_ingestion.md`,
`multi_asset_benchmarking.md` (superseded, history only) ·
`private_daily_operations.md`, `dagster_serverless_operations.md` (runbooks).
