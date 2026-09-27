#!/usr/bin/env python3
"""system-one-reviewer — local PR review powered by deterministic code + a system one model (hosted Jev or local Laya).

Experimental (D1, Kurt 2026-09-27): an ADDITIONAL lightweight reviewer for
Tessera on the ThinkPad. Runs in seconds, costs fractions of a cent, use
freely and often. Posts nothing anywhere; prints a report, optionally JSON.

Design (v0.2, evaluation-hardened):
  1. gather   — git plumbing pre-computes merge-base/diff/head (no re-derivation)
  2. triage   — deterministic skip: lockfiles, generated, docs-only
  3. package  — diff split into change clusters with file:line anchors,
                hunk-boundary clamping (windows never cross an @@ header)
  4. judge    — Jev ONLY (noul/choice/score), one call per cluster, keep-alive
  5. compose  — thresholds in code; plateau rule; jitter flags; fixed verdict
  6. measure  — every run appends raw scores to metrics jsonl; --golden gives
                precision/recall/F1 so the pattern can be refined as we go

Jev owns go/no-go judgments; deterministic code owns everything else.
Fail-open: repeated provider failures -> report ships with an
"Unavailable" banner, never dies.

Usage:
  system-one-reviewer --repo <path> (--range A..B | --pr N | --staged | --uncommitted)
             [--out f.json] [--max-hunks N] [--golden f] [--label s] [--json]
             [--negative-golden f] [--fixture NAME]
"""

import argparse
import json
import math
import os
import re
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.client import HTTPSConnection
from urllib.parse import urlparse

API_URL = "https://api.typesafe.ai/v1/systemone"
METRICS_PATH = os.environ.get(
    "JEV_REVIEW_METRICS",
    os.path.join(os.environ.get("XDG_STATE_HOME",
                                os.path.expanduser("~/.local/state")),
                 "jev-review", "metrics.jsonl"))

MAX_HUNK_LINES = 120          # hunks larger than this are noted, not judged
CALL_FAIL_LIMIT = 2           # consecutive Jev failures -> fail-open
REAL_THRESHOLD = 0.50         # is_real_issue noul gate (plateau-safe)
KNOWN_FIXTURES = {"positive", "negative"}
PACKAGING_VERSION = "v02"
def sev_level(v):
    """Nearest integer level, halves round up (2.5 is a BLOCKER)."""
    if v is None:
        return 0
    return max(0, min(3, math.floor(v + 0.5)))

SEV_NAME = {0: "none", 1: "MINOR", 2: "MAJOR", 3: "BLOCKER"}
CATEGORIES = ["bug-risk", "security", "style", "performance", "test-gap", "other"]
SKIP_PATTERNS = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|Cargo\.lock|poetry\.lock|"
    r"pnpm-lock\.yaml|uv\.lock|LICENSE|COPYING|\.gitignore|\.editorconfig)$"
    r"|(^|/)(dist|build|target|node_modules|\.min\.(js|css))(/|$)"
    r"|^(CHANGELOG|AUTHORS|CONTRIBUTORS)"
)
DOC_EXT = re.compile(r"\.(md|mdx|txt|rst|adoc)$", re.I)

# ---------- Jev client (same keep-alive contract as the voice gate) ----------

_ssl_ctx = ssl.create_default_context()
_conn = None
_url = urlparse(API_URL)


