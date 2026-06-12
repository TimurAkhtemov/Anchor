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
dbt_project = DbtProject(project_dir=REPO_ROOT, profiles_dir=DBT_PROFILES_DIR, target="prod")
dbt_project.prepare_if_dev()

dbt_resource = DbtCliResource(project_dir=dbt_project)
