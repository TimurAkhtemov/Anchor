# Anchor: one web app, running on its own

_Design, 2026-11-06. Supersedes the Dagster+ activation and "Vercel connect" items in `handoff.md`._

## Intent

Timur wants to finish Anchor and stop thinking about it. Anyone who opens the link
should see a polished, current dashboard, with no sleep screen, no stale-data banner,
and no sign of unfinished work. Anchor is also a portfolio piece for analytics
engineering roles, so what the README and resume claim must stay true.

Today the public link opens Streamlit's "gone to sleep" page, data stops at 2026-09-08,
the `web/` tour has never been deployed, and the two surfaces have diverged in design.

## Goals

1. One Next.js app replaces Streamlit everywhere, public and private.
2. The dashboard uses the "Morning paper" design Timur chose, with every Streamlit
   feature below, plus the existing guided reading in the same design.
3. The public demo refreshes itself every weekday through GitHub Actions and redeploys,
   with no action from Timur.
4. The real portfolio runs on the same app on their Mac, with its data never leaving it.

## Non-goals

Chat. The rest of the roadmap: Daily Note phases ②–⑤, portfolio history, intent tools,
paid EOD data, more brokers, multi-user. Intraday data. Dark mode (the paper identity is
light-only by design).

## Anti-goals: failure even if it technically works

- Real holdings or real tickers reach a commit, a public build, a GitHub-hosted runner,
  public Actions logs, Vercel, or the Claude API. The private path's existing services
  (SnapTrade, BigQuery, Yahoo, local Ollama) are the only places they may go.
- A pipeline failure leaves the site looking broken rather than merely dated.
- The site needs monthly attention to keep running.
- The briefing predicts or recommends. The resume says it never does.
- Green and red, or gains and losses, become the emotional center of the page.

## Decisions Timur made

- **Design:** B, "Morning paper". Reference mockup, working and using real data:
  `.superpowers/brainstorm/25995-1793967885/content/layouts.html` (second tab).
- **Scheduler:** GitHub Actions. Dagster stays in the repo for local and experimental
  use, and the README describes it as a learning part of the project.
- **Public briefing:** Claude, at the lowest reasonable cost.
- **Streamlit:** retired for the real portfolio too, so everything is on one stack. The
  public app is deleted once links point to the new site, and the site uses the default
  Vercel address.
- **No chat.**
- **Market data:** public and private use separate tables, and the public job uses a
  narrower credential.
- **Regime states:** a move of exactly the threshold counts as a change.

## What the dashboard must contain

Reading order is fixed: macro, then sectors, then holdings. All interaction runs in the
browser against one static JSON bundle.

- **Masthead:** Anchor, settled as-of date, and "Demo portfolio" (or "Private" on the
  Mac). The regime summary is the page headline.
- **Horizon toggle:** 1 Month / YTD / 1 Year. It drives every return, comparison,
  sector and holding sparkline, sort order, and rollup, using the `as_of_calendar` windows
  so a sparkline can never contradict the return beside it. Macro sparklines stay at their
  full series, as in the mockup: monthly indicators have too few points over one month.
- **Briefing:** first narration beside the headline, with a link to the guided reading.
- **Macro:** four indicators with value, 3-month change, sparkline, and regime state,
  plus a "How to read this" disclosure carrying the full text of the Streamlit Quick
  Guide and the per-card help text.
- **Sectors:** all 11, sorted by return for the chosen horizon, each with a diverging
  bar, return, sparkline, and measured correlation with rates plus its label. This
  replaces the "rate-sensitive" tag, which 10 of 11 sectors carried.
- **Holdings:** allocation band, per-axis ahead/behind/in-line rollup, asset-class filter
  (only classes actually held), and rows grouped by class. Each row shows ticker, name,
  sector and cap or duration, value, weight, return, each benchmark comparison with its
  label, and a sparkline overlaid with the first benchmark. Root holdings read as a
  reference point; unbenchmarked rows say so; import-valued rows are marked.
- **Guided reading:** the existing scroll tour moves to its own route, keeps its
  step-driven scenes, loses the large empty gaps, and matches the new page. `/text`
  stays as the plain-text fallback.
- **Staleness:** the browser compares the as-of date with today, so a quiet "Data through
  <date>" notice still appears if the pipeline has died. Threshold stays at 4 days.
- **Phone:** no horizontal scrolling at 375px, as the mockup already demonstrates.

## Public pipeline