def load_api_key() -> str:
    """Env var first; fall back to .env-style files (generic, no agent paths)."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key
    candidates = [
        os.path.expanduser(p) for p in (
            "~/.config/jev-review/.env",   # dedicated config
            "~/.env",                       # home dotfile
        )]
    for path in candidates:
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("TYPESAFE_API_KEY="):
                        return line.strip().split("=", 1)[1]
        except OSError:
            continue
    sys.exit("system-one-reviewer: set TYPESAFE_API_KEY (env) or put TYPESAFE_API_KEY=... "
             "in ~/.config/jev-review/.env")


def _get_conn():
    global _conn
    if _conn is None:
        _conn = HTTPSConnection(_url.hostname, _url.port or 443,
                                context=_ssl_ctx, timeout=15)
    return _conn


def _drop_conn():
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:
        pass
    _conn = None


class _NoRetry(Exception):
    """m5 (r10)/M1 (r11): HTTP 4xx must not be retried.

    jev_ask's retry loop catches Exception to retry transport hiccups;
    this dedicated type is re-raised untouched by the handler so a 401/
    403/429 costs exactly one request.
    """


def jev_ask(state, questions, api_key):
    """One batched Jev round-trip. Returns (payload, latency_ms)."""
    body = json.dumps({"state": state, "model": "jev-latest",
                       "questions": questions})
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    t0 = time.perf_counter()
    for attempt in (1, 2):
        try:
            conn = _get_conn()
            conn.request("POST", _url.path, body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            # M1 (r7): an HTTP error (401/403/429/5xx) often carries a JSON
            # body that parses fine — treat any >= 400 as a call failure so
            # the fail-open counter sees it, never a silent "Approved".
            if resp.status >= 400:
                # m5 (r10): 4xx is not worth a retry — raise _NoRetry, which
                # the handler below re-raises untouched. (r11 M1: a bare
                # RuntimeError was swallowed by the handler and retried —
                # the r10 fix never took effect.) 5xx retries once
                # (transient server errors), then re-raises on attempt 2.
                # Cost of a retry is one wasted request + latency, nothing
                # more: jev_ask raises once per call either way.
                if resp.status < 500:
                    raise _NoRetry(f"HTTP {resp.status}: {raw[:200]!r}")
                raise RuntimeError(f"HTTP {resp.status}: {raw[:200]!r}")
            payload = json.loads(raw)
            break
        except _NoRetry:
            _drop_conn()
            raise
        except Exception:
            _drop_conn()
            if attempt == 2:
                raise
    return payload, (time.perf_counter() - t0) * 1000.0


# ---------- provider facade (E8) ----------

# ask(state, questions) -> (payload, latency_ms) with payload["answers"][name]
# carrying score/noul/choice. judge/judge_pr_level only ever see this
# contract; the wired provider is injected transport-style so tests can
# substitute fakes without network or packages.
_TRANSPORT = None        # set by set_transport / make_provider
_PROVIDER_NAME = "jev"   # set by set_provider_name (r9 m1)
_LAYA_ROUTER = None      # one router per process (one model load per run)
_LAYA_SHAPE_VALIDATED = False  # m4 (r7): answers contract checked once
LAYA_DEFAULT_MODEL = "convaiinnovations/rl-agent"
PROVIDERS = ("jev", "laya")


def set_transport(transport):
    """Inject the ask transport (the jev client wrapper in production)."""
    global _TRANSPORT
    _TRANSPORT = transport


def set_provider_name(name):
    """Record the wired provider for user-facing messages (r9 m1)."""
    global _PROVIDER_NAME
    _PROVIDER_NAME = name


def ask(state, questions):
    """Module-level E8 entry point: dispatch through the wired transport."""
    if _TRANSPORT is None:
        sys.exit("system-one-reviewer: no provider wired — this is a bug")
    return _TRANSPORT(state, questions)


def provider_from(provider_arg, model_arg):
    """Resolve (--provider, --model); SOR_PROVIDER env is the default.

    r4 m2: `--model` is a laya-only knob — for jev it is dropped (not
    logged) so a stray --model cannot split identical jev runs into
    different (provider, model) sweep groups.
    """
    provider = provider_arg or os.environ.get("SOR_PROVIDER") or "jev"
    if provider not in PROVIDERS:
        sys.exit(f"system-one-reviewer: unknown provider {provider!r} "
                 f"(choose from {', '.join(PROVIDERS)})")
    if provider == "jev":
        return provider, None
    model = model_arg or LAYA_DEFAULT_MODEL
    return provider, model


def make_provider(provider, model, api_key=None):
    """Return the wired ask() for the chosen provider (E8 contract).

    The returned closure is also registered as the module-level `ask`
    dispatch target (set_transport).
    """
    if provider == "jev":
        key = api_key if api_key is not None else load_api_key()

        def provider_ask(state, questions):
            return jev_ask(state, questions, key)

        set_transport(provider_ask)
        set_provider_name("jev")
        return provider_ask
    # laya: local inference; the router loads lazily on first call and is
    # kept for the process lifetime.
    def provider_ask(state, questions):
        router = get_laya_router(model=model)
        return laya_ask(router, state, questions)

    set_transport(provider_ask)
    set_provider_name(f"laya/{model}" if model else "laya")
    return provider_ask


def get_laya_router(model=None, loader=None):
    """Import laya lazily; build the router once per process.

    `loader` is the import function (injectable for tests). Missing
    package or weights -> clean one-line error with the pip line.
    """
    global _LAYA_ROUTER
    if _LAYA_ROUTER is not None:
        return _LAYA_ROUTER
    try:
        laya = (loader or __import__)("laya")
    except ImportError as exc:
        sys.exit(f"system-one-reviewer: the laya provider needs the laya package: "
                 f"{exc}; fix with: pip install laya")
    try:
        # m4 (r10): provider_from always resolves a model (LAYA_DEFAULT_MODEL),
        # so the no-model branch is only reachable when get_laya_router is
        # called directly with model=None (tests, library use).
        _LAYA_ROUTER = laya.load(model=model) if model else laya.Router()
    except Exception as exc:
        sys.exit(f"system-one-reviewer: could not load the laya model "
                 f"{model or '(default)'}: {exc}. The laya package is "
                 f"imported, so this is most likely a missing/invalid "
                 f"model checkpoint — install the weights for "
                 f"{model or LAYA_DEFAULT_MODEL} or pass a valid --model. "
                 f"(If the laya package itself is missing: pip install laya)")
    return _LAYA_ROUTER


def laya_ask(router, state, questions):
    """One batched laya round-trip over the same answers shape.

    m4 (r7): the response shape is validated once on the first call —
    a shape mismatch raises so the fail-open path reports it instead of
    quietly turning every cluster into a parse_error "Approved"."""
    global _LAYA_SHAPE_VALIDATED
    t0 = time.perf_counter()
    payload = router.predict(state, questions)
    # m4 (r7): validate the answers contract on the first response. The
    # judge's parse_error path would otherwise mask a shape mismatch as
    # "Approved / no findings".
    if not _LAYA_SHAPE_VALIDATED:
        answers = (payload or {}).get("answers")
        if not isinstance(answers, dict) or not answers:
            raise RuntimeError(
                "laya response shape mismatch: expected "
                '{"answers": {name: {score|noul|choice}}}, got '
                f"{type(payload).__name__}: {str(payload)[:200]!r}")
        _LAYA_SHAPE_VALIDATED = True
    return payload, (time.perf_counter() - t0) * 1000.0


def laya_ask_or_die(model=None, loader=None):
    """Eager laya check used by main() so a missing local stack fails
    before any review work happens. (r7 nit: the never-used router
    parameter is gone.)"""
    return get_laya_router(model=model, loader=loader)


# ---------- deterministic stages ----------

def run_git(repo, *args):
    if args and args[0] == "diff":
        # m1 (r6): pin the output format — user config (mnemonicPrefix,
        # color.ui, diff.external, quotePath) would break parsing.
        # B1 (r7): the flags belong AFTER the `diff` subcommand; git
        # rejects top-level unknown options with exit 129.
        args = ("diff", "--no-color", "--no-ext-diff", "--src-prefix=a/",
                "--dst-prefix=b/") + tuple(args[1:])
        r = subprocess.run(["git", "-C", repo, "-c", "core.quotePath=false",
                            *args], capture_output=True, text=True)
    else:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"system-one-reviewer: git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout


def resolve_diff(repo, args):
    """Return (diff_text, head_sha, mode).

    fixture_head semantics (m2 disposition): the logged `fixture_head` is
    the checkout HEAD (git rev-parse HEAD), not the tip of --range and not
    the reviewed commit itself. For a committed fixture this is exactly the
    SHA the sweep gates on (--staged/--uncommitted review HEAD's tree, so
    the same value is correct there); only a range that does not END at
    HEAD would diverge, which the committed fixtures never do.
    """
    if args.range:
        diff = run_git(repo, "diff", args.range)
        head = run_git(repo, "rev-parse", "HEAD").strip()
        return diff, head, f"range:{args.range}"
    if args.staged:
        return (run_git(repo, "diff", "--cached"),
                run_git(repo, "rev-parse", "HEAD").strip(), "staged")
    if args.uncommitted:
        return (run_git(repo, "diff"),
                run_git(repo, "rev-parse", "HEAD").strip(), "uncommitted")
    if args.pr:
        diff = run_git(repo, "diff", f"origin/main...pr/{args.pr}")
        head = run_git(repo, "rev-parse", f"pr/{args.pr}").strip()
        return diff, head, f"pr:{args.pr}"
    sys.exit("system-one-reviewer: pick one of --range/--pr/--staged/--uncommitted")


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def package_hunks(diff):
    """Cluster-level packaging: contiguous changed lines form a cluster, each
    with +/-4 context lines. Windows are clamped at @@ hunk boundaries (a
    cluster never crosses an @@ header) and trimmed at the neighbouring
    clusters' changed entries, so one change never dilutes another.
    Anchors: first '+' in the cluster's own run -> else the deletion site
    (first '-' in the run, at the position in HEAD where the line was
    removed) -> else the first context entry with a lineno at/after the run
    -> else the run's hunk_start (a deletion-only cluster never collapses to
    line 1). Deletion-only clusters anchor at the '-' entry's tracked
    new_line — the HEAD line before which the content was removed — so the
    anchor stays comparable with golden lines recorded against HEAD even
    when earlier lines in the hunk shifted the count (old-file numbering
    would drift); the old-file line rides along on each '-' entry for
    display. Deterministic."""
    CTX = 4
    per_file, cur_file, entries = [], None, []
    old_line = new_line = hunk_start = hunk_end = 1
    awaiting_hunk = True  # m2 (r6): plain unified diffs start at `--- `
                          # with no `diff --git` line before them
    old_left = new_left = 0  # m1 (r7): remaining hunk content counts
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            # M3 (r4): the `diff --git a/X b/X` header names the NEXT file —
            # flush the previous file here so no header lines (index/,
            # mode/rename lines) of the new file can leak into the old
            # file's last window as fake context.
            if cur_file is not None:
                per_file.append((cur_file, entries))
            cur_file, entries = None, []
            awaiting_hunk = True
            continue
        if awaiting_hunk and line.startswith("--- "):
            # M3 (r4): for a whole-file deletion this is the ONLY place the
            # real file name appears (new side is /dev/null) — keep it as
            # the FALLBACK. M1 (r6): the new side wins otherwise, because
            # line numbers are HEAD-side and renames must report the new
            # path. Header prefixes are ONLY headers here, before the first
            # @@ — inside a hunk, `--- text` is a removed line whose content
            # starts with `-- ` (SQL/Lua comments, diff-like text).
            old_path = line[4:].split("\t", 1)[0]
            if old_path != "/dev/null" and cur_file is None:
                cur_file = old_path[2:] if old_path.startswith("a/") else old_path
            continue
        if awaiting_hunk and line.startswith("+++ "):
            # M1 (r6): the +++ path is authoritative unless /dev/null (a
            # whole-file deletion has no new side). Never flush the previous
            # file here: `diff --git` already did that.
            new_path = line[4:].split("\t", 1)[0]
            if new_path != "/dev/null":
                cur_file = new_path[2:] if new_path.startswith("b/") else new_path
            continue
        if awaiting_hunk and line.startswith(("index ", "old mode ", "new mode ",
                                              "new file mode", "deleted file mode",
                                              "similarity index", "rename from",
                                              "rename to", "copy from", "copy to",
                                              "Binary files", "GIT binary patch")):
            continue
        if line.startswith("@@"):
            awaiting_hunk = False
            m = HUNK_RE.match(line)
            old_line = int(m.group(1)) if m else 1
            new_line = int(m.group(3)) if m else 1
            # m1 (r7): remaining content counts from the @@ header. When
            # both hit 0, a following `--- `/`+++ ` line is the next file's
            # header (plain multi-file unified diffs), never content.
            old_left = (int(m.group(2)) if (m and m.group(2)) else 1) if m else 0
            new_left = (int(m.group(4)) if (m and m.group(4)) else 1) if m else 0
            hunk_start = new_line
            # m5 (r3)/M3 (r4): where the hunk's new side ends. Omitted
            # count means 1; count 0 (pure-deletion hunk) means git's
            # start N is "after line N", i.e. the file ends at N — the
            # clamp target for trailing deletions. Deletions never
            # anchor past this line.
            if m:
                new_count = int(m.group(4)) if m.group(4) else 1
                hunk_end = new_line if new_count == 0 else new_line + new_count - 1
                hunk_end = max(1, hunk_end)
            else:
                hunk_end = new_line
        elif cur_file is not None:
            # m1 (r7): once a hunk's declared content counts are exhausted,
            # a `--- `/`+++ ` line is the NEXT file's header (plain
            # multi-file unified diffs) — flush and re-enter header state.
            # Checked FIRST: it outranks the +/- content handlers.
            if (line.startswith(("--- ", "+++ "))
                    and old_left <= 0 and new_left <= 0):
                if entries:
                    per_file.append((cur_file, entries))
                cur_file, entries = None, []
                awaiting_hunk = True
                old_left = new_left = 0
                if line.startswith("--- "):
                    old_path = line[4:].split("\t", 1)[0]
                    if old_path != "/dev/null":
                        cur_file = (old_path[2:] if old_path.startswith("a/")
                                    else old_path)
                else:
                    new_path = line[4:].split("\t", 1)[0]
                    if new_path != "/dev/null":
                        cur_file = (new_path[2:] if new_path.startswith("b/")
                                    else new_path)
                continue
            if line.startswith("diff ") and old_left <= 0 and new_left <= 0:
                # m1 (r8): `diff -ruN a/x b/x` separators from recursive
                # plain diffs arrive between files — ignore them; the
                # following ---/+++ pair does the real work.
                continue
            # M2 (r5): inside a hunk EVERY +/- prefix is content — real file
            # headers were consumed above (gated on awaiting_hunk).
            if line.startswith("+"):
                entries.append(("+", new_line, line[1:], hunk_start))
                new_line += 1
                new_left -= 1
            elif line.startswith("-"):
                # m5 (r3): clamp the tracked HEAD position to the hunk's
                # new-side end — a trailing deletion's raw new_line is
                # len(HEAD)+1, which doesn't exist.
                entries.append(("-", old_line, line[1:], hunk_start,
                                max(1, min(new_line, hunk_end))))
                old_line += 1
                old_left -= 1
            elif line.startswith("\\"):
                pass  # "\ No newline at end of file" markers never count
            else:
                entries.append((" ", new_line, line[1:], hunk_start))
                new_line += 1
                old_line += 1
                old_left -= 1
                new_left -= 1
    if cur_file is not None:
        per_file.append((cur_file, entries))

    hunks = []
    for fname, ents in per_file:
        # hunk-boundary segments: no cluster/window crosses an @@
        segments, cur_seg, cur_hs = [], [], None
        for e in ents:
            if cur_seg and e[3] != cur_hs:
                segments.append((cur_hs, cur_seg))
                cur_seg = []
            cur_hs = e[3]
            cur_seg.append(e)
        if cur_seg:
            segments.append((cur_hs, cur_seg))

        for seg_hunk_start, seg in segments:
            changed = [i for i, e in enumerate(seg) if e[0] != " "]
            if not changed:
                continue
            # group changed indices into runs of contiguous changed lines
            groups, run = [], [changed[0]]
            for i in changed[1:]:
                if i - run[-1] <= 1:
                    run.append(i)
                else:
                    groups.append(run)
                    run = [i]
            groups.append(run)
            for g in groups:
                # E2: expand the window outward from the cluster's own run
                # over context lines only, within ±CTX and the hunk bounds.
                # Expansion stops at any neighbouring cluster's +/- entry,
                # so a neighbour's changed lines never appear — not even as
                # "context"; only shared context lines may.
                foreign = set()
                for g2 in groups:
                    if g2 is not g:
                        foreign.update(range(g2[0], g2[-1] + 1))
                lo = g[0]
                while lo - 1 >= max(0, g[0] - CTX) and (lo - 1) not in foreign:
                    lo -= 1
                hi = g[-1] + 1
                while hi < min(len(seg), g[-1] + CTX + 1) and hi not in foreign:
                    hi += 1
                window = seg[lo:hi]
                # anchor chain (plan Task 2): first '+' in the cluster's own
                # run, never a neighbouring cluster's window; then the first
                # context entry with a lineno at/after the run; then the run's
                # hunk_start
                anchor = next((e[1] for e in seg[g[0]:g[-1] + 1]
                               if e[0] == "+" and e[1] is not None), None)
                if anchor is None:
                    # deletion-only cluster: anchor at the position in HEAD
                    # where the line was removed (M2, r2) — the '-' entry's
                    # tracked new_line, correct even when earlier lines in
                    # the hunk shifted the count (the old-file line is kept
                    # on the entry for display)
                    anchor = next((e[4] for e in seg[g[0]:g[-1] + 1]
                                   if e[0] == "-" and e[4] is not None), None)
                if anchor is None:
                    anchor = next((e[1] for e in seg[g[-1] + 1:hi]
                                   if e[0] == " " and e[1] is not None), None)
                if anchor is None:
                    anchor = seg_hunk_start
                lines, n_changed = [], 0
                for w in window:
                    k, n, t, _ = (w[0], w[1], w[2], w[3])
                    if k == "+":
                        lines.append(f"{n}: + {t}")
                    elif k == "-":
                        lines.append("    - " + t)
                    else:
                        lines.append(f"{n}:   {t}")
                # count only THIS cluster's changed lines: a neighbour's
                # changed lines may appear as context but are not ours
                n_changed = len(g)
                hunks.append({
                    "file": fname, "line": anchor,
                    "hunk_start": seg_hunk_start,
                    "header": f"@@ {fname} around line {anchor} "
                              f"({n_changed} changed lines) @@",
                    "lines": lines, "entries": window,
                    "n_changed": n_changed,
                })
    for h in hunks:
        h["size"] = len(h["lines"])
        h["too_large"] = h["size"] > MAX_HUNK_LINES
    return hunks


def triage(hunks):
    """Deterministic skip: lockfiles, generated dirs, docs-only runs."""
    kept, skipped = [], []
    for h in hunks:
        f = h["file"] or ""
        if SKIP_PATTERNS.search(f) or DOC_EXT.search(f):
            skipped.append({"file": f, "reason": "docs/generated/lockfile"})
        elif h["too_large"]:
            skipped.append({"file": f, "reason": f"hunk>{MAX_HUNK_LINES} lines"})
        else:
            kept.append(h)
    return kept, skipped


HUNK_QUESTIONS = {
    "severity": {
        "type": "score",
        "instructions": "How severe is the most serious problem in this code-change hunk?",
        "criteria": [
            "No real problem; the change is fine",
            "Minor: style, naming, small cleanup",
            "Major: likely bug, wrong logic, missing error handling",
            "Blocker: will break builds, tests, security, or data",
        ]},
    "is_real_issue": {
        "type": "noul",
        "instructions": "Does this hunk contain a genuine issue worth a reviewer comment?"},
    "category": {
        "type": "choice",
        "instructions": "What kind of issue is it, if any?",
        "criteria": {
            "bug-risk": "Likely bug, wrong logic, or missing error handling",
            "security": "Security vulnerability or unsafe handling of secrets/input",
            "style": "Style, naming, formatting, or duplication",
            "performance": "Performance or resource-usage problem",
            "test-gap": "Change lacks test coverage it clearly needs",
            "other": "Any other issue worth noting",
        }},
}

PR_QUESTIONS = {
    "overall_risk": {
        "type": "score",
        "instructions": "How risky is this change set to merge as-is?",
        "criteria": [
            "Safe: docs, tests, trivial",
            "Low: routine feature/refactor",
            "Elevated: touches logic, error paths, or concurrency",
            "High: security, data integrity, or breaking change",
        ]},
    "needs_human_review": {
        "type": "noul",
        "instructions": "Should a human reviewer look at this change set beyond this automated report?"},
}


# ---------- judge + compose ----------

def hunk_state(h):
    """Structured before/after state, read from `entries` only (never the
    rendered lines, which can corrupt text containing ': + ')."""
    before, after = [], []
    for w in h["entries"]:
        kind, _n, text = w[0], w[1], w[2]
        if kind == "+":
            after.append(text)
        elif kind == "-":
            before.append(text)
        else:
            before.append(text)
            after.append(text)
    return {
        "file": h["file"],
        "location": f"around line {h['line']}",
        "code_before_change": before,
        "code_after_change": after,
    }


def judge(hunks, ask):
    """ask is the wired provider's ask(state, questions) (E8 contract)."""
    findings, latencies, failures = [], [], 0
    parse_failures = 0  # M1 (r8): consecutive shape errors, separate counter
    kept_hunks = len(hunks)
    for h in hunks:
        state = hunk_state(h)
        try:
            payload, ms = ask(state, HUNK_QUESTIONS)
            latencies.append(ms)
            failures = 0
        except Exception:
            failures += 1
            if failures >= CALL_FAIL_LIMIT:
                return None, latencies  # fail-open signal
            # M2 (r9): record the failed call so the incomplete-review
            # downgrade can see it (a 1-cluster diff can never reach the
            # consecutive limit, but its failure must not vanish).
            findings.append({"hunk": h, "parse_error": True,
                             "raw": None, "latency_ms": 0.0})
            continue
        try:
            ans = payload["answers"]
            sev = ans["severity"]
            real = ans["is_real_issue"]
            cat = ans["category"]
            score = float(sev.get("score", 0))
            noul = real.get("noul")
            # m1 (r10): json.loads accepts NaN/Infinity literals and
            # non-numeric types slip through float() — check finiteness up
            # front so sev_level/judge_pr_level can't crash the run later.
            if not math.isfinite(score):
                raise ValueError(f"non-finite severity score: {score!r}")
            if not isinstance(noul, (int, float, bool)) or \
                    not math.isfinite(float(noul)):
                raise ValueError(f"non-numeric noul: {noul!r}")
            rec = {
                "hunk": h,
                "severity": score,
                "sev_dist": sev.get("probabilities"),
                "confidence": sev.get("confidence"),
                "is_real": noul,
                "category": cat.get("choice"),
                "cat_dist": cat.get("probabilities"),
                "latency_ms": round(ms, 1),
            }
            findings.append(rec)
            parse_failures = 0
        except (KeyError, TypeError, AttributeError, ValueError):
            # M1 (r7)/m2 (r9): shape errors count toward fail-open — a wrong
            # response shape on every call is a broken/changed API, not a
            # set of harmless per-hunk misses. ValueError covers non-numeric
            # scores ("high"), which would otherwise kill the whole run.
            # The counter is separate from transport failures: transport
            # success resets `failures`, so a run of 200-with-garbage
            # responses could otherwise never reach the limit.
            parse_failures += 1
            # m3 (r11): `failures` is deliberately SHARED between transport
            # and parse failures — any repeated failure pattern (mixed
            # causes included) means the provider is not trustworthy for
            # this run, so reaching CALL_FAIL_LIMIT by any combination
            # fails open. `parse_failures` additionally catches consecutive
            # same-cause shape errors.
            failures += 1
            if parse_failures >= CALL_FAIL_LIMIT or failures >= CALL_FAIL_LIMIT:
                return None, latencies  # fail-open signal
            findings.append({"hunk": h, "parse_error": True,
                             "raw": payload, "latency_ms": round(ms, 1)})
    # M2 (r9), the reviewer's stronger option: if EVERY call failed
    # (nothing was ever judged), that is a dead provider — full fail-open
    # regardless of the consecutive-counter arithmetic. m1 (r11): a
    # 200-with-garbage provider never appends a latency either, so
    # "nothing judged" means no successful parse, not just no transport
    # success.
    if kept_hunks and not any(not f.get("parse_error") for f in findings):
        return None, latencies
    return findings, latencies


