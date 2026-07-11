import json
from urllib.error import HTTPError

import pytest

from app.snapshot_publication import git_blob_sha, publish_snapshot


def _snapshot(tmp_path):
    (tmp_path / "one.parquet").write_bytes(b"parquet")
    (tmp_path / "publication.json").write_text(json.dumps({"as_of_date": "2026-07-09"}))
    return tmp_path


def test_publication_is_noop_when_remote_tree_matches(tmp_path):
    snapshot = _snapshot(tmp_path)
    expected = {
        "app/snapshot/one.parquet": git_blob_sha(b"parquet"),
        "app/snapshot/publication.json": git_blob_sha(
            (snapshot / "publication.json").read_bytes()
        ),
    }

    def request(_token, method, url, _payload):
        if "/ref/" in url:
            return {"object": {"sha": "base"}}
        if "/commits/base" in url:
            return {"tree": {"sha": "tree"}}
        if "recursive=1" in url:
            return {"tree": [{"path": path, "sha": sha} for path, sha in expected.items()]}
        raise AssertionError((method, url))

    result = publish_snapshot(snapshot, "token", request_fn=request)
    assert result.status == "unchanged"
    assert result.files == 2


def test_publication_creates_one_atomic_commit(tmp_path):
    snapshot = _snapshot(tmp_path)
    calls = []

    def request(_token, method, url, payload):
        calls.append((method, url, payload))
        if "/ref/" in url and method == "GET":
            return {"object": {"sha": "base"}}
        if "/commits/base" in url:
            return {"tree": {"sha": "base-tree"}}
        if "recursive=1" in url:
            return {"tree": []}
        if url.endswith("/git/blobs"):
            return {"sha": f"blob-{len(calls)}"}
        if url.endswith("/git/trees"):
            return {"sha": "new-tree"}
        if url.endswith("/git/commits"):
            assert payload["parents"] == ["base"]
            return {"sha": "new-commit"}
        if "/ref/" in url and method == "PATCH":
            assert payload == {"sha": "new-commit", "force": False}
            return {}
        raise AssertionError((method, url))

    result = publish_snapshot(snapshot, "token", request_fn=request)
    assert result.status == "published"
    assert result.commit_sha == "new-commit"
    assert len([call for call in calls if call[1].endswith("/git/commits")]) == 1


def test_publication_does_not_force_after_two_head_conflicts(tmp_path):
    snapshot = _snapshot(tmp_path)
    ref_reads = 0

    def request(_token, method, url, payload):
        nonlocal ref_reads
        if "/ref/" in url and method == "GET":
            ref_reads += 1
            return {"object": {"sha": f"base-{ref_reads}"}}
        if "/commits/base-" in url:
            return {"tree": {"sha": f"tree-{ref_reads}"}}
        if "recursive=1" in url:
            return {"tree": []}
        if url.endswith("/git/blobs"):
            return {"sha": "blob"}
        if url.endswith("/git/trees"):
            return {"sha": "tree"}
        if url.endswith("/git/commits"):
            return {"sha": "commit"}
        if "/ref/" in url and method == "PATCH":
            raise HTTPError(url, 422, "head moved", {}, None)
        raise AssertionError((method, url, payload))

    with pytest.raises(HTTPError):
        publish_snapshot(snapshot, "token", request_fn=request)
    assert ref_reads == 2
