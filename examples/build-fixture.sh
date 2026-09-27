#!/bin/bash
# Build the jev-review test fixture: repo with 5 planted issues.
set -e
ROOT=/tmp/jev-review-test
rm -rf "$ROOT"
mkdir -p "$ROOT/src"
cd "$ROOT"
git init -q -b main
git config user.email t@example.com
git config user.name tester

cat > src/app.py <<'EOF'
def compute_total(items):
    total = 0
    for item in items:
        total += item.price * item.qty
    return total

def find_user(users, uid):
    for u in users:
        if u.id == uid:
            return u
    return None

def divide(a, b):
    return a / b

import json
import json

def load_config(path):
    with open(path) as f:
        return json.load(f)

def render(items):
    out = ""
    for i in range(len(items)):
        out += str(items[i]) + ","
    return out
EOF
git add .
git commit -qm base

cat > src/app.py <<'EOF'
def compute_total(items):
    total = 0
    for item in items:
        total += item.price * item.qty
    return total

def find_user(users, uid):
    for u in users:
        if u.id == uid:
            return u
    return None  # PLANT 1: silent failure — callers can't distinguish missing user

def divide(a, b):
    return a / b  # PLANT 2: zero-division risk, no guard on b

import json
import json  # PLANT 3: duplicate import

def load_config(path):
    with open(path, "r") as f:  # PLANT 4 (minor): redundant mode arg
        return json.load(f)

def render(items):
    out = ""
    for i in range(len(items)):
        out += str(items[i]) + ","  # PLANT 5 (minor): O(n^2) string concat
    return out
EOF
git add .
git commit -qm "add features with issues"
echo "fixture ready: $ROOT"
