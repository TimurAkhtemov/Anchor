import json

from orchestration.prepare_manifest import drop_hook_nodes


def test_drop_hook_nodes_preserves_materializable_nodes(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "nodes": {
            "operation.anchor.guard": {"resource_type": "operation"},
            "model.anchor.example": {"resource_type": "model"},
        },
        "parent_map": {"operation.anchor.guard": [], "model.anchor.example": []},
        "child_map": {"operation.anchor.guard": [], "model.anchor.example": []},
    }))

    drop_hook_nodes(path)

    manifest = json.loads(path.read_text())
    assert set(manifest["nodes"]) == {"model.anchor.example"}
    assert "operation.anchor.guard" not in manifest["parent_map"]
    assert "operation.anchor.guard" not in manifest["child_map"]


def test_cloud_profile_exposes_only_public_prod_target():
    profile = (
        __import__("pathlib").Path(__file__).parents[2]
        / "orchestration/dbt_profiles/profiles.yml"
    ).read_text()
    assert "service-account-json" in profile
    assert "BQ_SA_KEY" in profile
    assert "prod-private" not in profile
    assert "holdings_source" not in profile
