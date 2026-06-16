# Dagster Orchestration — A Study Review

A walkthrough of the Dagster orchestration layer built for Anchor — written to (a) actually
understand what's in `orchestration/`, and (b) be able to talk about it in an AE interview.
Read top to bottom; each section builds on the last.

> **How deep should an AE know Dagster?** Aim for **working fluency + a strong narrative**,
> not internals.
> - **Know well:** the asset model, `dagster-dbt`, resources, schedules, and how to read/extend the code here.
> - **Know exists:** code locations, Dagster+ vs OSS, sensors, partitions, asset checks.
> - **Skip for now:** the execution engine, IO managers, gRPC plumbing.

---

## 1. The mental model: software-defined assets

Everything in Dagster collapses to one idea you already half-know from dbt.

**An asset is a *thing that persists in storage and has value*** — a BigQuery table, a parquet
file, an ML model. A *thing*, not a *task*. You write a function that **produces** an asset and
**declare its dependencies**; Dagster reads those declarations and builds the lineage graph.
You never hand-wire a DAG — you declare assets and the DAG falls out.

You already think this way in dbt: a model is an asset, `ref()`/`source()` declares a
dependency, dbt assembles the build order. Dagster generalizes that **past SQL** — a Python
script that writes a BigQuery table is an asset; a parquet export is an asset. So the whole
pipeline (Python ingestion + dbt + export) becomes **one** asset graph instead of three
disconnected tools.

