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
import os
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Iterator

from dagster import EnvVar
from dagster_dbt import DbtCliResource, DbtProject
from dagster_gcp import BigQueryResource
from google.cloud import bigquery
from google.oauth2 import service_account

from orchestration.prepare_manifest import drop_hook_nodes

PROJECT_ID = "anchor-495115"
REPO_ROOT = Path(__file__).resolve().parents[2]

IS_DAGSTER_CLOUD = bool(os.environ.get("DAGSTER_CLOUD_DEPLOYMENT_NAME"))

class AnchorBigQueryResource(BigQueryResource):
    """BigQuery resource sharing dbt's raw service-account JSON secret."""

    service_account_json: str | None = None

    @contextmanager
    def get_client(self) -> Iterator[bigquery.Client]:
        if not self.service_account_json:
            with super().get_client() as client:
                yield client
            return
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.service_account_json)
        )
        yield bigquery.Client(
            project=self.project,
            location=self.location,
            credentials=credentials,
        )


bigquery_resource = (
    AnchorBigQueryResource(project=PROJECT_ID, service_account_json=EnvVar("BQ_SA_KEY"))
    if IS_DAGSTER_CLOUD
    else AnchorBigQueryResource(project=PROJECT_ID)
)

# Profiles live in ~/.dbt (where the `prod` target is defined), not the project
# dir. Setting profiles_dir + target on the DbtProject means both the manifest
# prep step (prepare_if_dev's internal `dbt deps`/`dbt parse`) and the runtime
# resource inherit them — so the parse uses --target prod and the asset keys
# carry the anchor_* prod schemas.
DBT_PROFILES_DIR = (
    REPO_ROOT / "orchestration" / "dbt_profiles"
    if IS_DAGSTER_CLOUD
    else Path(os.environ.get("DBT_PROFILES_DIR", Path.home() / ".dbt"))
)

# DbtProject regenerates the manifest from source on `dagster dev`
# (prepare_if_dev), so the Dagster asset graph never drifts from the dbt project.
dbt_project = DbtProject(project_dir=REPO_ROOT / "transformation", profiles_dir=DBT_PROFILES_DIR, target="prod")
dbt_project.prepare_if_dev()


if dbt_project.manifest_path.exists():
    drop_hook_nodes(dbt_project.manifest_path)

dbt_resource = DbtCliResource(project_dir=dbt_project)
