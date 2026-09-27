#!/bin/bash
# Build the jev-review v0.2 POSITIVE test fixture: repo whose HEAD commit
# introduces exactly five real issues (3 real: BLOCKER + 2 MAJOR; 2 nits:
# 2 MINOR). Deterministic: fixed dates/author => identical commit SHA on
# every machine. ROOT comes from JEV_FIXTURE_ROOT (default /tmp/jev-review-pos).
# Ends by verifying every golden TSV line (file, line, desc, verify-substring,
# severity-class) against actual HEAD content, asserting the head SHA against
# examples/fixture-shas.txt, and printing the full head SHA.
set -euo pipefail
ROOT=${JEV_FIXTURE_ROOT:-/tmp/jev-review-pos}
SHAS_FILE="$(cd "$(dirname "$0")" && pwd)/fixture-shas.txt"
GOLDEN_FILE="$(cd "$(dirname "$0")" && pwd)/fixture-golden.tsv"
rm -rf "$ROOT"
mkdir -p "$ROOT/src"
cd "$ROOT"
export GIT_AUTHOR_DATE="2026-09-27T12:00:00 +0000"
export GIT_COMMITTER_DATE="2026-09-27T12:00:00 +0000"
git init -q -b main
git config user.email fixture@example.invalid
git config user.name jev-fixture

# ---------- base commit: clean, idiomatic code ----------
cat > src/app.py <<'EOF'
import json

def load_config(path):
    with open(path) as f:
        return json.load(f)

def find_user(users, uid, missing=None):
    for u in users:
        if u.id == uid:
            return u
    return missing

def divide(a, b):
    if b == 0:
        return None
    return a / b

def render(items):
    return ",".join(str(i) for i in items)
EOF
git add src/app.py
git commit -qm "base"

# ---------- HEAD commit: the same file with 5 planted issues ----------
# 1. load_config opens with "w" (BLOCKER: truncates the file it reads)
# 2. find_user drops the missing sentinel, returns None (MAJOR)
# 3. divide loses the zero guard (MAJOR: ZeroDivisionError)
# 4. duplicate `import json` appended at the bottom (MINOR, style)
# 5. render becomes an O(n^2) += loop (MINOR, performance)
cat > src/app.py <<'EOF'
import json

def load_config(path):
    with open(path, "w") as f:
        return json.load(f)

def find_user(users, uid, missing=None):
    for u in users:
        if u.id == uid:
            return u
    return None

def divide(a, b):
    return a / b

def render(items):
    out = ""
    for i in range(len(items)):
        out += str(i) + ","
    return out

import json
EOF
git add src/app.py
git commit -qm "add features with issues"

HEAD_SHA=$(git rev-parse HEAD)

# ---------- verify every golden line against actual HEAD content ----------
i=0
while IFS=$'\t' read -r gfile gline gdesc gverify gsev; do
  case "$gfile" in \#*) continue ;; esac
  i=$((i+1))
  actual=$(sed -n "${gline}p" "$gfile")
  case "$actual" in
    *"$gverify"*) : ;;
    *) echo "FATAL: golden line $i ($gfile:$gline) verify substring" \
          "[$gverify] not found in actual content: [$actual]" >&2; exit 1 ;;
  esac
done < "$GOLDEN_FILE"
echo "golden verified: $i planted issues match HEAD content"

# ---------- assert head SHA against the committed constant ----------
expected=$(grep -E '^positive=' "$SHAS_FILE" | head -1 | cut -d= -f2)
if [ -n "$expected" ] && [ "$HEAD_SHA" != "$expected" ]; then
  echo "FATAL: head SHA $HEAD_SHA != expected $expected" >&2
  exit 1
fi
echo "fixture ready: $ROOT"
echo "head=$HEAD_SHA"
