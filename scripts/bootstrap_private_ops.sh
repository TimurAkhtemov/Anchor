#!/bin/zsh
set -euo pipefail

repo_root=${0:A:h:h}
python_bin=${ANCHOR_BOOTSTRAP_PYTHON:-/opt/homebrew/bin/python3.12}

if [[ ! -x "$python_bin" ]]; then
  print -u2 "Python 3.12 not found at $python_bin"
  exit 1
fi

"$python_bin" -m venv "$repo_root/venv"
"$repo_root/venv/bin/python" -m pip install --upgrade pip
"$repo_root/venv/bin/python" -m pip install \
  -r "$repo_root/ingestion/requirements.txt" \
  -r "$repo_root/app/requirements.txt"

print "Private operations runtime ready: $repo_root/venv"