def judge_pr_level(findings, ask):
    """One extra round-trip: PR-level risk from the per-hunk digest."""
    prov_name = _PROVIDER_NAME  # r9 m1: the wired provider, not the env
    # m2 (r10): failed calls must not look like clean hunks — label them
    # "unjudged" so the PR-level model can't read them as severity=none.
    digest = "\n".join(
        (f"- {f['hunk']['file']}:{f['hunk']['line']} unjudged "
         f"(provider call failed)"
         if f.get("parse_error") else
         f"- {f['hunk']['file']}:{f['hunk']['line']} "
         f"severity={SEV_NAME[sev_level(f.get('severity'))]} "
         f"category={f.get('category')}")
        for f in findings) or "no per-hunk findings"
    try:
        payload, ms = ask(
            "Change set under review, per-hunk automated digest:\n" + digest,
            PR_QUESTIONS)
        ans = payload["answers"]
        return {"overall_risk": float(ans["overall_risk"].get("score", 0)),
                "needs_human_review": ans["needs_human_review"].get("noul"),
                "latency_ms": round(ms, 1)}
    except Exception as exc:
        return {"overall_risk": None, "needs_human_review": None,
                "error": f"pr-level model call failed ({prov_name}): {exc!r}"[:300]}


def near(v, t, zone=0.03):
    return v is not None and abs(v - t) <= zone


