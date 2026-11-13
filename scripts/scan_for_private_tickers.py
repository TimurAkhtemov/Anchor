"""Local-only scan: do any real-portfolio tickers appear in files or git history?

    python scripts/scan_for_private_tickers.py PATH [PATH ...]
    python scripts/scan_for_private_tickers.py --git-history            # every commit's diff
    python scripts/scan_for_private_tickers.py --tracked                # files git tracks today

Reads the real tickers from `raw_holdings.holdings_real` (BigQuery, needs the
private credential), removes everything in the public demo universe
(`allowed_tickers()`), and searches for whole-word, case-sensitive matches.
It reports COUNTS and LOCATIONS only, never the tickers themselves, so the
output is safe to paste anywhere. Run it only on this machine.

Common-word tickers: a symbol that is also an English word (checked against
the system dictionary) can match ordinary upper-case prose such as headings or
SQL keywords. Each hit is reported as "word-like" or "symbol" so the operator
knows which ones need a local look; --show prints the matching lines (and so
the symbols) and must stay on this machine.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.bundle_validation import allowed_tickers  # noqa: E402

PROJECT = os.environ.get("ANCHOR_BQ_PROJECT", "anchor-495115")
DICTIONARY = Path("/usr/share/dict/words")
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "var", "__pycache__", ".next", "out", "data"}
TEXT_SUFFIXES = {
    ".py", ".sql", ".yml", ".yaml", ".md", ".txt", ".json", ".csv", ".toml", ".cfg",
    ".ini", ".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".sh", ".log", ".plist", "",
}


def real_tickers(client) -> set[str]:
    rows = client.query(
        f"select distinct upper(ticker) as ticker from `{PROJECT}.raw_holdings.holdings_real`"
    ).result()
    return {r.ticker for r in rows if r.ticker}


def private_only_tickers(client) -> set[str]:
    return real_tickers(client) - allowed_tickers()


def dictionary_words() -> set[str]:
    try:
        return {w.strip().lower() for w in DICTIONARY.read_text(errors="ignore").splitlines()}
    except OSError:
        return set()


def compile_pattern(tickers: set[str]) -> re.Pattern[str] | None:
    if not tickers:
        return None
    alts = "|".join(re.escape(t) for t in sorted(tickers, key=len, reverse=True))
    # Whole word, case-sensitive: tickers are upper case; prose rarely is.
    return re.compile(rf"(?<![A-Za-z0-9_])(?:{alts})(?![A-Za-z0-9_])")


def iter_files(paths: list[Path]):
    for root in paths:
        if root.is_file():
            yield root
            continue
        for p in root.rglob("*"):
            if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
                continue
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
                yield p


class Scanner:
    def __init__(self, secret: set[str], wordlike: set[str], show: bool):
        self.pattern = compile_pattern(secret)
        self.wordlike = wordlike
        self.show = show
        self.hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def scan(self, label: str, text: str) -> None:
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in self.pattern.finditer(line):
                kind = "word-like" if m.group(0) in self.wordlike else "symbol"
                self.hits[label][f"{kind} (len {len(m.group(0))})"] += 1
                if self.show:
                    print(f"    {label}:{lineno}: {line.strip()[:160]}")

    def report(self) -> int:
        total = sum(sum(v.values()) for v in self.hits.values())
        print(f"matches: {total} across {len(self.hits)} location(s)")
        for label, kinds in sorted(self.hits.items()):
            print(f"  {label}: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))
        return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--git-history", action="store_true", help="scan `git log -p --all`")
    ap.add_argument("--tracked", action="store_true", help="scan files git tracks today")
    ap.add_argument("--show", action="store_true", help="print matching lines (LOCAL ONLY — reveals symbols)")
    args = ap.parse_args()
    if not (args.paths or args.git_history or args.tracked):
        ap.error("give paths, --git-history, or --tracked")

    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT)
    secret = private_only_tickers(client)
    wordlike = {t for t in secret if t.lower() in dictionary_words()}
    by_len = defaultdict(int)
    for t in secret:
        by_len[len(t)] += 1
    print(
        f"private-only tickers: {len(secret)} (by length: {dict(sorted(by_len.items()))}; "
        f"{len(wordlike)} are also English words and may match prose)"
    )
    if not secret:
        print("nothing to scan for")
        return 0
    scanner = Scanner(secret, wordlike, args.show)

    for p in iter_files(args.paths):
        try:
            scanner.scan(str(p), p.read_text(errors="ignore"))
        except OSError:
            continue

    if args.tracked:
        files = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
        ).stdout.decode().split("\0")
        for rel in filter(None, files):
            p = REPO_ROOT / rel
            if p.suffix.lower() in TEXT_SUFFIXES and p.is_file():
                scanner.scan(rel, p.read_text(errors="ignore"))

    if args.git_history:
        log = subprocess.run(
            ["git", "log", "-p", "--all", "--no-color", "--format=commit %H"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout.decode(errors="ignore")
        commit, buf = "?", []
        for line in log.splitlines():
            if line.startswith("commit "):
                if buf:
                    scanner.scan(f"git:{commit}", "\n".join(buf))
                commit, buf = line.split()[1][:12], []
            else:
                buf.append(line)
        if buf:
            scanner.scan(f"git:{commit}", "\n".join(buf))

    return 1 if scanner.report() else 0


if __name__ == "__main__":
    sys.exit(main())
