"""Serve-layer asset: export, validate, and write the web bundle.

Downstream of the marts the web app renders, web_bundle exports the demo marts plus
the briefing row to one JSON bundle, validates it, and writes
web/public/data/anchor.json. Local only: it publishes nothing. Publication is the
GitHub Actions public refresh.
"""
import json
import shutil
import tempfile
from pathlib import Path

from dagster import AssetKey, MaterializeResult, MetadataValue, asset
from dagster_gcp import BigQueryResource

from app.bundle_validation import validate_bundle
from app.export_web import BUNDLE_PATH, export_web

# copilot_briefing is a serve-layer table written outside dbt by the local-LLM
# workflow. The bundle carries it, but there is no dbt asset to depend on.
_MART_DEPS = [
    AssetKey(["anchor_marts", table])
    for table in (
        "macro_indicators",
        "macro_regime",
        "macro_trend",
        "sector_performance",
        "holdings_benchmarks",
        "portfolio_composition",
        "ticker_trend",
        "as_of_calendar",
    )
] + [AssetKey("source_freshness")]


@asset(
    name="web_bundle",
    deps=_MART_DEPS,
    group_name="serve",
    compute_kind="python",
    description="Validated demo web bundle written to web/public/data/anchor.json (local only; publishes nothing).",
)
def web_bundle(context, bigquery: BigQueryResource) -> MaterializeResult:
    with tempfile.TemporaryDirectory(prefix="anchor-bundle-") as temporary:
        staged = Path(temporary) / "anchor.json"
        with bigquery.get_client() as client:
            export_web(client, staged)
        bundle = json.loads(staged.read_text())
        counts = validate_bundle(bundle)
        shutil.copyfile(staged, BUNDLE_PATH)

    context.log.info(f"Web bundle wrote {counts}")
    return MaterializeResult(
        metadata={
            "total_rows": MetadataValue.int(sum(counts.values())),
            **{f"rows.{key}": MetadataValue.int(n) for key, n in counts.items()},
            "as_of_date": str(bundle["as_of_calendar"]["as_of_date"]),
        }
    )
