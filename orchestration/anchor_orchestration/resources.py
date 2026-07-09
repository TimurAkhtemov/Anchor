"""Dagster resources for the Anchor code location.

The BigQuery client is the single auth seam: locally it resolves Application
Default Credentials (GOOGLE_APPLICATION_CREDENTIALS -> the service-account
keyfile); in a Dagster cloud run you swap to a `gcp_credentials` secret instead
— config, not code. This also unifies the auth that the ingestion scripts and
the snapshot export each used to wire up separately.

The dbt resources point dagster-dbt at this repo's dbt project on the `prod`
target, so materializing the dbt assets runs `dbt build --target prod` into the
anchor_* datasets the dashboard reads.
"""
import json
from pathlib import Path

from dagster_dbt import DbtCliResource, DbtProject
from dagster_gcp import BigQueryResource

PROJECT_ID = "anchor-495115"
REPO_ROOT = Path(__file__).resolve().parents[2]

bigquery_resource = BigQueryResource(project=PROJECT_ID)

# Profiles live in ~/.dbt (where the `prod` target is defined), not the project
# dir. Setting profiles_dir + target on the DbtProject means both the manifest
# prep step (prepare_if_dev's internal `dbt deps`/`dbt parse`) and the runtime
# resource inherit them — so the parse uses --target prod and the asset keys
# carry the anchor_* prod schemas.
DBT_PROFILES_DIR = Path.home() / ".dbt"

# DbtProject regenerates the manifest from source on `dagster dev`
# (prepare_if_dev), so the Dagster asset graph never drifts from the dbt project.
dbt_project = DbtProject(project_dir=REPO_ROOT / "transformation", profiles_dir=DBT_PROFILES_DIR, target="prod")
dbt_project.prepare_if_dev()


def _drop_hook_nodes_for_dagster(manifest_path: Path) -> None:
    """Strip on-run-start/on-run-end hook ("operation") nodes from the parsed
    manifest before dagster-dbt reads it.

    dagster-dbt's asset-graph construction walks every manifest node through
    dbt-core's own NodeSelector, which unconditionally reads `node.config.enabled`.
    dbt-fusion (our local/CI engine) never populates `config` on operation nodes
    (the `assert_portfolio_isolation()` on-run-start hook in dbt_project.yml), so
    that read raises AttributeError and the whole Definitions object fails to
    load. Hooks aren't `ref()`-able resources — they run as a side effect of
    `dbt build`, not a materializable asset — so Dagster doesn't need to see them
    at all; dropping them from its copy of the manifest sidesteps the crash
    without touching how dbt itself builds. Idempotent and manifest is a
    gitignored build artifact, so this never touches version control.
    """
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text())
    nodes = manifest.get("nodes", {})
    hook_ids = [uid for uid, node in nodes.items() if node.get("resource_type") == "operation"]
    if not hook_ids:
        return
    for uid in hook_ids:
        del nodes[uid]
        manifest.get("parent_map", {}).pop(uid, None)
        manifest.get("child_map", {}).pop(uid, None)
    manifest_path.write_text(json.dumps(manifest))


_drop_hook_nodes_for_dagster(dbt_project.manifest_path)

dbt_resource = DbtCliResource(project_dir=dbt_project)