**vs. Airflow** (the other name you'll hear): Airflow is **task-centric** — you schedule "run
script A, then B," and the data the tasks write is a side effect Airflow never sees. To classic
Airflow this project is ~4 opaque boxes. Dagster is **asset-centric** — every one of the 19
nodes *is* a table or file, each with its own status (last materialized, row count, freshness,
checks passed).

| Question | Airflow (task-centric) | Dagster (asset-centric) |
|---|---|---|
| Did tonight's run succeed? | ✅ | ✅ |
| When was `holdings_benchmarks` last refreshed, from which run? | ✖️ no concept of it | ✅ click the asset |
| Is `macro_trend` stale because FRED updated but dbt didn't re-run? | ✖️ | ✅ flagged stale |
| Rebuild just the marts, skip ingestion | hard (re-run tasks) | one click |
| Show everything downstream of `raw_yfinance_prices` | ✖️ | ✅ that *is* the graph |

**Honest nuance** (use it; don't oversell): Airflow has added data-awareness — "Datasets"
(2.4+), renamed "Assets" in Airflow 3 — and Dagster still runs *tasks* underneath. The real
difference is the **organizing primitive**: Airflow began with tasks and bolted assets on;
Dagster began with assets and derives the tasks.

**Why orchestrate at all** (vs. the `Makefile`/cron): an orchestrator gives you four things a
Makefile can't — the **graph**, **observability**, **scheduling + retries**, and **partial
re-runs**. The Makefile *runs* steps; the orchestrator *understands* them.

---

## 2. The refactor: making the scripts *callable* as assets

A Dagster asset is a *function it calls*. The ingestion scripts weren't callable — they were
standalone CLIs (`main()` builds its own client, `sys.exit(1)`s on error, all behind
`if __name__ == "__main__"`). So the logic had to become **importable** first.

(The design fork: *subprocess* — shell out to the untouched script, but Dagster only sees exit
codes/stdout — vs. *in-process* — import and call a function, which hands Dagster row counts,
config, and injected resources. We chose **in-process** for the roadmap.)

```python
# Before: a CLI only
def main():
    client = bigquery.Client(...)     # builds its own client
    ...; sys.exit(1) on error         # hard-exits the process

# After: logic + entrypoint, cleanly split
def ingest_fred(client) -> dict:      # ← the logic Dagster calls
    ...
    return {"raw_fred_series": n1, "raw_fred_observations": n2}   # row counts
def main():                           # ← CLI still works: make ingest / CI unchanged
    client = build_bigquery_client()
    ingest_fred(client)
```

Three changes, each with a reason:
1. **Extract `ingest_fred(client)` that *takes* a client and *returns* counts.** Taking the
   client as an argument is **dependency injection** — the caller decides where it comes from
   (Dagster injects a resource; the CLI builds its own). Returning counts populates the asset
   metadata.
2. **`raise` instead of `sys.exit(1)`.** `sys.exit` in a library kills the whole process — it
   would take Dagster down. An exception lets Dagster fail *just that asset* and show where.
3. **Keep client-building + logging setup behind `main()`.** So merely *importing* the module
   has no side effects.

> **Reusable lesson (not a Dagster trick):** split the **logic** (a function that takes its
> dependencies as arguments and returns results) from the **entrypoint** (builds dependencies,
> calls logic, handles exit). One split makes the same code drivable by a CLI, a test, *and* an
> orchestrator.

---

## 3. Scaffold, resource, and the bronze assets

**A. The scaffold = a "code location."** Dagster loads a module exposing one `Definitions`
object — the registry of everything (assets, resources, jobs, schedules). It's Dagster's
`dbt_project.yml`. Lives in `orchestration/anchor_orchestration/definitions.py`; `pyproject.toml`
points `dagster dev` at it; `__init__.py` puts the repo root on `sys.path` so assets can
`import ingestion.ingest_fred`.

**B. The resource = the auth seam.** A **resource** is a shared, configurable dependency Dagster
*injects* into assets. We used `BigQueryResource(project="anchor-495115")`. Before, each script
built its own client three different ways; now **one** place authenticates. Local → ADC/keyfile;
cloud → swap to a credentials secret, *no asset changes*. Auth is config, not scattered code.

**C. The bronze `@multi_asset`s.** Each script writes *two* tables per run, so the construct is
`@multi_asset` (one function → several assets):

```python
@multi_asset(outs={"raw_fred_series": AssetOut(...), "raw_fred_observations": AssetOut(...)})
def ingest_fred_asset(context, bigquery: BigQueryResource):   # ← resource injected by name
    with bigquery.get_client() as client:
        counts = ingest_fred(client)                          # ← the refactored fn
    yield MaterializeResult("raw_fred_series",       metadata={"rows": counts["raw_fred_series"]})
    yield MaterializeResult("raw_fred_observations", metadata={"rows": counts["raw_fred_observations"]})
```

The asset keys are deliberately the **raw table names** — the hook §4 grabs.

Mental model so far: **asset (a table) ← produced by a function ← which receives a resource.**

---

## 4. dbt as assets, fused onto bronze (the heart)

**A. `@dbt_assets` — one decorator, the whole project.** dbt already has a dependency graph (the
`manifest.json`). `dagster-dbt` reads it and creates one asset per node (13 models + the seed),
lineage already derived. The decorated function is the *execution recipe*:

```python
@dbt_assets(manifest=..., dagster_dbt_translator=AnchorDbtTranslator())
def anchor_dbt_assets(context, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
```

Because it's `dbt build`, the **78 tests run too and surface as asset checks**.

**B. `DbtProject` + `DbtCliResource`.** Same resource idea, for dbt:
`DbtProject(project_dir=…, profiles_dir=~/.dbt, target="prod")` packages which project/profile/
target. Materializing runs `dbt build --target prod` into the `anchor_*` datasets.
`prepare_if_dev()` regenerates the manifest under `dagster dev` so the graph can't drift.

**C. The translator — the wiring trick (the crux).** `dagster-dbt` loads models *and* their
`source()`s as nodes — but the sources are phantom upstream nodes nothing produces. Meanwhile
the bronze `@multi_asset` produces a key named `raw_fred_series`. Two disconnected islands. The
fix is a `DagsterDbtTranslator` overriding one method:

```python
class AnchorDbtTranslator(DagsterDbtTranslator):
    def get_asset_key(self, props):
        if props["resource_type"] == "source":
            return AssetKey(props["name"])      # dbt source name == bronze key
        return super().get_asset_key(props)     # models keep their default key
    def get_group_name(self, props):
        ...                                     # staging/intermediate→silver, marts→gold
```

> **Dagster merges graphs by asset-key *identity*.** Two definitions that reference the same
> `AssetKey` *are the same node.*

So the dbt source `fred.raw_fred_series` resolves to the key `raw_fred_series` — the exact key
the bronze asset produces. The phantom source and the bronze node collapse into one, and the
islands fuse into a continuous graph: `raw_* → stg_* → int_* → marts`. (The source `name` was
verified against the real manifest *before* writing the translator — that's why the keys line
up instead of silently missing.)

---

## 5. The snapshot asset, the job, and the schedule

**A. The snapshot asset — declaring a dependency Dagster can't infer.** `export_snapshot` got the
§2 treatment. It's a plain `@asset` downstream of the marts. But it reads them through a raw SQL
string Dagster can't see into, so the link is declared explicitly:

```python
@asset(deps=[AssetKey(["anchor_marts", t]) for t in TABLES])   # explicit deps on the marts
def snapshot_parquet(context, bigquery: BigQueryResource):
    with bigquery.get_client() as client:
        counts = export_snapshot(client)
    return MaterializeResult(metadata={...})    # writes parquet itself → just record it
```

Note the keys are `anchor_marts/<table>` — `dagster-dbt` prefixes model keys with their schema.

> Dependencies are **implicit** (dbt graph, function inputs) until the link crosses something
> Dagster can't introspect — a SQL string, a side-effecting write — then you **declare** it.

**B. The job.** `define_asset_job("anchor_refresh", selection=AssetSelection.all())` — a
selectable, schedulable slice of the graph. A schedule triggers a *job*, not loose assets.
Order is read from the lineage (ingest in parallel → dbt → snapshot).

**C. The schedule.**
```python
ScheduleDefinition(job=anchor_refresh_job,
                   cron_schedule="30 18 * * 1-5",                 # weekdays 6:30pm ET, post-close
                   execution_timezone="America/New_York",
                   default_status=DefaultScheduleStatus.STOPPED)  # off until toggled on
```
`STOPPED` by default is the safe choice. **Caveat:** locally it only ticks while `dagster dev`
runs — it won't fire unattended on a laptop. That's the Dagster+ Serverless follow-up.

All of it lands in the registry: `Definitions(assets=[...], jobs=[...], schedules=[...], resources={...})`.

---

## 6. How we verified, and the two bugs (most AE-real section)

**The verification ladder (cheapest check first)** — three different questions:
1. **Does it load?** `dagster definitions validate` — import errors, duplicate/unresolved keys.
2. **Is it shaped right?** introspect the asset graph in Python; print each asset's parents to
   *prove the edges* (e.g. `stg_fred__observations` → `raw_fred_observations`) before running
   anything expensive.
3. **Does it run?** materialize against BigQuery — cheap node first, then the full graph.

> Never let "the definitions validate" stand in for "the pipeline works." Different claims.

**War story 1 — the `profiles_dir` chase.** Symptom: `DbtCliResource … does not contain a
profiles.yml` (profiles live in `~/.dbt`, not the project root). Passing `profiles_dir` to the
*resource* fixed the runtime but `prepare_if_dev()` failed identically — it builds its own
internal resource. Root cause (found by reading the dagster-dbt source): the internal resource
**inherits `profiles_dir` from the `DbtProject`**, which had defaulted to the project root. Fix:
set `profiles_dir` on the **`DbtProject`** — both paths inherit it (and `target="prod"` too).
**Lesson:** when a fix only half-works, there are two code paths; set config at the **highest
shared level**.

**War story 2 — the manifest-drift `KeyError`.** Symptom: a dbt-asset run died with
`KeyError: 'test.anchor.assert_holdings_benchmarked…'` — dagster-dbt got a test result whose ID
wasn't in the manifest it loaded. Root cause: **manifest drift** — the CLI test ran outside
`dagster dev`, so `prepare_if_dev()` no-op'd and a stale committed manifest was used.
**Lesson:** the manifest is a **build artifact that must be current** (dev regenerates it; a
cloud deploy needs a build-time `prepare-and-package` step). "Works in one entrypoint, breaks in
another" → suspect environment/build-state, not your code.

**The AE takeaway:** both bugs were *integration/config/build-state*, not logic. That's the
texture of orchestration work — credentials, profiles, manifests, targets, the seams between
tools.

---

## 7. The interview narrative (~2 minutes, all defensible)

> "I built a macro-aware investment dashboard called Anchor — but the analytics-engineering
> point is the *pipeline*, not the charts. FRED and yfinance flow into BigQuery as raw tables,
> dbt transforms them through staging and intermediate layers into relationship-framed marts,
> and Streamlit serves them.
>
> Once dbt was solid, the missing piece was orchestration — the pipeline only existed as a
> Makefile of steps. I picked Dagster over Airflow or cron because Dagster is *asset-centric*:
> you declare the data objects and it derives the run graph, instead of scheduling opaque tasks.
> That matches how dbt already thinks, so it generalized across my Python ingestion *and* my dbt
> models.
>
> The part I'm proudest of: ingestion and dbt were two disconnected graphs. dbt knows its models
> depend on 'sources,' but has no idea those sources come from my Python scripts. So I wrote a
> small translator that maps each dbt source onto the asset key my ingestion produces — and
> since Dagster merges nodes by key identity, that one mapping fused everything into a single
> lineage graph, from raw ingestion through to the served snapshot.
>
> I also chose to run ingestion *in-process* rather than shelling out, so the orchestrator can
> pass config, capture row counts, and inject one shared BigQuery client — which sets up cleanly
> for adding real brokerage holdings later.
>
> Most of the work wasn't the SQL — it was integration seams: dbt profiles, manifest freshness,
> credentials. I verified each layer separately — does it load, is the graph shaped right, does
> it run — which is how I caught a manifest-drift bug before it ever hit a schedule. It runs
> locally today; next step is Dagster's serverless tier for the unattended run."

**20-second version:** *"I orchestrated a FRED/yfinance → dbt → Streamlit pipeline as a single
Dagster asset graph — including a translator that fuses my Python ingestion and dbt models into
one continuous lineage that neither tool shows alone."*

**Follow-up ammo:**
- *Why Dagster over Airflow?* Asset vs. task primitive; dbt-native. Hedge: "Airflow added
  data-aware scheduling — Datasets, now Assets in v3 — but Dagster's built around it."
- *Why not cron / GitHub Actions?* A cron runs steps; an orchestrator understands them — graph,
  stale-awareness, observability, partial re-runs. (CI stays on GitHub Actions — CI ≠ orchestration.)
- *What was hard?* The two war stories in §6 — both integration bugs, not logic.
- *What's next?* Dagster+ Serverless; then partitioned/incremental loads and dbt source-freshness checks.

**Delivery tip:** technical interviewer → lead with the translator/key-identity trick.
Broader AE/manager conversation → lead with the "turn a modeling project into a running,
observable data product" arc, and keep the translator as the depth you go to when they lean in.

---

## Concept glossary (one-liners)

| Term | One-liner |
|---|---|
| **Asset** | A persistent data object (table/file) you declare how to produce. |
| **`@asset` / `@multi_asset`** | A function that produces one / several assets. |
| **Asset key** | The asset's identity; same key in two places = same node. |
| **Resource** | A shared, injected dependency (a DB client, the dbt CLI). |
| **`Definitions`** | The registry Dagster loads — assets + resources + jobs + schedules. |
| **Code location** | A module exposing a `Definitions` (here, `anchor_orchestration`). |
| **`@dbt_assets`** | Loads every dbt model/seed from the manifest as an asset. |
| **`DagsterDbtTranslator`** | Customizes how dbt nodes map to Dagster (keys, groups). |
| **Job** | A selectable, schedulable slice of the asset graph. |
| **Schedule** | A cron trigger over a job. |
| **Asset check** | A data-quality assertion on an asset (your dbt tests). |
| **Materialize** | Run the function to (re)produce an asset. |

## Run it

```bash
make dagster          # UI at localhost:3000; Materialize all = ingest -> dbt -> snapshot
```
See `orchestration/README.md` for the env it sets and the design decisions.