Weekday GitHub Actions run after the 21:30 ET settle, in the existing order: ingest →
`dbt build --target prod` → briefing → export → web build and browser tests → one commit
touching only the bundle → Vercel deploys. Pipeline logic stays in the Makefile, with
Actions as a thin trigger. Use a cron time that is past 21:30 ET in both EST and EDT.

- **Commits from the workflow may not trigger CI**, so the workflow itself must validate
  the bundle and run the web build and tests before committing.
- **Nothing new, nothing spent:** if the settled as-of date hasn't changed (holidays),
  skip the model call and the commit.
- **Bundle validation:** extend the existing `app/snapshot_validation.py` checks to the
  bundle (allowed tickers only, required sections non-empty, settled date sane).
- **Bundle contents:** add `macro_trend` and `ticker_trend` to `app/export_web.py`.

**The first task is a test, not a build:** fetch prices from a GitHub-hosted runner using
only seed and demo tickers, with no BigQuery access and no call to the current universe
function. Yahoo may block cloud IPs, and the whole schedule depends on this. If it fails,
stop and bring the options to Timur.

### Separating the two worlds' market data

`ingest_yfinance.py` currently builds one universe from `holdings_demo` and `holdings_real`,
logs the full ticker list, and truncates tables both worlds share. On a public runner that
would publish real tickers. Timur's decision is to separate them:

- **Public ingestion** reads no real holdings table. Its universe is the demo portfolio
  plus benchmark ETFs, written to public market-data tables.
- **Private ingestion** writes to its own dataset. `prod-private` dbt sources read from
  there, selected by the existing `holdings_source` var. Neither job can truncate the
  other's rows, however their schedules overlap.
- **Public credential:** the workflow uses a new, narrower service account with no access
  to `holdings_real`, `fund_classifications_real`, or `anchor_*_private`. The demo dbt path
  doesn't read those tables. `BQ_SA_KEY`, which appears to be the Mac's key, is replaced in
  GitHub by the narrower one, so CI gets the same reduced access. IAM has not been checked.
- **One-time cleanup:** `stg_yfinance__prices` merges and never deletes, and the ticker
  snapshot keeps history, so the public datasets probably still hold real tickers. Query
  first to confirm. Purging means rebuilding those tables, which resets the snapshot's
  change history. Show Timur what will be dropped and get their go-ahead before running it.
- **Local Dagster** calls this same ingestion, so it moves to the demo-only universe. This
  also makes true the claim in its docs that the code location has no real-holdings access.

### When a step fails

- **Ingest, dbt, validation, or web tests fail:** nothing is published and the last good
  site keeps serving.
- **Only the briefing fails:** publish the fresh numbers anyway, with deterministic
  regime lines in place of narration and the guided-reading link hidden. This reverses
  the current strict "briefing failure halts the chain" policy, on purpose: fresh numbers
  with no narration beat a site going stale because credits ran out.

## Public briefing

- Use the existing `AnthropicProvider`, which is already structurally demo-only.
  `ANTHROPIC_API_KEY` lives only in GitHub secrets. Read the `claude-api` skill before
  touching the call; the provider's request shape dates from Opus 4.8.
- **Model:** generate one briefing with `claude-sonnet-5-5` and one with
  `claude-haiku-5-5` from the same data. Timur picks after reading both. Estimated cost
  per run is about $0.05 and $0.002 respectively (estimate, not yet measured).
- **Cadence:** every weekday, not weekly. Step figures are validated verbatim against
  the data and the tour's spotlights match them, so a weekly narration would contradict
  the numbers beside it.
- **Enforce "never predicts":** today only the prompt forbids it, and the live briefing
  contains "will provide a near-term catalyst". Add a hard validation check. Use that
  sentence as a test fixture. One retry, then treat as a briefing failure.
- **Credits:** Timur's plan may include monthly API credits, which must be claimed by
  linking a Console organization. Credits are shared across that organization, so give
  Anchor its own workspace with a spend limit.

## Private portfolio

Same app, same design, built on the Mac. The weekday private job becomes SnapTrade →
market data → `prod-private` → local briefing → private bundle → private static build →
atomic swap. The existing localhost service serves it on `127.0.0.1:8501`, keeping the
same address, and never binds to anything else.

Privacy rules, stronger than the current ones, which say the private runner writes no web
bundle at all (`docs/private_daily_operations.md` must be updated to match):

- The private bundle and build live only in gitignored `var/`. Nothing real is ever
  written to `web/public/`, `web/out/`, or `web/.next/`, including build caches.
- `app/export_web.py` must refuse any combination of real data and the public path. A
  test proves it, in the same spirit as `assert_portfolio_isolation`.
