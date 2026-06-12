# orchestration/ — Dagster code location

The whole Anchor pipeline as **one software-defined asset graph**:

```
ingest_fred ─────┐
                 ├──→ staging ──→ intermediate ──→ marts ──→ snapshot_parquet
ingest_yfinance ─┘   (dbt: silver)   (dbt: silver)   (dbt: gold)   (serve)
        bronze
```

This is the artifact plain dbt docs can't produce: dbt's lineage stops at its own
`source()`/`ref()` boundary, so it can't show that the `raw_*` tables come from Python
ingestion or that a parquet snapshot hangs off the marts. Dagster models all of it as
assets, so the graph is **continuous bronze → silver → gold → serve**.

## Run it

```bash
make dagster      # from the repo root, with the venv active
```

Opens the Dagster UI at <http://localhost:3000>. Click **Materialize all** to run
`ingest → dbt build → snapshot` in dependency order, or open **Lineage** for the graph.
The `make dagster` target sets the env this needs:

| Env | Why |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | BigQuery auth for ingestion + snapshot (the `BigQueryResource`) |
| `DBT_PROFILES_DIR=~/.dbt` | where the dbt `prod` target is defined |
| `DAGSTER_HOME` | persistent run history (`orchestration/.dagster_home`, gitignored) |
| `PYTHONPATH=orchestration` | makes the `anchor_orchestration` package importable |

The daily schedule (`daily_refresh`, weekday 18:30 ET post-close) is **stopped by
default** — toggle it on in the UI. v1 runs locally; it does not run unattended.

## Layout

| File | Responsibility |
|---|---|
| `anchor_orchestration/definitions.py` | the `Definitions` Dagster loads: assets + job + schedule + resources |
| `anchor_orchestration/resources.py` | `BigQueryResource` (the auth seam) + `DbtProject`/`DbtCliResource` (prod target) |
| `anchor_orchestration/ingestion.py` | `ingest_fred` / `ingest_yfinance` `@multi_asset`s → the 4 bronze nodes |
| `anchor_orchestration/dbt.py` | `@dbt_assets` + `AnchorDbtTranslator` (source→bronze wiring, layer grouping) |
| `anchor_orchestration/snapshot.py` | `snapshot_parquet` `@asset`, downstream of the marts |

## Design decisions

- **In-process assets, not subprocess.** Each asset imports the existing
  `ingest_*(client)` / `export_snapshot(client)` function and calls it with a client from
  the `BigQueryResource`. This future-proofs the roadmap: new sources (SnapTrade holdings)
  reuse the one resource; partitioned/incremental loads pass config into the functions;
  data-quality checks emit from the returned row counts; a cloud deploy swaps resource
  config, not code. The scripts keep their `main()` CLI, so `make ingest` / CI are
  untouched.
- **The source→bronze wiring trick.** dbt sources are normally phantom upstream nodes
  nothing fills. `AnchorDbtTranslator.get_asset_key` maps each source (`fred.raw_fred_series`,
  …) onto the *same* key the bronze `@multi_asset` produces (`raw_fred_series`, …), fusing
  ingestion and dbt into one graph.
- **One BigQuery auth seam.** A single `BigQueryResource` replaces the per-script client
  setup (and the snapshot script's separate bare client). Local = ADC/keyfile; cloud =
  `gcp_credentials` secret.
- **Manifest never drifts.** `DbtProject.prepare_if_dev()` regenerates the dbt manifest
  (`dbt parse --target prod`) under `dagster dev`, so the asset graph always matches the
  dbt project.

## Follow-up: Dagster+ Serverless

Local `dagster dev` gives the asset graph but doesn't run unattended. Dagster+ Serverless
(free tier, same code) is the live scheduled story. It needs a **build-time** manifest
(`dagster-dbt project prepare-and-package`, since `prepare_if_dev` only fires locally) and
the `gcp_credentials` secret wired to the `BigQueryResource`. The `git push` that refreshes
the live Streamlit demo from the new snapshot stays a separate step — Dagster materializes
the parquet, not the commit.

> The `dbt` executable on PATH is `dbt-fusion 2.0 preview`; it parses/builds fine on the
> `prod` target and emits a harmless deferral-manifest 404 warning.
