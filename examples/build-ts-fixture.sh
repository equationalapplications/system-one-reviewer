#!/bin/bash
# Build the system-one-reviewer v0.9 TS POSITIVE fixture (spec m4): a repo
# whose HEAD commit introduces exactly THREE real issues, each planted
# directly on an E2 decision-site kind so the TS leg of V1 exercises the
# SAME cutting path E2 ships (not just the AST-units top-level cutter):
#   1. a non-literal object-property assignment (call-argument order swap
#      inside a config object literal) — MAJOR
#   2. a call-argument swap on a slice() call — MAJOR
#   3. a ternary/conditional polarity flip (branches swapped) — BLOCKER
# Deterministic: fixed dates/author => identical commit SHA on every
# machine. ROOT comes from JEV_FIXTURE_ROOT (default /tmp/jev-review-ts-pos).
# Ends by verifying every golden TSV line against actual HEAD content,
# asserting the head SHA against examples/fixture-shas.txt (positive_ts=),
# and printing the head SHA.
set -euo pipefail
ROOT=${JEV_FIXTURE_ROOT:-/tmp/jev-review-ts-pos}
SHAS_FILE="$(cd "$(dirname "$0")" && pwd)/fixture-shas.txt"
GOLDEN_FILE="$(cd "$(dirname "$0")" && pwd)/ts-fixture-golden.tsv"
rm -rf "$ROOT"
mkdir -p "$ROOT/src"
cd "$ROOT"
export GIT_AUTHOR_DATE="2026-10-19T12:00:00 +0000"
export GIT_COMMITTER_DATE="2026-10-19T12:00:00 +0000"
git init -q -b main
git config commit.gpgsign false
git config core.autocrlf false
git config user.email fixture@example.invalid
git config user.name jev-fixture

# ---------- base commit: clean, idiomatic TS ----------
cat > src/app.ts <<'EOF'
function computeTimeout(base: number, jitter: number): number {
  return base + jitter;
}

function buildConfig(base: number, jitter: number) {
  const config = {
    timeout: computeTimeout(base, jitter),
    retries: 3,
  };
  return config;
}

function lastN(items: string[], n: number): string[] {
  return items.slice(items.length - n, items.length);
}

function describe(isAdmin: boolean, restricted: string, full: string): string {
  const scope = isAdmin ? full : restricted;
  return scope;
}
EOF
git add src/app.ts
git commit -qm "base"

# ---------- HEAD commit: the same file with 3 planted issues ----------
# 1. buildConfig's timeout property swaps computeTimeout's arguments
#    (jitter, base) instead of (base, jitter) — MAJOR, a call-argument
#    defect nested inside a non-literal object-property assignment.
# 2. lastN's slice() call swaps its two arguments — MAJOR, a plain
#    call-argument defect.
# 3. describe's ternary swaps its two branches (full/restricted reversed)
#    — BLOCKER, a conditional/ternary polarity defect (an admin now gets
#    the RESTRICTED scope and a non-admin gets FULL).
cat > src/app.ts <<'EOF'
function computeTimeout(base: number, jitter: number): number {
  return base + jitter;
}

function buildConfig(base: number, jitter: number) {
  const config = {
    timeout: computeTimeout(jitter, base),
    retries: 3,
  };
  return config;
}

function lastN(items: string[], n: number): string[] {
  return items.slice(items.length, items.length - n);
}

function describe(isAdmin: boolean, restricted: string, full: string): string {
  const scope = isAdmin ? restricted : full;
  return scope;
}
EOF
git add src/app.ts
git commit -qm "add features with issues"

HEAD_SHA=$(git rev-parse HEAD)

# ---------- verify every golden line against actual HEAD content ----------
i=0
while IFS=$'\t' read -r gfile gline gdesc gverify gsev || [ -n "$gfile" ]; do
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
expected=$(grep -E '^positive_ts=' "$SHAS_FILE" | head -1 | cut -d= -f2)
if [ -n "$expected" ] && [ "$HEAD_SHA" != "$expected" ]; then
  echo "FATAL: head SHA $HEAD_SHA != expected $expected" >&2
  exit 1
fi
echo "fixture ready: $ROOT"
echo "head=$HEAD_SHA"