- A real-portfolio build leaves `git status` clean; this gets a test or a checked step.
- The private briefing stays local. The `build_provider` guard is unchanged.

The configured briefing model is `gemma4:31b`, which is no longer installed, and last
night's run failed on a 404 from Ollama at that step. Use `qwen3.6:35b`, the resident
model, which generated the September briefing now in the snapshot. Earlier failures also
hit SnapTrade, marts, and FRED, so watch one full scheduled run before calling it fixed.
Ollama is shared with Timur's meeting recorder; don't load other models.

The "never predicts" check and the briefing failure policy apply here too: if only the
local briefing fails, the Mac dashboard still gets fresh numbers without narration, and
`private_daily` records a degraded status rather than failing the whole run.

## Retiring Streamlit

Once the new site is live on its default Vercel address and the README and repo homepage
point to it, Timur deletes the Streamlit Cloud app. There is no "moved" page: it would show
the sleep screen to anyone arriving cold, so old links simply stop working. No custom domain.

The Streamlit code goes too (`app.py`, `ui.py`, `trends.py`, `data.py`, `.streamlit/`, and
their tests, after checking for other callers). `app/briefing.py`, `generate_briefing.py`,
and the exporters stay. The parquet snapshot retires with it.

Dagster stays runnable locally, so its serve assets must move to the web bundle rather
than break. The dormant `dagster-plus-deploy.yml` workflow is removed.

## Regime-state bug

Unemployment's 3-month change of −0.20 pp reads "stable", but the guide says 0.20 or more
is "tightening". The cause is confirmed in code: `transformation/macros/three_way_state.sql`
uses strict `>` and `<`, and the delta is already rounded to 2dp upstream, so a move of
exactly the threshold falls into the neutral state. It is not floating-point noise.
Rates and inflation use the same macro, so a clean 25 bp Fed move would read "steady",
contradicting the "~one 25bp move" intent in `dbt_project.yml`.

Timur's decision: a move of exactly the threshold counts as a change, matching the guide.
The macro also serves `macro_indicators.direction` (threshold 0, where an exact 0 must stay
"flat") and the sector co-movement label, so the fix must not change those. Add an
`inclusive` argument, default false, passed as true by the three `macro_regime` calls.
Pin it with a test at exactly ±0.25, ±0.30, and ±0.20, plus an in-band value such as 0.19.
Check that the test form works under both dbt-fusion and dbt-core. None of this has been
run yet.

The demo headline becomes "Rates steady, inflation cooling, labor tightening", and exports
and the briefing pick this up on their next run. The frozen web test fixture stays frozen.

## Docs and claims to bring in line

README (pitch, stack, limitations, roadmap, the Dagster learning note, live links),
`CLAUDE.md`, `handoff.md`, `docs/architecture.md`, `docs/setup.md`,
`docs/private_daily_operations.md`, `_exposures.yml`, and the repo homepage URL.

Suggested resume changes, for Timur to make: "→ Streamlit" becomes "→ Next.js", and the
LLM bullet covers both worlds (local model on the private portfolio, Claude on the public
demo, validated so it explains and never predicts).

## Only Timur can do

- Connect the repo to Vercel (root directory `web/`, default address).
- Create the narrower Google service account, with a walkthrough, and replace the secret.
- Create the Anthropic key, add it as a GitHub secret, and set the spend limit.
- Read the two sample briefings and pick a model.
- Approve the one-time public-table cleanup after seeing what it would drop.
- Update the resume, then delete the Streamlit Cloud app.

## Honest limits

Yahoo data is scraped with no guarantee. GitHub can delay scheduled runs, and disables
schedules after 60 days without repository activity, which a long outage could reach.
So "never think about it again" really means: if it breaks, the site stays up, says how
old its data is, and GitHub emails them.

## Left to the builder

Component structure, chart implementation (inline SVG as in the mockup is fine), how the
private build swaps its data source, static file server choice for localhost, exact cron
time, the forward-looking phrase check's wording, and test design. Heed `web/AGENTS.md`:
this Next.js has breaking changes, so read its bundled docs before writing code.

## Calls made without Timur

- Vercel as host, carried over from the September plan.
- Dashboard at `/`, guided reading on its own route.
- Publishing fresh numbers when only the briefing fails.
- Weekday cadence for the briefing, per the reasoning above.
- Removing the Dagster+ deploy workflow and retiring the parquet snapshot.
- Macro sparklines ignoring the horizon toggle.
- The "never predicts" check and failed-briefing behavior applying on the Mac too.
- Where real tickers may and may not go, as worded in the anti-goals.
