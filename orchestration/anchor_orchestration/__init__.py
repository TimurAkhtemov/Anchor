"""Anchor Dagster code location: FRED/yfinance -> bronze -> dbt -> snapshot.

The ingestion + snapshot assets import the existing repo-root packages
(`ingestion/`, `app/`). Put the repo root on sys.path so those imports resolve
no matter where `dagster dev` is launched from.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Re-export the code location's Definitions so `dagster dev -m anchor_orchestration`
# (and the pyproject `[tool.dagster] module_name`) resolve it. Imported here —
# after the sys.path insert — so the downstream `ingestion.*` imports it pulls in
# can find the repo-root packages.
from anchor_orchestration.definitions import defs  # noqa: E402

__all__ = ["defs"]
