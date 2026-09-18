"""Atomic GitHub publication for the validated public snapshot set."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PublicationResult:
    status: str
    commit_sha: str | None = None
    files: int = 0


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


def _request(token: str, method: str, url: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "anchor-dagster-snapshot-publisher",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _snapshot_files(snapshot_dir: Path) -> dict[str, bytes]:
    paths = sorted(snapshot_dir.glob("*.parquet"))
    metadata = snapshot_dir / "publication.json"
    if not paths or not metadata.exists():
        raise ValueError("validated snapshot parquet and publication.json are required")
    return {
        f"app/snapshot/{path.name}": path.read_bytes()
        for path in [*paths, metadata]
    }


def publish_snapshot(
    snapshot_dir: Path,
    token: str,
    repository: str = "TimurAkhtemov/Anchor",
    branch: str = "main",
    api_base: str = "https://api.github.com",
    request_fn: Callable[[str, str, str, dict | None], dict] = _request,
) -> PublicationResult:
    """Create one commit from the current branch head; retry one head race."""
    files = _snapshot_files(snapshot_dir)
    ref_url = f"{api_base}/repos/{repository}/git/ref/heads/{branch}"

    for attempt in range(2):
        base_commit = request_fn(token, "GET", ref_url, None)["object"]["sha"]
        commit_url = f"{api_base}/repos/{repository}/git/commits/{base_commit}"
        base_tree = request_fn(token, "GET", commit_url, None)["tree"]["sha"]
        tree_url = f"{api_base}/repos/{repository}/git/trees/{base_tree}?recursive=1"
        remote_tree = request_fn(token, "GET", tree_url, None).get("tree", [])
        remote_shas = {entry["path"]: entry["sha"] for entry in remote_tree}
        if all(remote_shas.get(path) == git_blob_sha(content) for path, content in files.items()):
            return PublicationResult(status="unchanged", files=len(files))

        entries = []
        for path, content in files.items():
            blob = request_fn(
                token,
                "POST",
                f"{api_base}/repos/{repository}/git/blobs",
                {"content": base64.b64encode(content).decode(), "encoding": "base64"},
            )
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = request_fn(
            token,
            "POST",
            f"{api_base}/repos/{repository}/git/trees",
            {"base_tree": base_tree, "tree": entries},
        )
        commit = request_fn(
            token,
            "POST",
            f"{api_base}/repos/{repository}/git/commits",
            {
                "message": "chore(snapshot): publish settled weekday refresh",
                "tree": tree["sha"],
                "parents": [base_commit],
            },
        )
        try:
            request_fn(
                token,
                "PATCH",
                ref_url,
                {"sha": commit["sha"], "force": False},
            )
            return PublicationResult(status="published", commit_sha=commit["sha"], files=len(files))
        except HTTPError as error:
            if error.code not in (409, 422) or attempt == 1:
                raise
    raise RuntimeError("unreachable")
