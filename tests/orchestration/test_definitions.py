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
    assert {"holdings_demo", "source_freshness", "web_bundle"} <= keys
    assert "snapshot_parquet" not in keys and "publish_snapshot" not in keys
    assert not any("private" in key or "real" in key or "snaptrade" in key for key in keys)


def test_schedule_is_stopped_by_default(monkeypatch):
    for deployment in (None, "branch-pr-123", "prod"):
        if deployment is None:
            monkeypatch.delenv("DAGSTER_CLOUD_DEPLOYMENT_NAME", raising=False)
        else:
            monkeypatch.setenv("DAGSTER_CLOUD_DEPLOYMENT_NAME", deployment)
        assert schedule_default_status() == DefaultScheduleStatus.STOPPED


def test_bigquery_resource_uses_one_raw_json_secret():
    resource = AnchorBigQueryResource(project="example", service_account_json='{"type":"service_account"}')
    assert resource.service_account_json == '{"type":"service_account"}'
    assert resource.gcp_credentials is None