def compose(findings, skipped, pr_level, threshold=REAL_THRESHOLD):
    """Thresholds in code. Plateau rule: 0.50 sits >=0.05 from 0.80/0.90."""
    reported, jitter = [], []
    for f in findings:
        if f.get("parse_error"):
            continue
        r = f.get("is_real")
        if near(r, threshold):
            jitter.append({"file": f["hunk"]["file"], "is_real": r})
        if r is not None and r >= threshold and (f.get("severity") or 0) >= 1:
            reported.append(f)
    blockers = [f for f in reported if sev_level(f.get("severity")) == 3]
    majors = [f for f in reported if sev_level(f.get("severity")) == 2]
    verdict = "Changes requested" if (blockers or len(majors) >= 2) else "Approved"
    return reported, jitter, verdict


# ---------- measurement ----------

def log_run(record):
    os.makedirs(os.path.dirname(METRICS_PATH), exist_ok=True)
    record["ts"] = datetime.now(timezone.utc).isoformat()
    with open(METRICS_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def eval_negative(reported):
    """False-positive census on an all-benign diff (m4: counting never
    filters on --negative-golden; that flag only triggers/documents this
    evaluation). minor-note := sev_level(severity)==1 and category=='style'.
    """
    counts = {"blocker_major": 0, "minor_notes": 0, "other_fp": 0}
    for f in reported:
        if f.get("severity") is None:
            continue
        lvl = sev_level(f.get("severity"))
        if lvl >= 2:
            counts["blocker_major"] += 1
        elif lvl == 1 and f.get("category") == "style":
            counts["minor_notes"] += 1
        else:
            counts["other_fp"] += 1
    return counts


def eval_against_golden(reported, golden_path):
    """Precision/recall/F1 of reported findings vs a golden issues file.

    Golden format, one issue per line:  <file>\t<line>\t<description>
    Matching (Task 3): a reported finding matches a golden issue when the
    file matches and the reported line is within +/-1 of the golden line;
    ties go to the lower golden line, and each golden issue matches at most
    one reported finding (nearest distance wins). tp_severities records the
    sev_level() class of every true positive.
    """
    golden = []
    with open(golden_path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    golden.append((parts[0], int(parts[1]), parts[2] if len(parts) > 2 else ""))
    matched_golden, matched_reported = set(), set()
    chosen = []  # (reported_idx, golden_idx) pairs the greedy pass kept
    matches = []  # (distance, reported_idx, golden_idx)
    for i, f in enumerate(reported):
        for j, (gfile, gline, gdesc) in enumerate(golden):
            if f["hunk"]["file"] == gfile and abs(f["hunk"]["line"] - gline) <= 1:
                matches.append((abs(f["hunk"]["line"] - gline), i, j))
    matches.sort(key=lambda m: (m[0], golden[m[2]][1], m[1]))
    # nearest first; distance ties -> lower golden line -> earlier reported
    for _d, i, j in matches:
        if i in matched_reported or j in matched_golden:
            continue
        matched_reported.add(i)
        matched_golden.add(j)
        chosen.append((i, j))
    tp = len(matched_reported)
    precision = tp / len(reported) if reported else None
    recall = len(matched_golden) / len(golden) if golden else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall > 0 else None)
    return {"golden_issues": len(golden), "reported": len(reported),
            "true_positives": tp, "precision": precision,
            "recall": recall, "f1": f1,
            "tp_severities": sorted(sev_level(reported[i].get("severity"))
                                    for i in matched_reported),
            # m1: only the pairs the greedy selection actually chose — never
            # more entries than true_positives (display order: reported index)
            "matched": [(golden[j][0], golden[j][1])
                        for i, j in sorted(chosen, key=lambda p: p[0])],
            # indices into `reported` the greedy selection matched (M3, r2:
            # lets callers derive false positives from this exact matching)
            "matched_reported": sorted(matched_reported),
            "missed": [g for j, g in enumerate(golden) if j not in matched_golden]}


# ---------- report ----------

def render(reported, skipped, verdict, pr_level, jitter, meta):
    prov = meta.get("provider", "jev")
    model = meta.get("model")
    prov_name = f"{prov}/{model}" if (prov == "laya" and model) else prov
    out = [f"SYSTEM-ONE REVIEW (experimental local reviewer — advisory only, provider: {prov_name})"]
    out.append(f"repo={meta['repo']} mode={meta['mode']} head={meta['head'][:10]}")
    out.append(f"analyzed={meta['n_analyzed']} hunks, "
               f"skipped={len(skipped)}, "
               f"total_latency={meta['total_latency_ms']:.0f}ms, "
               f"model_calls={meta['jev_calls']}")
    if meta.get("fail_open"):
        out.append(f"!! {prov_name} unavailable after repeated failures — "
                   "heuristic-only run, treat as triage not review")
    out.append("")
    if not reported:
        out.append("No findings above threshold.")
    for f in reported:
        sev = SEV_NAME.get(sev_level(f.get("severity")), "?")
        out.append(f"[{sev}] {f['hunk']['file']}:{f['hunk']['line']} "
                   f"({f.get('category')}, is_real={f.get('is_real')})")
        out.append(f"  hunk: {f['hunk']['header']}")
        for l in f["hunk"]["lines"][:6]:
            out.append("    " + l)
        out.append("")
    if jitter:
        out.append("Jitter-zone scores (within 0.03 of threshold — do not trust):")
        for j in jitter:
            out.append(f"  {j['file']} is_real={j['is_real']}")
        out.append("")
    if pr_level and pr_level.get("overall_risk") is not None:
        out.append(f"PR-level risk: {pr_level['overall_risk']}/3, "
                   f"needs_human_review={pr_level.get('needs_human_review')}")
    if skipped:
        out.append("Skipped (deterministic triage): " +
                   ", ".join(f"{s['file']} ({s['reason']})" for s in skipped[:10]))
    out.append("Verdict: " + verdict)
    # m3 (r10)/M2 (r11): the last line is a CLOSED SET for grep-ledgering —
    # detail lives on the Verdict: line above, never here. The incomplete
    # suffix can ride on "Changes requested" too, so match it anywhere.
    if verdict.startswith("Unavailable"):
        out.append("Unavailable")
    elif "(incomplete" in verdict:
        out.append("Incomplete")
    else:
        out.append(verdict)  # "Approved" / "Changes requested"
    return "\n".join(out)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(prog="system-one-reviewer")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--range", dest="range")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--uncommitted", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--max-hunks", type=int, default=40)
    ap.add_argument("--golden")
    ap.add_argument("--negative-golden", dest="negative_golden")
    ap.add_argument("--fixture", choices=sorted(KNOWN_FIXTURES),
                    help="which committed fixture this run exercises "
                         "(recorded in metrics)")
    ap.add_argument("--label", default="")
    ap.add_argument("--provider", choices=list(PROVIDERS),
                    help="judgment provider: jev (hosted, default) or "
                         "laya (local); SOR_PROVIDER env is the default")
    ap.add_argument("--model",
                    help="model/checkpoint for the laya provider "
                         f"(default {LAYA_DEFAULT_MODEL})")
    ap.add_argument("--json", action="store_true", help="JSON-only stdout")
    args = ap.parse_args()

    provider, model = provider_from(args.provider, args.model)
    if provider == "laya":
        laya_ask_or_die(model=model)  # fail fast on a missing local stack
        api_key = None
    else:
        api_key = load_api_key()
    ask = make_provider(provider, model, api_key)
    diff, head, mode = resolve_diff(args.repo, args)
    hunks = package_hunks(diff)
    kept, skipped = triage(hunks)
    n_triaged = len(hunks) - len(kept)  # deliberate skips, NOT drops (r10 M1)
    kept.sort(key=lambda h: -h["size"])
    kept = kept[: args.max_hunks]
    n_dropped = len(hunks) - n_triaged - len(kept)  # --max-hunks truncation only

    findings, latencies = judge(kept, ask)
    fail_open = findings is None
    if fail_open:
        findings = []
    else:
        pr_level = judge_pr_level(findings, ask)
    # M1 (r9): a fail-open run must never carry a clean "Approved" — the
    # verdict is forced to "Unavailable" and flows into JSON/metrics/last
    # line, so nothing downstream reads it as a pass.
    # M2 (r9): on a non-fail-open run, unjudged clusters (parse errors or
    # dropped over max-hunks) downgrade the verdict so partial reviews are
    # never mistaken for complete ones.
    reported, jitter, verdict = compose(findings, skipped,
                                        pr_level if not fail_open else None)
    n_unjudged = sum(1 for f in findings if f.get("parse_error"))
    if fail_open:
        verdict = "Unavailable — provider failed (fail-open)"
    elif n_unjudged or n_dropped:
        verdict += (f" (incomplete review — {len(kept) - n_unjudged} of "
                    f"{len(hunks) - n_triaged} clusters judged)")

    total = sum(latencies)
    judged = [
        {"file": f["hunk"]["file"], "line": f["hunk"]["line"],
         "severity": f.get("severity"), "is_real": f.get("is_real"),
         "category": f.get("category"), "confidence": f.get("confidence"),
         "reported": f in reported}
        for f in findings if not f.get("parse_error")]
    meta = {"repo": os.path.basename(args.repo), "mode": mode, "head": head,
            "provider": provider, "model": model,  # M3 (r11): report/metadata
            "n_hunks": len(hunks), "n_analyzed": len(kept),
            "total_latency_ms": total, "jev_calls": len(latencies),
            "fail_open": fail_open}

    result = {"meta": meta, "pr_level": pr_level if not fail_open else None,
              "findings": [
                  {"file": f["hunk"]["file"], "line": f["hunk"]["line"],
                   "severity": f.get("severity"), "is_real": f.get("is_real"),
                   "category": f.get("category"), "header": f["hunk"]["header"]}
                  for f in reported],
              "skipped": skipped, "jitter": jitter, "verdict": verdict}

    golden_eval = None
    if args.golden:
        golden_eval = eval_against_golden(reported, args.golden)
        result["golden_eval"] = golden_eval
    if args.negative_golden:
        neg = eval_negative(reported)
        if golden_eval is None:
            golden_eval = {}
        golden_eval["negative_eval"] = neg
        result["golden_eval"] = golden_eval

    log_run({"label": args.label, "repo": meta["repo"], "mode": mode,
             "head": head[:10], "n_hunks": meta["n_hunks"],
             "n_analyzed": meta["n_analyzed"], "verdict": verdict,
             "fail_open": fail_open, "total_latency_ms": round(total, 1),
             "avg_call_ms": round(total / len(latencies), 1) if latencies else None,
             "judged": judged,
             "packaging_version": PACKAGING_VERSION,
             "provider": provider, "model": model,
             "fixture": args.fixture,
             "fixture_head": head,
             "findings": result["findings"], "jitter": jitter,
             "pr_level": result["pr_level"], "golden_eval": golden_eval})

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(render(reported, skipped, verdict,
                     result["pr_level"], jitter, meta))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, default=str)


if __name__ == "__main__":
    main()
