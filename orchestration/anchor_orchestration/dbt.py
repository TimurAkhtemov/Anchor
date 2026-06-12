"""dbt models as Dagster assets, stitched onto the bronze ingestion layer.

`@dbt_assets` auto-loads every model/seed in the manifest as an asset and derives
their lineage from dbt's own ref/source graph. The translator does two things:

  1. get_asset_key — maps each dbt source() (fred.raw_fred_series, ...) onto the
     SAME asset key the bronze ingestion multi_assets produce (raw_fred_series,
     ...). dbt sources are normally phantom upstream nodes nothing fills; this
     makes the bronze assets fill them, fusing ingestion + dbt into one graph.
  2. get_group_name — clusters models by warehouse layer (folder) so the graph
     reads bronze -> silver (staging/intermediate) -> gold (marts).
"""
from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

from anchor_orchestration.resources import dbt_project

_LAYER_GROUPS = {"staging": "silver", "intermediate": "silver", "marts": "gold"}


class AnchorDbtTranslator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            # Source table name == the bronze ingestion asset key it feeds.
            return AssetKey(dbt_resource_props["name"])
        return super().get_asset_key(dbt_resource_props)

    def get_group_name(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "seed":
            return "seeds"
        fqn = dbt_resource_props.get("fqn", [])
        layer = fqn[1] if len(fqn) > 1 else ""
        return _LAYER_GROUPS.get(layer)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=AnchorDbtTranslator(),
)
def anchor_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """Run `dbt build` (models + tests) on the prod target; tests surface as
    asset checks in the Dagster UI."""
    yield from dbt.cli(["build"], context=context).stream()
