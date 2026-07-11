"""Build the dbt manifest shipped with the Dagster+ code location."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = REPO_ROOT / "transformation"
PROFILES_DIR = Path(
    os.environ.get(
        "ANCHOR_MANIFEST_PROFILES_DIR",
        REPO_ROOT / "orchestration" / "dbt_profiles",
    )
)
MANIFEST_PATH = PROJECT_DIR / "target" / "manifest.json"


def drop_hook_nodes(manifest_path: Path = MANIFEST_PATH) -> None:
    """Remove dbt operation nodes that dagster-dbt cannot materialize."""
    manifest = json.loads(manifest_path.read_text())
    nodes = manifest.get("nodes", {})
    hook_ids = [
        unique_id
        for unique_id, node in nodes.items()
        if node.get("resource_type") == "operation"
    ]
    for unique_id in hook_ids:
        nodes.pop(unique_id, None)
        manifest.get("parent_map", {}).pop(unique_id, None)
        manifest.get("child_map", {}).pop(unique_id, None)
    manifest_path.write_text(json.dumps(manifest))


def main() -> None:
    command = [
        "dbt",
        "parse",
        "--project-dir",
        str(PROJECT_DIR),
        "--profiles-dir",
        str(PROFILES_DIR),
        "--target",
        "prod",
    ]
    subprocess.run(command, check=True)
    drop_hook_nodes()
    print(f"Prepared Dagster manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
