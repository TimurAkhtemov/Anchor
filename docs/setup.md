# Setup and run

**Prerequisites:** a Google BigQuery project and service-account key, a `FRED_API_KEY`
in `.env`, the `anchor` dbt profile in `~/.dbt/profiles.yml`, a Python venv. Keep the
repo outside iCloud-synced folders.

## The pipeline by hand

```bash
# 1. Python deps + ingestion (writes bronze tables to BigQuery)
pip install -r ingestion/requirements.txt
python ingestion/ingest_fred.py
make ingest-holdings-demo             # committed sample portfolio -> raw_holdings.holdings_demo
python ingestion/ingest_yfinance.py   # ticker universe derives from held tickers + benchmark ETFs

# 2. dbt packages + build + test (run from the dbt project in transformation/)
cd transformation
dbt deps
dbt build                  # dev: into the personal sandbox (demo holdings by default)
dbt build --target prod    # prod: into the anchor_* datasets
cd ..

# 3. serve layer: export the bundle, then run the site
make export-web            # marts -> web/public/data/anchor.json
make dev-web               # Next.js dev server against that bundle
```

Run dbt from inside `transformation/`. The local engine is dbt-fusion, whose
`--project-dir` flag mishandles seed paths, so `cd` in first. Useful selectors:

```bash
dbt build --select staging
dbt build --select marts
dbt show --inline "select * from {{ ref('holdings_benchmarks') }}" --limit 20
```

## Make targets

The Makefile is the tool-agnostic step list; GitHub Actions and the LaunchAgent only trigger it.

| Target | What it does |
|---|---|
| `make ingest` | FRED + yfinance → bronze (full refresh) |
| `make ingest-holdings-demo` | committed sample portfolio → `raw_holdings.holdings_demo` |
| `make ingest-holdings-real` | Fidelity export + private fund classes → `raw_holdings.holdings_real` |
| `make build-prod` | `dbt build --target prod` (demo holdings, public datasets) |
| `make build-private` | `dbt build --target prod-private --vars '{holdings_source: real}'` |
| `make briefing` / `make briefing-real` | generate the LLM briefing (`briefing-real` is local-only by construction) |
| `make export-web` | export marts + briefing → `web/public/data/anchor.json` |
| `make public-refresh` | briefing (new settled date only) → validated bundle; what the GitHub job runs |
| `make refresh` | the full demo chain: ingest → build-prod → public-refresh |
| `make refresh-private` / `make private-status` | the real-portfolio chain, and its last result |
| `make dagster` | the retired Dagster asset graph, kept as a record (localhost:3000) |

`make refresh` only touches the demo world. Real-portfolio builds
are never part of any scheduled *public* path: they run manually (`make build-private`) or
through the separate local-only weekday service described below.

## Real portfolio (local only, never in the public deploy)

Drop a Fidelity positions export at `data/private/fidelity_positions.csv` (gitignored)
plus a `fund_classifications_real.csv`, then:

```bash
make ingest-holdings-real && make build-private
```

This builds into `anchor_*_private`, isolated from every public target by the
compile-time interlock. Or connect live: run `python ingestion/snaptrade_connect.py`
once, then `python ingestion/ingest_holdings.py --from-snaptrade --portfolio real`
(requires the SnapTrade secrets in `.env`).

For daily private use, run `make bootstrap-private`, then `make install-private-services`.
This installs a Tue-Sat 06:00 ET refresh (previous weekday's close) and a localhost-only real dashboard at
<http://127.0.0.1:8501>. `make private-status` shows the last result; append
`--skip-briefing` to the private runner during a temporary local-model conflict. Full
operations and privacy contract: `docs/private_daily_operations.md`.

## Briefing

```bash
python app/generate_briefing.py --portfolio demo   # writes copilot_briefing; needs Ollama
```

Optional `.env` config: `ANCHOR_BRIEFING_PROVIDER` (`ollama` default | `llama-server` |
`anthropic`), `ANCHOR_BRIEFING_MODEL` (Ollama only; default `gemma4:31b`), `OLLAMA_HOST`,
`ANCHOR_LLAMA_SERVER_HOST` (default `http://127.0.0.1:8080`), `ANCHOR_BRIEFING_ATTEMPTS`,
`ANCHOR_BRIEFING_PROVIDER` (`ollama` default; the `anthropic` cloud path is dormant and
structurally refuses the real portfolio).

## Web tour

```bash
python app/export_web.py                       # refresh the committed data bundle
cd web && npm ci && npm run dev                # local dev
cd web && npm run build && npm run test:e2e    # static export to out/ + Playwright smoke
```

Read `web/AGENTS.md` before changing code there; the Next.js version differs from what
most references describe.

## Orchestration

```bash
pip install -r orchestration/requirements.txt
make dagster               # materialize holdings/ingest -> dbt -> snapshot from the UI
```
