#!/bin/bash
# Build the system-one-reviewer v0.2 NEGATIVE test fixture: base->HEAD is
# behavior-preserving per spec E1 — a whitespace-only reformat, a
# behavior-preserving import reorder, one
# innocuous comment, and a README.md change that deterministic triage MUST
# skip (asserted by tests/test_negative.py from the built diff — never
# judged). NO renames, NO signature changes, NO docstring rewrites: every
# source change is whitespace, a comment, or an equivalent-code reorder.
# Deterministic: fixed dates/identities; tree hash independent of path.
set -euo pipefail
ROOT="${JEV_FIXTURE_ROOT:-/tmp/jev-review-neg}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHAS_FILE="$SCRIPT_DIR/fixture-shas.txt"

rm -rf "$ROOT"
mkdir -p "$ROOT/src"
cd "$ROOT"
git init -q -b main
# m5 (r6): pin the config that would change commit/tree SHAs
git config commit.gpgsign false
git config core.autocrlf false
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

# HEAD: same code, whitespace-only reformat + one innocuous comment.
# The items parameter keeps its name (renaming it would break keyword
# callers and is NOT behavior-preserving — spec E1 forbids that).
cat > src/app.py <<'EOF'
import os
import json

# Render the items as a comma-separated string (innocuous comment).
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

## Usage

    python src/app.py
EOF
git add .
git commit -qm "benign cleanup: whitespace, comment, docs"

HEAD_SHA="$(git rev-parse HEAD)"
EXPECT="$(grep -E '^negative=' "$SHAS_FILE" | cut -d= -f2)"
if [ -n "$EXPECT" ] && [ "$HEAD_SHA" != "$EXPECT" ]; then
    echo "SHA GATE FAIL: built $HEAD_SHA, expected $EXPECT" >&2
    exit 1
fi

# golden verification: README.md changed but src/app.py diff is all-benign
GOLDEN="$SCRIPT_DIR/negative-golden.tsv"
while IFS=$'\t' read -r fname substr || [ -n "$fname" ]; do
    case "$fname" in \#*) continue;; esac
    # M1 (r2): the TSV is 2 columns (file, substring). An empty $substr
    # would make `grep -qF -- ""` match ANY file — a check that can't
    # fail is not a check — so refuse to run with one.
    if [ -z "$substr" ]; then
        echo "golden verify FAIL: $fname has an empty verify-substring" >&2
        exit 1
    fi
    git show "HEAD:$fname" | grep -qF -- "$substr" \
        || { echo "golden verify FAIL: $fname missing '$substr'" >&2; exit 1; }
done < "$GOLDEN"
echo "negative fixture ready: $ROOT head=$HEAD_SHA"
