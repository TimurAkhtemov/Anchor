from dagster import DefaultScheduleStatus, Definitions

from anchor_orchestration.definitions import (
    DEMO_REFRESH_SELECTION,
    defs,
    schedule_default_status,
)
from anchor_orchestration.resources import AnchorBigQueryResource


def test_definitions_load_and_demo_job_excludes_private_assets():
    Definitions.validate_loadable(defs)
    keys = {
        key.to_user_string()
        for key in DEMO_REFRESH_SELECTION.resolve(defs.get_repository_def().asset_graph)
    }
    assert {"holdings_demo", "source_freshness", "snapshot_parquet", "publish_snapshot"} <= keys
    assert not any("private" in key or "real" in key or "snaptrade" in key for key in keys)


def test_schedule_runs_only_in_prod_deployment(monkeypatch):
    monkeypatch.delenv("DAGSTER_CLOUD_DEPLOYMENT_NAME", raising=False)
    assert schedule_default_status() == DefaultScheduleStatus.STOPPED
    monkeypatch.setenv("DAGSTER_CLOUD_DEPLOYMENT_NAME", "branch-pr-123")
    assert schedule_default_status() == DefaultScheduleStatus.STOPPED
    monkeypatch.setenv("DAGSTER_CLOUD_DEPLOYMENT_NAME", "prod")
    assert schedule_default_status() == DefaultScheduleStatus.RUNNING


def test_bigquery_resource_uses_one_raw_json_secret():
    resource = AnchorBigQueryResource(project="example", service_account_json='{"type":"service_account"}')
    assert resource.service_account_json == '{"type":"service_account"}'
    assert resource.gcp_credentials is None
