"""Unit checks for the local leak scanners (no BigQuery; the matching logic only)."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scan = _load("scan_for_private_tickers")
audit = _load("audit_public_tables")


def test_pattern_matches_whole_upper_case_words_only():
    pat = scan.compile_pattern({"ZZQ", "ABCD"})
    assert pat.findall("bought ZZQ and ABCD today") == ["ZZQ", "ABCD"]
    assert pat.findall("ZZQX, XZZQ, zzq, ABCDE, ab ABCD_1") == []
    assert pat.findall('"ZZQ"') == ["ZZQ"]  # punctuation is a boundary


def test_pattern_is_none_for_empty_set():
    assert scan.compile_pattern(set()) is None


def test_scanner_reports_counts_and_kinds_without_symbols(capsys):
    s = scan.Scanner({"ZZQ", "CAT"}, wordlike={"CAT"}, show=False)
    s.scan("a.md", "CAT sat.\nZZQ ZZQ\n")
    total = s.report()
    out = capsys.readouterr().out
    assert total == 3
    assert "a.md" in out and "word-like" in out and "symbol" in out
    assert "ZZQ" not in out and "CAT" not in out


def test_audit_scope_excludes_private_datasets():
    assert all(not d.endswith("_private") for d in audit.PUBLIC_DATASETS)
    assert "raw_holdings" not in audit.PUBLIC_DATASETS
    assert audit.PUBLIC_TABLES == (("raw_holdings", "holdings_demo"),)
