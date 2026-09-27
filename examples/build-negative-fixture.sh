#!/bin/bash
# Build the jev-review v0.2 NEGATIVE test fixture: base->HEAD touches only
# benign changes (rename a local, reorder imports, whitespace, one comment,
# one docstring) plus a README.md change that deterministic triage MUST skip
# (asserted by tests/test_negative.py from the built diff — never judged).
# Deterministic: fixed dates/identities; tree hash independent of path.
set -euo pipefail
ROOT="${JEV_FIXTURE_ROOT:-/tmp/jev-review-neg}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHAS_FILE="$SCRIPT_DIR/fixture-shas.txt"

rm -rf "$ROOT"
mkdir -p "$ROOT/src"
cd "$ROOT"
git init -q -b main
git config user.email fixture@example.invalid
git config user.name jev-fixture
export GIT_AUTHOR_DATE="2026-09-27T12:00:00+0000"
export GIT_COMMITTER_DATE="2026-09-27T12:00:00+0000"

cat > src/app.py <<'EOF'
import json
import os

def render(items):
    out = ""
    for i in items:
        out += str(i) + ","
    return out

def load_config(path):
    with open(path) as f:
        return json.load(f)

def divide(a, b):
    if b == 0:
        raise ValueError("denominator must be non-zero")
    return a / b
EOF
cat > README.md <<'EOF'
# demo app

Renders items and loads config.
EOF
git add .
git commit -qm base

cat > src/app.py <<'EOF'
import os
import json

def render(entries):
    """Render entries as a comma-separated string."""
    out = ""
    for e in entries:
        out += str(e) + ","
    return out

def load_config(path):
    with open(path) as f:
        return json.load(f)

def divide(a, b):
    if b == 0:
        raise ValueError("denominator must be non-zero")
    return a / b
EOF
cat > README.md <<'EOF'
# demo app

Renders items and loads config.

## Usage

    python src/app.py
EOF
git add .
git commit -qm "benign cleanup: rename, reorder imports, docs"

HEAD_SHA="$(git rev-parse HEAD)"
EXPECT="$(grep -E '^negative=' "$SHAS_FILE" | cut -d= -f2)"
if [ -n "$EXPECT" ] && [ "$HEAD_SHA" != "$EXPECT" ]; then
    echo "SHA GATE FAIL: built $HEAD_SHA, expected $EXPECT" >&2
    exit 1
fi

# golden verification: README.md changed but src/app.py diff is all-benign
GOLDEN="$SCRIPT_DIR/negative-golden.tsv"
while IFS=$'\t' read -r fname line substr; do
    case "$fname" in \#*) continue;; esac
    git show "HEAD:$fname" | grep -qF -- "$substr" \
        || { echo "golden verify FAIL: $fname missing '$substr'" >&2; exit 1; }
done < "$GOLDEN"
echo "negative fixture ready: $ROOT head=$HEAD_SHA"
