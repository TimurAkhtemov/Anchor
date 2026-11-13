# Anchor — Handoff

_Last updated: 2026-11-12._ The lean "current state + what's next" pointer. The
**`README.md` is the canonical project doc** (pitch, design decisions, limitations,
roadmap); the full inventory is `docs/architecture.md`; commands are `docs/setup.md`;
working style is `CLAUDE.md`. This file holds only what those don't: where things stand
today, operator steps still owed, deviations from the locked designs, and gotchas.

## Where things stand

- **Live and unattended (2026-11-12).** Public site <https://anchor-pi-five.vercel.app>
  (Vercel, root `web/`), refreshed Tue-Sat 10:00 UTC by GitHub Actions on the narrow
  `anchor-public-refresh` service account, briefing by Claude Sonnet. Private refresh
  Tue-Sat 06:00 ET by LaunchAgent, local Qwen briefing, site on `127.0.0.1:8501`.
  Streamlit (v1) is frozen on branch `streamlit-v1` at anchor-dashboard.streamlit.app;
  Dagster is retired (PR #19).
- **Both capstones shipped** (ops layer; "make it real" multi-asset holdings), plus the
  LLM briefing (PRs #5–#7), the immersive web tour (#8), and Daily Note phase ① (#9).
- **Landed 2026-09-18:** private daily ops (#10), Dagster+ Serverless deployment (#12),
  and a web-test fix (#11).
- **Private daily refresh is operating** (LaunchAgents from this checkout; Mon–Fri
  21:30 ET until 2026-11-11, now Tue–Sat 06:00 ET, PR #20). Since 2026-09-18 the data steps have passed nightly (154/154), but the
  **briefing step failed every night until 2026-11-06**: `.env` still named
  `gemma4:31b`, which had been removed from Ollama (`404`). Fixed by pointing the
  briefing at the resident llama-server (#16); verified end to end on the real
  portfolio the same day (first attempt passed the validator).
- **Landed 2026-11-06:** 60 s wall-clock deadline on every yfinance call (#15);
  llama-server provider + validation retries with rejection feedback (#16); gain
  since purchase shown next to market value, horizon column relabeled "Price Return"
  (#17). Local `.env` now: `ANCHOR_BRIEFING_PROVIDER=llama-server`.
- **Landed 2026-11-06 → 11-12:** one Next.js app for both worlds, Streamlit and Dagster
  retired, Claude briefing for the demo (#19); morning schedules (#20); public service
  account, Vercel, leak scanners, docs (this PR).

## Operator steps still owed (user-owned)

1. **Confirm the first morning runs**: `make private-status` after 06:00 ET, and a
   `chore(data)` commit plus Vercel deploy after 10:00 UTC.
2. **Old real-ticker rows in BigQuery time travel** (`dbt_ci`, dropped 2026-11-12) age
   out after 7 days; accepted rather than shortening the window.

## What's next (README roadmap order)

1. Reliable settled EOD data — `docs/ingestion_roadmap.md`, still deferred.
2. Grounded portfolio history — allocation drift, concentration, contribution.
3. **Daily Note phase ② — derived-signal marts** (`portfolio_rate_sensitivity`,
   `holding_attribution`, concentration signals). The next dbt-heavy build; design is
   locked in `docs/briefing_daily_note_design.md`. Phases ③–⑤ follow it.
4. Intent and reflection tools.

Scope decision in force: the real portfolio's briefing is local only (llama-server);
the demo's uses Claude via `AnthropicProvider`, which `build_provider` refuses for real
data.

## Lessons from the 2026-09-18 landing (each cost a red build)

- **The settle cutoff is 21:30 ET, not 18:30.** At 18:30 ETFs carry the session's bar
  while mutual funds (FXAIX, FXNAX) don't, so funds are null-priced at the common as-of
  date and `assert_source_valuation_is_intentional` +
  `not_null_holdings_benchmarks_relative_1m_pp` fail — correctly. One constant,
  `SESSION_SETTLED_ET` in `ingestion/ingest_yfinance.py`; the LaunchAgent and the Dagster
  cron must match it. Before the cutoff, ingestion drops today's bars, so a daytime
  `make ingest` is safe and yields yesterday's settled session.
- **Schedules moved to the morning (2026-11-11).** Even 21:30 ET raced Yahoo: on
  2026-11-10, 9 closes were still blank at 21:31 and the private build failed both
  guardrails above. Private now runs Tue-Sat 06:00 ET, public Tue-Sat 10:00 UTC; the
  cutoff constant stays, so a run before 21:30 still yields yesterday's session.
- **launchd `Weekday` is 0/7 = Sunday, 1 = Monday.** `range(2, 7)` was Tue–Sat, and the
  test pinned the same mistake.
- **Pin on frozen fixtures, assert invariants on live data.** `web/tests/resolve.spec.ts`
  pinned exact expectations against the committed bundle, whose briefing is
  LLM-generated; every refresh broke CI. Exact pins now use
  `web/tests/fixtures/anchor-2026-07.json`.
- **A model name in `.env` is a dependency.** Ollama models get pruned; the briefing
  then 404s nightly and the chain halts before the status file updates, so
  `make private-status` reports a stale `data_as_of` even though the marts are fresh.
  llama-server serves one fixed model and ignores the request's name, which removes
  that failure mode.
- **yfinance's 30 s timeout is not a wall-clock bound.** Calls stalled 4–15 min with 0
  bytes; `call_with_deadline` in `ingestion/ingest_yfinance.py` is the real cap.
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
- **Two local LLM servers hold the same 35B model** when both are warm (Ollama for the
  meeting recorder, llama-server for pi/Pendant + Anchor). Ollama is no longer needed
  by Anchor; drop it from Anchor's docs once nothing else depends on it.
- **Streamlit:** restarting the server drops open tabs' connections — hard-refresh.
- The `dbt_timurakhtemov` dev sandbox still holds orphaned dbt-tutorial tables; harmless.

## Design records in `docs/`

`make_it_real_design.md` (built) · `briefing_daily_note_design.md` (active arc) ·
`immersive_briefing_design.md`, `llm_copilot_briefing_design.md` (built) ·
`ingestion_roadmap.md` (deferred) · `holdings_ingestion.md`,
`multi_asset_benchmarking.md` (superseded, history only) ·
`private_daily_operations.md`, `dagster_serverless_operations.md` (runbooks).
