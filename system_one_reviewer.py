#!/usr/bin/env python3
"""system-one-reviewer — local PR review powered by deterministic code + a system
one model (hosted Jev or local Laya).

Experimental (D1, Kurt 2026-09-27): an ADDITIONAL lightweight reviewer for
Tessera on the ThinkPad. Runs in seconds, costs fractions of a cent, use
freely and often. Posts nothing anywhere; prints a report, optionally JSON.

Design (v0.2, evaluation-hardened):
  1. gather   — git plumbing computes diff/head (--range reviews the
                merge-base diff A...B; --pr uses the same form)
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
import ast
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
# Option 2 (r8-M2 escalation, Kurt APPROVED 2026-10-02): the ~120-line AST
# engagement threshold for the 121-line…84k-char band. A unit whose span
# exceeds BAND_ENGAGE_LINES engages the Task 2/3 cutter even when its
# serialized estimate is under the token gate, so band clusters are judged
# in windows with per-window anchors instead of as ONE whole-call anchor
# (the importMachine.ts failure the G-D band check measured: judged whole,
# reported 2-of-6, band goldens missed). The token gate (r1-M4) stays the
# PRIMARY engagement — oversize is tested first; band is additive.
BAND_ENGAGE_LINES = 120
# Token-based call budgets (AST-units plan Task 1; brief rev 6 :263):
# the 32k budget covers `state` plus the single LONGEST question — that
# is the quantity estimate_call_size measures, not the all-questions
# wire total (r2-M5). CHARS_PER_TOKEN=3.0 is the brief's code-dense-JSON
# prior; dividing question chars by 3.0 too is a deliberate CONSERVATIVE
# deviation from the brief's exact-question-sum (it over-estimates,
# never under). MAX_HUNK_LINES itself is retired in Task 4.
SOFT_CAP_TOKENS = 28_000      # over this: split before judging (Task 5)
HARD_CAP_TOKENS = 56_000      # over this: never send (Task 5 send-gate)
CHARS_PER_TOKEN = 3.0
# Line-window fallback SIZE (plan Task 3, FALLBACK_WINDOW_LINES): this is
# a window SIZE choice only, never an engagement or skip test — the
# arbitrary-ness concern was about SKIPPING on a line count, not about
# how wide a fallback window is. Engagement is token-based everywhere
# (r1-M4: estimate_call_size > SOFT_CAP_TOKENS).
FALLBACK_WINDOW_LINES = 120
CALL_FAIL_LIMIT = 2           # consecutive Jev failures -> fail-open
# Rubric thresholds (v0.3b, Kurt review): the 0.50 plateau was calibrated
# on code-change answers. The deletion rubric asks a different question, so
# its answers are NOT assumed to land on the same distribution — it gets
# its own threshold until the v0.3 sweep measures the deletion-rubric
# is_real distribution and justifies a number. Starting CONSERVATIVE
# (0.70): a deletion finding must clear a higher bar to be reported at
# all, because #45 showed deletion clusters over-scoring, not
# under-scoring. Both stay >=0.05 from the 0.80/0.90 upper region.
REAL_THRESHOLD = 0.50           # code-change rubric (calibrated, v02 sweep)
DELETION_REAL_THRESHOLD = 0.70  # deletion rubric (provisional; sweep TBD)
KNOWN_FIXTURES = {"positive", "negative"}
# v03b (field evals, 2026-09-28, Kurt review round): model input changed
# AGAIN — references_remaining in state, three-valued change_type,
# rewritten deletion rubric, per-rubric thresholds, corroboration gate in
# compose. Ledger records produced from different input shapes must never
# share a version tag. (v03 negative benchmark superseded: its
# fixture_head predates the deletion cluster in the negative fixture.
# Per-run build provenance lives in
# docs/benchmarks/2026-09-28-v03b-branch-benchmark.md.)
# v08-ast (AST-units plan Task 7): model input changed AGAIN — oversize
# clusters cut into AST sub-clusters (Tasks 2/3), a 32k token budget guard
# bounds every payload (Task 5), and states carry ast_context enrichment
# (Task 6). The ledger stamps transport/wire_format/enrichment/record_version
# (D7) so replay baselines are only ever compared like-for-like. v03b
# ledgers remain gateable under an explicit --packaging-version v03b.
PACKAGING_VERSION = "v08-ast"
# Release version, stamped by scripts/build_release.py during semantic-release
# (tags vX.Y.Z). Distinct from PACKAGING_VERSION, which versions the scoring
# rubric the threshold sweep gates on.
__version__ = "0.7.0"


def sev_level(v):
    """Nearest integer level, halves round up (2.5 is a BLOCKER)."""
    if v is None:
        return 0
    return max(0, min(3, math.floor(v + 0.5)))

SEV_NAME = {0: "none", 1: "MINOR", 2: "MAJOR", 3: "BLOCKER"}
CATEGORIES = ["bug-risk", "security", "style", "performance", "test-gap", "other"]
SKIP_PATTERNS = re.compile(
    r"(^|/)(package-lock\.json|yarn\.lock|Cargo\.lock|poetry\.lock|"
    r"pnpm-lock\.yaml|uv\.lock|Gemfile\.lock|composer\.lock|Pipfile\.lock|"
    r"flake\.lock|bun\.lockb?|go\.sum|"
    r"LICENSE|COPYING|\.gitignore|\.editorconfig)$"
    r"|(^|/)(dist|build|target|node_modules|\.min\.(js|css))(/|$)"
    r"|^(CHANGELOG|AUTHORS|CONTRIBUTORS)"
)
DOC_EXT = re.compile(r"\.(md|mdx|txt|rst|adoc)$", re.I)
# Data ledgers, tabular fixtures and test snapshots: the hunk rubric asks
# about code bugs, so judging a metrics.jsonl line just prints the record
# back as a "finding" (first live install run, 2026-09-28). .json stays
# judged — package.json/tsconfig changes are real config changes.
DATA_EXT = re.compile(r"\.(jsonl|ndjson|csv|tsv|snap)$", re.I)

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
        _conn = HTTPSConnection(_url.hostname or "", _url.port or 443,
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


class _OverBudget(_NoRetry):
    """Plan Task 5 (r8-m1): the provider rejected a call with HTTP 400
    `max_tokens_exceeded` — the payload did not fit the model's budget.

    A SUBCLASS of _NoRetry so the handler's re-raise-untouched semantics
    apply mechanically: an over-budget 400 is never given the 5xx retry
    (a wasted over-budget resend). jev_ask-internal — laya never
    observes it (D6: its transport never calls jev_ask). judge() catches
    this BEFORE its generic `except Exception` and drives the halve-
    and-retry split.
    """


def _is_max_tokens_body(raw):
    """True when the HTTP body matches the over-budget shape: the
    `error_type` field carrying `max_tokens_exceeded` (community-measured
    400 body, 2026-09 probes). Case-insensitive, any nesting.
    r15-m7 (Opus Task-10 review): the previous `max_tokens` + `exceed`
    two-word match also caught PARAMETER-validation 400s ("max_tokens
    must not exceed N"), sending healthy units into split cascades —
    the marker must name the OVER-BUDGET error type, not mention the
    parameter."""
    try:
        text = raw.decode("utf-8", "replace").lower()
    except Exception:
        return False
    return "max_tokens_exceeded" in text


def payload_over_hard_cap(state, questions):
    """The SEND gate (plan Task 5, r1-m2): the serialized wire total —
    `state` plus ALL questions, exactly what one HTTP call carries —
    must stay <= HARD_CAP_TOKENS. Defense-in-depth behind the pre-judge
    soft-cap pass (Task 4): the estimator's per-call quantity is state +
    longest question, so this gate is what guarantees nothing over the
    hard cap is ever SENT."""
    total_chars = len(json.dumps(state)) + sum(
        len(json.dumps(q)) for q in questions.values())
    return total_chars / CHARS_PER_TOKEN > HARD_CAP_TOKENS


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
                # Task 5 (r8-m1): the max_tokens_exceeded body check runs
                # BEFORE the _NoRetry raise (raw is inspected on this >=400
                # path) — _OverBudget is a _NoRetry subclass, so it too is
                # re-raised untouched and never given the 5xx retry.
                if resp.status < 500:
                    if _is_max_tokens_body(raw):
                        raise _OverBudget(
                            f"HTTP {resp.status}: {raw[:200]!r}")
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


def estimate_call_size(state, questions):
    """Estimated TOKENS for one model call (AST-units plan Task 1).

    Measures the 32k-rule quantity: the serialized `state` plus the
    serialized LONGEST question — not the all-questions total (r2-M5;
    the full payload is lower-bounded by this and capped by the Task 5
    HARD_CAP send-gate). Deviation note (r7-nit): the brief sums the
    question map exactly and estimates only the state; this estimator
    divides the longest question's chars by CHARS_PER_TOKEN too — a
    deliberate conservative deviation (over-estimates, never under).
    Pure and deterministic; no caching (YAGNI).
    """
    state_json = json.dumps(state)
    longest_q = max(len(json.dumps(q)) for q in questions.values())
    return (len(state_json) + longest_q) / CHARS_PER_TOKEN


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

        def jev_provider_ask(state, questions):
            return jev_ask(state, questions, key)

        set_transport(jev_provider_ask)
        set_provider_name("jev")
        return jev_provider_ask
    # laya: local inference; the router loads lazily on first call and is
    # kept for the process lifetime.
    def laya_provider_ask(state, questions):
        router = get_laya_router(model=model)
        return laya_ask(router, state, questions)

    set_transport(laya_provider_ask)
    set_provider_name(f"laya/{model}" if model else "laya")
    return laya_provider_ask


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


GIT_PROBE_TIMEOUT = 30  # seconds; rev-parse is instant unless git is stuck


def _git_probe(repo, *args):
    """Cheap up-front git check -> returncode. Bounded: a stalled git
    (hung network FS, index lock) must not block the CLI forever."""
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                              text=True, timeout=GIT_PROBE_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        sys.exit(f"system-one-reviewer: git {' '.join(args)} timed out after "
                 f"{GIT_PROBE_TIMEOUT}s in {repo!r}")


def resolve_diff(repo, args):
    """Return (diff_text, head_sha, mode).

    fixture_head semantics (m2 disposition): the logged `fixture_head` is
    the checkout HEAD (git rev-parse HEAD), not the tip of --range and not
    the reviewed commit itself. For a committed fixture this is exactly the
    SHA the sweep gates on (--staged/--uncommitted review HEAD's tree, so
    the same value is correct there); only a range that does not END at
    HEAD would diverge, which the committed fixtures never do.
    """
    # Checked up front: a bad --repo otherwise surfaces as git diff's full
    # usage text (outside a work tree `git diff` falls back to --no-index).
    if _git_probe(repo, "rev-parse", "--git-dir") != 0:
        sys.exit(f"system-one-reviewer: {repo!r} is not a git repository")
    if args.range:
        # F5 (field evals, 2026-09-28): merge-base diff, matching the
        # documented behavior and --pr. A..B on a stale base showed
        # post-branch main-side changes as deletions (false-FP machine).
        spec = triple_dot(args.range)
        # v0.3b (Kurt review): HEAD is a fine fixture sentinel, but the
        # ledger must record what was DIFFED. triple_dot can pass bare
        # specs through (a single SHA) — those have no right-hand side, so
        # reject them loudly BEFORE diffing, not with an IndexError
        # traceback afterwards (Opus r2 M1).
        if "..." not in spec:
            sys.exit("system-one-reviewer: --range needs A..B or A...B; "
                     f"a bare {spec!r} has no right-hand tip to record")
        diff = run_git(repo, "diff", spec)
        # r3 m3 (Opus): `A...` with an empty right side means HEAD, same
        # as triple_dot's two-dot fill — don't pass an empty ref to git.
        right_ref = spec.rsplit("...", 1)[1] or "HEAD"
        head = run_git(repo, "rev-parse", "--verify",
                       f"{right_ref}^{{commit}}").strip()
        # mode records the spec actually diffed (r1-M3), so ledger readers
        # can't confuse pre/post-F5 records sharing a user-facing spelling.
        return diff, head, f"range:{spec}"
    if args.staged:
        return (run_git(repo, "diff", "--cached"),
                run_git(repo, "rev-parse", "HEAD").strip(), "staged")
    if args.uncommitted:
        return (run_git(repo, "diff"),
                run_git(repo, "rev-parse", "HEAD").strip(), "uncommitted")
    if args.pr:
        if _git_probe(repo, "rev-parse", "--verify", "--quiet",
                      f"pr/{args.pr}^{{commit}}") != 0:
            sys.exit(f"system-one-reviewer: no local ref pr/{args.pr} — run "
                     f"`git fetch origin pull/{args.pr}/head:pr/{args.pr}` "
                     "in the repo first")
        diff = run_git(repo, "diff", f"origin/main...pr/{args.pr}")
        head = run_git(repo, "rev-parse", f"pr/{args.pr}").strip()
        return diff, head, f"pr:{args.pr}"
    sys.exit("system-one-reviewer: pick one of --range/--pr/--staged/--uncommitted")


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def triple_dot(rng):
    """Rewrite a two-dot range spec to its merge-base form.

    `A..B` becomes `A...B`; an open-ended side is filled with HEAD first
    (`main..` -> `main...HEAD`, `..feature` -> `HEAD...feature`). Anything
    else (a bare SHA, a spec already in `...` form) passes through
    unchanged. `git diff A...B` reviews the branch's own changes against
    the merge-base, so a stale main never masquerades as deletions in the
    reviewed diff.
    """
    if rng.count("..") == 1 and "..." not in rng:
        left, right = rng.split("..", 1)
        left = left or "HEAD"
        right = right or "HEAD"
        return f"{left}...{right}"
    return rng


def _cluster_anchor(entries, seg_start, seg_end, hunk_start):
    """Shared anchor chain (plan Task 2, r1-M3): first '+' tracked line in
    seg[seg_start:seg_end] -> first '-' entry's e[4] (the tracked HEAD
    position where the line was removed — anchor-FALLBACK only, r5-M1)
    -> first context entry's line at/after the run -> the run's
    hunk_start. Used by BOTH package_hunks and sub-cluster assembly, so
    parent clusters and their sub-clusters anchor by the same rule."""
    anchor = next((e[1] for e in entries[seg_start:seg_end]
                   if e[0] == "+" and e[1] is not None), None)
    if anchor is None:
        anchor = next((e[4] for e in entries[seg_start:seg_end]
                       if e[0] == "-" and e[4] is not None), None)
    if anchor is None:
        anchor = next((e[1] for e in entries[seg_end:]
                       if e[0] == " " and e[1] is not None), None)
    return anchor if anchor is not None else hunk_start


def package_hunks(diff):
    """Cluster-level packaging: contiguous changed lines form a cluster, each
    with +/-4 context lines. Windows are clamped at @@ hunk boundaries (a
    cluster never crosses an @@ header) and trimmed at the neighbouring
    clusters' changed entries, so one change never dilutes another.
    Anchors: first '+' in the cluster's own run -> else the deletion site
    (first '-' in the run, at the position in HEAD where the line was
    removed) -> else the first context entry with a lineno at/after the run
    -> else the run's hunk_start. An IN-FILE deletion cluster never
    collapses to line 1; a WHOLE-FILE deletion does anchor at line 1
    (`@@ -1,N +0,0 @@` clamps hunk_end to 1 — seen throughout the #45
    field run). Deletion-only clusters anchor at the '-' entry's tracked
    new_line — the HEAD line before which the content was removed — so the
    anchor stays comparable with golden lines recorded against HEAD even
    when earlier lines in the hunk shifted the count (old-file numbering
    would drift); the old-file line rides along on each '-' entry for
    display. Deterministic."""
    CTX = 4
    per_file, cur_file = [], None
    # ('+', new_line, text, hunk_start) or, for deletions, the same plus the
    # clamped HEAD anchor — variable-length on purpose.
    entries: list[tuple] = []
    file_deleted = False  # v0.3b: the +++ side was /dev/null (whole-file deletion)
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
                per_file.append((cur_file, entries, file_deleted))
            cur_file, entries = None, []
            file_deleted = False
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
            if new_path == "/dev/null":
                file_deleted = True  # whole-file deletion (+++ /dev/null)
            else:
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
                    per_file.append((cur_file, entries, file_deleted))
                cur_file, entries = None, []
                file_deleted = False
                awaiting_hunk = True
                old_left = new_left = 0
                if line.startswith("--- "):
                    old_path = line[4:].split("\t", 1)[0]
                    if old_path != "/dev/null":
                        cur_file = (old_path[2:] if old_path.startswith("a/")
                                    else old_path)
                else:
                    new_path = line[4:].split("\t", 1)[0]
                    if new_path == "/dev/null":
                        file_deleted = True  # whole-file deletion
                    else:
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
        per_file.append((cur_file, entries, file_deleted))

    hunks = []
    for fname, ents, file_was_deleted in per_file:
        # hunk-boundary segments: no cluster/window crosses an @@
        segments: list[tuple] = []
        cur_seg: list = []
        cur_hs = None
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
                foreign: set[int] = set()
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
                # anchor chain via the SHARED helper (plan Task 2, r1-M3):
                # first '+' in the cluster's own run, never a neighbouring
                # cluster's window; then the first context entry with a
                # lineno at/after the run; then the run's hunk_start
                anchor = _cluster_anchor(seg, g[0], g[-1] + 1, seg_hunk_start)
                lines, n_changed = [], 0
                for w in window:
                    k, n, t, _ = (w[0], w[1], w[2], w[3])
                    if k == "+":
                        lines.append(f"{n}: + {t}")
                    elif k == "-":
                        lines.append("    - " + t)
                    else:
                        lines.append(f"{n}:   {t}")
                # corpus spec §1: cluster line span (new-file line numbers
                # covering the cluster's window). Deletion entries use the
                # tracked new line; missing entries drop out so a pure
                # insertion can't drag the span to a different hunk.
                span = [e[4] if e[0] == "-" else e[1] for e in window]
                span = [n for n in span if n is not None] or [anchor]
                # count only THIS cluster's changed lines: a neighbour's
                # changed lines may appear as context but are not ours
                n_changed = len(g)
                # F1/M1 (Opus v0.3 review): deletion-only means the
                # cluster's own RUN has no '+' entries — independent of
                # context. A whole-file deletion has none; an in-file
                # removal surrounded by unchanged lines also has none,
                # even though its window carries context that survives in
                # HEAD. Context must not flip the classification.
                # v0.3b (Kurt review): three-valued change_type —
                # 'whole-file-deleted' when the +++ side was /dev/null, so
                # the model knows the file is GONE (it cannot infer this
                # from a single cluster's before/after state).
                run_kinds = {seg[i][0] for i in g}
                deletion_only = "+" not in run_kinds
                if deletion_only and file_was_deleted:
                    change_type = "whole-file-deleted"
                elif deletion_only:
                    change_type = "deletion-only"
                else:
                    change_type = "code-change"
                hunks.append({
                    "file": fname, "line": anchor,
                    "line_start": min(span), "line_end": max(span),
                    "hunk_start": seg_hunk_start,
                    "header": f"@@ {fname} around line {anchor} "
                              f"({n_changed} changed lines) @@",
                    "lines": lines, "entries": window,
                    "n_changed": n_changed,
                    "change_type": change_type,
                })
    for h in hunks:
        h["size"] = len(h["lines"])
        h["too_large"] = h["size"] > MAX_HUNK_LINES
    return hunks


# ---------- AST unit extraction (plan Tasks 2/3) ----------

# entry tuples in sub-clusters keep package_hunks' exact shapes:
#   ('+', new_line, text, hunk_start)
#   ('-', old_line, text, hunk_start, tracked_head_line)


def _top_level_units(tree_src):
    """(name, start_line, end_line) for a parsed module's top-level
    def/class nodes (end_lineno is 3.8+). Deterministic source order.
    r16-m5 (round-2): ValueError joins SyntaxError — on Python 3.10/3.11
    `ast.parse` raises ValueError (not SyntaxError) for NUL bytes, which
    `git_show_or_none`'s 8 KB head-check misses on large files.
    r19-MAJOR-1 (round-5): RecursionError/MemoryError join too — a
    pathological deep expression (`a + b + …` × thousands) raises
    RecursionError out of `ast.parse`; uncaught, it crashes the whole
    run from enrichment or the cutter. A file we cannot parse safely
    yields None and the callers fall back to line windows."""
    try:
        tree = ast.parse(tree_src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    units = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            end = getattr(node, "end_lineno", None)
            if end is None:
                return None
            units.append((node.name, node.lineno, end))
    return units


def _qualified_matches(pre_units, post_units):
    """Pre-unit index -> matching post-unit index by qualified name
    (r5-M1/r2-M3: '-' lines map by old-file line into the PRE-image AST
    and join the sub-cluster of the same-named post-image unit)."""
    post_by_name = {name: i for i, (name, _s, _e) in enumerate(post_units)}
    return {i: post_by_name[name]
            for i, (name, _s, _e) in enumerate(pre_units)
            if name in post_by_name}


# ---------- AST context enrichment (plan Task 6, Arch 2) ----------
#
# Read-only enclosing-symbol context attached to unit states AFTER the
# pre-judge expansion (jev only). Text-only: no merged units, no question
# changes, no call graph (Arch 3 is UNPROVEN AND DEFERRED, r2-m5).
# Size is bounded at ATTACHMENT (r2-m3) so enrichment keeps budget
# headroom; a unit whose context still trips the soft cap has the
# context DROPPED at re-expansion step 0 (r12-M1) — never split.

ENRICHMENT_MAX_SYMBOLS = 40        # file top-level symbol table cap
ENRICHMENT_MAX_CONTEXT_LINES = 20  # enclosing-symbol context-window cap


def _signature_line(node, src_lines):
    """The source line that defines `node` (the `def`/`class` header)."""
    n = node.lineno
    if 1 <= n <= len(src_lines):
        return src_lines[n - 1].rstrip()
    return ""


def _file_symbol_table(src):
    """Ordered {name: signature line} for a module's top-level def/class
    symbols — the ENRICHMENT_MAX_SYMBOLS head in source order, or None
    when the file has no parseable top-level symbols (non-Python text,
    syntax errors, no symbols). Deterministic."""
    units = _top_level_units(src)
    if not units:
        return None
    src_lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    table: dict[str, str] = {}
    for name, s, _en in units[:ENRICHMENT_MAX_SYMBOLS]:
        node = next((cand for cand in tree.body
                     if getattr(cand, "name", None) == name
                     and getattr(cand, "lineno", None) == s), None)
        table[name] = (_signature_line(node, src_lines) if node is not None
                       else (src_lines[s - 1].rstrip()
                             if 1 <= s <= len(src_lines) else ""))
    return table or None


def _walk_with_parents(tree):
    """Yield (node, parent_chain) where parent_chain is the list of
    enclosing def/class names (outermost first). ast.walk loses parents,
    so this keeps an explicit chain."""
    stack: list[tuple[ast.AST, list[str]]] = [(tree, [])]
    while stack:
        node, chain = stack.pop()
        name = getattr(node, "name", None)
        here = chain + [name] if isinstance(name, str) else chain
        yield node, here
        for child in ast.iter_child_nodes(node):
            stack.append((child, here))


def _enclosing_chain(src, lineno):
    """The enclosing symbol chain at `lineno` — 'Class.method' style,
    outermost first, dotted. Deletion-only units map by OLD-file line
    into the PRE image (r2-m4). None when no def/class encloses the
    line (module-level change)."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    best: list[str] = []
    for node, chain in _walk_with_parents(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None or not (node.lineno <= lineno <= end):
            continue
        if len(chain) > len(best):
            best = chain
    return ".".join(best) or None


def _symbol_context_window(src, lineno):
    """Up to ENRICHMENT_MAX_CONTEXT_LINES of the innermost enclosing
    symbol's own source (header .. end, deterministic head-first clamp)
    — the part of the file that gives the changed lines their
    enclosing-symbol shape."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    src_lines = src.splitlines()
    best = None
    for node, _chain in _walk_with_parents(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None or not (node.lineno <= lineno <= end):
            continue
        # r20-M1 (round-6): pick the NARROWEST enclosing span (innermost
        # symbol), not the smallest start line — `(lineno, end) <= best`
        # kept `class Big(1-35)` over `def m(32-35)`, so a method change
        # got the class header as "context". Ties go to the deeper node
        # (larger start), which encloses less.
        span = end - node.lineno
        if best is None or (span, -node.lineno) < best:
            best = (span, -node.lineno, end)
    if best is None:
        return []
    s, en = best[1] * -1, best[2]
    lo = max(1, min(s, len(src_lines)))
    hi = min(len(src_lines), en)
    return [src_lines[i - 1].rstrip() for i in range(lo, hi + 1)] \
        [:ENRICHMENT_MAX_CONTEXT_LINES]


def build_ast_context(path, pre, post, unit):
    """The ast_context value for ONE unit, or None when the unit has no
    usable symbol context (non-Python text, no parseable images, no
    enclosing symbols). `pre` is preferred for deletion-only units
    (r2-m4: the removed code lives only in the old file); everything
    else maps by POST-image lines. WHOLE-FILE-DELETED units always get
    None (no post-image at all — the cluster is judged as-is)."""
    if unit.get("change_type") == "whole-file-deleted":
        return None
    if unit.get("change_type") == "deletion-only" and pre:
        src = pre
        first = next((e for e in unit.get("entries", []) if e[0] == "-"),
                     None)
        lineno = first[1] if first is not None else unit["line"]
    else:
        src = post
        lineno = unit["line"]
    if not src:
        return None
    symbols = _file_symbol_table(src)
    enclosing = _enclosing_chain(src, lineno)
    if symbols is None and enclosing is None:
        return None
    return {"symbols": symbols or {},
            "enclosing": enclosing,
            "context": _symbol_context_window(src, lineno)}


def attach_ast_context(units, images):
    """Bounded (r2-m3) attachment of `ast_context` to each unit — called
    by main() for jev only, after the pre-judge expansion and only when
    --no-enrichment is absent (r5-m3: the mechanism lives here, so
    `hunk_state` stays provider-agnostic and a laya state NEVER carries
    the key). `images(path, unit)` mirrors the cutter's injection
    contract (mode_file_images). Units without a usable symbol context
    (non-Python text, missing images, whole-file-deleted) simply do not
    get the key — it is ABSENT, never None-valued."""
    out: list = []
    for unit in units:
        pre, post = images(unit.get("file") or "", unit)
        ctx = build_ast_context(unit.get("file") or "", pre, post, unit)
        if ctx is not None:
            unit = dict(unit, ast_context=ctx)
        out.append(unit)
    return out


def _subcluster(parent, entries, change_type=None, hunk_start=None):
    """Assemble one sub-cluster record from `entries`, sharing the parent's
    identity (D8) and anchoring via the SHARED anchor chain."""
    anchor = _cluster_anchor(entries, 0, len(entries),
                             hunk_start if hunk_start is not None
                             else parent["hunk_start"])
    span = [e[4] if e[0] == "-" else e[1] for e in entries]
    span = [n for n in span if n is not None] or [anchor]
    lines = []
    for w in entries:
        k, n, t, _hs = w[0], w[1], w[2], w[3]
        if k == "+":
            lines.append(f"{n}: + {t}")
        elif k == "-":
            lines.append("    - " + t)
        else:
            lines.append(f"{n}:   {t}")
    return {
        "file": parent["file"],
        "line": anchor,
        "line_start": min(span), "line_end": max(span),
        "hunk_start": hunk_start if hunk_start is not None
        else parent["hunk_start"],
        "header": (f"@@ {parent['file']} around line {anchor} "
                   f"({len(_changed_entries(entries))} changed lines) @@"),
        "lines": lines, "entries": list(entries),
        # r19-m6 (round-5): count only CHANGED entries — the header the
        # model sees ("N changed lines") counted glued context too.
        "n_changed": len(_changed_entries(entries)),
        "change_type": change_type or parent.get("change_type",
                                                 "code-change"),
        "parent_cluster": parent,
    }


def _changed_entries(entries):
    return [e for e in entries if e[0] != " "]


def _window_line(e):
    """The line a window cutter sizes by. r18-M2 (round-4): a deletion
    run's entries all share e[4] (new_line never advances across '-'
    lines), which made `line - run_start + 1` stay at 1 — a 2,000-line
    deletion never cut. Size by e[1] (the line that ADVANCES for the
    entry's own kind: old-file for '-', new-file otherwise); one
    coordinate system per RUN, which is all the window cutter needs."""
    if e[0] == "-":
        return e[1]
    return e[4] if (len(e) > 4 and e[4] is not None) else e[1]


# r19-m7 (round-5): `_entry_sort_key` RETIRED — cutters iterate in the
# parent's diff order (r16-M3/r18-M1); the legacy per-image key had no
# callers left.


def ast_units(path, before_text, after_text, entries, change_type="code-change",
              parent_cluster=None):
    """Sub-cluster an OVERSIZE code-change cluster on Python unit
    boundaries (plan Task 2). stdlib `ast` only.

    Engagement is TOKEN-based only (r1-M4): the caller's serialized
    estimate must exceed SOFT_CAP_TOKENS — `ast_units` is only CALLED for
    oversize clusters; small clusters and whole-file deletions return
    None. `before_text` is parsed as the PRE-image AST ('-' entries map
    by e[1] into it, r5-M1); `after_text` as the POST-image ('+' by e[1]).

    Returns sub-clusters (boundaries on top-level def/class ends, own
    anchor + full question triple per D8, parent change_type inherited,
    union == original always) or None when the AST cannot help (parse
    error, non-Python, no units cover the span) — the caller then falls
    back to line windows."""
    if change_type == "whole-file-deleted":
        return None  # no post-image to parse (r5-M3); Task 4 skips these
    changed = _changed_entries(entries)
    if not changed:
        return None
    # TOKEN-based engagement was REMOVED (r15-M3, Opus Task-10 review):
    # band units (121+ lines, under cap by definition) and runtime-400
    # units are all <= SOFT_CAP_TOKENS, so an internal check here made
    # them fall through to arbitrary line windows, contradicting the
    # band contract (the caller's cutter order). The CALLERS decide when
    # the AST cutter engages (expand_oversize_units only calls it for
    # oversize units / split retries); a small top-level entry can never
    # reach this function on those paths.
    try:
        post_units = _top_level_units(after_text)
    except (ValueError, TypeError, RecursionError, MemoryError):
        post_units = None  # r19-MAJOR-1: pathological parse -> line windows
    pre_units = None
    if before_text:
        try:
            pre_units = _top_level_units(before_text)
        except (ValueError, TypeError, RecursionError, MemoryError):
            pre_units = None
    if not post_units:
        return None  # parse error / non-Python -> line-window fallback
    # r15-m8: single `parent` build, after the parse succeeds (the old
    # pre-parse build was dead — unconditionally rebuilt here).
    parent = parent_cluster if parent_cluster is not None else {
        "file": path, "hunk_start": next(
            (e[3] for e in changed if len(e) > 3), 1),
        "change_type": change_type}
    match = _qualified_matches(pre_units, post_units) if pre_units else {}

    # assignment: '+' -> enclosing post unit by e[1]; '-' -> matched post
    # unit via the PRE-image enclosing symbol by e[1]; unmatched '-' ->
    # its own PRE-boundary sub-cluster (r6-M2); context rides with the
    # nearest '+'/'-' assignment (window glue, never changes the union).
    by_post: dict[int, list] = {}
    own: list = []
    context: list = []
    for e in entries:
        if e[0] == " ":
            context.append(e)
            continue
        lineno = e[1]
        if e[0] == "+":
            unit = next((i for i, (_n, s, en) in enumerate(post_units)
                         if s <= lineno <= en), None)
            if unit is not None:
                by_post.setdefault(unit, []).append(e)
                continue
            own.append(e)  # outside every unit: glued below (union == orig)
        else:  # '-': pre-image symbol by e[1], joined by qualified name
            if pre_units:
                pre_i = next((i for i, (_n, s, en) in enumerate(pre_units)
                              if s <= lineno <= en), None)
                if pre_i is not None and pre_i in match:
                    by_post.setdefault(match[pre_i], []).append(e)
                    continue
            own.append(e)
    # '+' entries outside every unit (blank separators, module-level
    # stragglers) glue to the NEAREST unit by line — union == original
    # always (r6-M2); ties go to the earlier unit (deterministic).
    own_pluses = [e for e in own if e[0] == "+"]
    for e in own_pluses:
        lineno = e[1]
        nearest = min(
            range(len(post_units)),
            key=lambda i: (min(abs(post_units[i][1] - lineno),
                               abs(post_units[i][2] - lineno)), i))
        by_post.setdefault(nearest, []).append(e)
        own.remove(e)
    if not by_post and not own:
        return None
    subs = []
    for i in sorted(by_post):
        group = by_post[i]
        # glue this unit's flanking context onto its sub-cluster window
        _n, s, en = post_units[i]
        lo = min((e[1] for e in group), default=s)
        hi = max((e[1] for e in group), default=en)
        glue = [c for c in context if s - 4 <= c[1] <= en + 4
                and not (lo < c[1] < hi)]
        # r16-M3: keep the parent's DIFF order (no per-image re-sort) —
        # `sorted(group+glue, key=...)` scrambled before/after text.
        # r18-M1 (round-4): `group + glue` still broke diff order (glue
        # appended AFTER the changed lines, incl. leading `def` lines).
        # Rebuild by filtering the parent's `entries` in order against
        # the selected set — entries keep their diff sequence.
        selected = set(map(id, group + glue))
        in_order = [e for e in entries if id(e) in selected]
        subs.append(_subcluster(parent, in_order,
                                change_type=change_type,
                                hunk_start=parent["hunk_start"]))
    # unmatched pre-image symbols: own sub-clusters cut on PRE-image
    # boundaries, anchored via e[4], parent change_type kept (r6-M2);
    # r16-M3: keep diff order (no per-image re-sort).
    if own:
        if pre_units:
            bounds: dict[int, list] = {i: [] for i in range(len(pre_units))}
            loose = []
            for e in own:
                pre_i = next((i for i, (_n, s, en) in enumerate(pre_units)
                              if s <= e[1] <= en), None)
                if pre_i is None:
                    loose.append(e)
                else:
                    bounds[pre_i].append(e)
            for pre_i in sorted(k for k in bounds if bounds[k]):
                _n, s, en = pre_units[pre_i]
                grp = bounds[pre_i]
                anchor_fb = next((e[4] for e in grp
                                  if len(e) > 4 and e[4] is not None),
                                 grp[0][1])
                # cut on PRE-image boundaries; span/anchor via e[4]
                subs.append(_subcluster(
                    parent, grp, change_type=change_type,
                    hunk_start=parent["hunk_start"]))
                subs[-1]["line"] = anchor_fb
            own = loose
        # r15-M5 (Opus Task-10 review): the old per-entry loop made one
        # Jev call per deleted line — a 60-deletion refactor became 60
        # single-line calls that could fill the --max-hunks ceiling.
        # Contiguous loose entries (adjacent in the sort order, same
        # coordinate system) now group into one sub-cluster per run.
        runs: list[list] = []
        for e in own:
            if runs:
                prev = runs[-1][-1]
                gap = (e[1] - prev[1] if e[0] == "-" and prev[0] == "-"
                       else None)
                if gap is not None and 0 < gap <= 2:
                    runs[-1].append(e)
                    continue
            runs.append([e])
        for run in runs:
            subs.append(_subcluster(parent, run, change_type=change_type,
                                    hunk_start=parent["hunk_start"]))
            fb = next((e[4] for e in run
                       if len(e) > 4 and e[4] is not None), run[0][1])
            subs[-1]["line"] = fb
    if not subs:
        return None
    # r16-M1 (Opus Task-10 round-2 review): a single sub-cluster whose
    # changed entries EQUAL the input's is a no-op cut — the common case
    # is every change inside ONE top-level def/class. Returning it let
    # _split_once treat it as progress: expand_oversize_units looped to
    # the depth cap (oversize -> false leaf; band -> judged whole) and a
    # runtime 400 burned 6 split attempts. `None` makes the caller fall
    # through to line windows / halving, as with any other no-gain cut.
    # r17-m2 (round-3): compare CHANGED entries — context glue is
    # deliberately partial (±4-line windows), so comparing ALL entries
    # made the no-op check miss the common case. Key = (kind, new-line,
    # text) so a glued-but-identical entry set compares equal.
    def _changed_key(e):
        return (e[0], e[1], e[2])
    if len(subs) == 1 and \
            {_changed_key(e) for e in _changed_entries(subs[0]["entries"])} \
            == {_changed_key(e) for e in changed}:
        return None
    return subs


# ---------- tree-sitter units + line-window fallback (plan Task 3) ----------

TS_LANGUAGE_BY_EXT = {"ts": "typescript", "tsx": "tsx", "js": "javascript",
                      "jsx": "javascript", "mjs": "javascript",
                      "cjs": "javascript"}


def ts_units(path, before_text, after_text, entries,
             change_type="code-change", parent_cluster=None, loader=None):
    """Same contract as ast_units for TS/JS via tree-sitter. The import is
    LAZY through the injectable `loader` seam (r1-m5/m6): NO static
    `import tree_sitter` anywhere and NO `# type: ignore` — CI has no
    tree-sitter, and a missing module returns None (fallback), never
    raises."""
    if change_type == "whole-file-deleted":
        return None
    ext = os.path.splitext(path or "")[1].lower().lstrip(".")
    lang = TS_LANGUAGE_BY_EXT.get(ext)
    if lang is None:
        return None
    changed = _changed_entries(entries)
    if not changed:
        return None
    try:
        tree_sitter = (loader or __import__)("tree_sitter")
        grammar_mod = (loader or __import__)(
            "tree_sitter_typescript" if lang in ("typescript", "tsx")
            else "tree_sitter_javascript")
    except Exception:
        return None  # missing/failed import -> deterministic fallback
    try:
        get_lang = (grammar_mod.language_typescript if lang == "typescript"
                    else grammar_mod.language_tsx if lang == "tsx"
                    else getattr(grammar_mod, "language", None))
        if get_lang is None:
            return None
        parser = tree_sitter.Parser(tree_sitter.Language(get_lang()))
        tree = parser.parse(after_text.encode("utf-8", "replace"))
        root = tree.root_node
        units = []
        for node in root.children:
            # r19-MAJOR-2 (round-5): unwrap `export_statement` to its
            # `declaration` (export function/class/const are the
            # MAJORITY of real TS/JS top-level symbols; without this the
            # cutter saw none of them) and read const names from the
            # nested variable_declarator. Fall back to the node's own
            # `name` field for plain function/class.
            target = node
            if node.type == "export_statement":
                decl = node.child_by_field_name("declaration") \
                    if hasattr(node, "child_by_field_name") else None
                if decl is None:
                    continue
                target = decl
            name_node = (target.child_by_field_name("name")
                         if hasattr(target, "child_by_field_name")
                         else None)
            if name_node is None and target.type in (
                    "lexical_declaration", "variable_declaration"):
                # const f = ... / var g = ...: name lives on the
                # variable_declarator's `name` field
                for child in target.children:
                    if child.type == "variable_declarator":
                        name_node = (child.child_by_field_name("name")
                                     if hasattr(child,
                                                "child_by_field_name")
                                     else None)
                        break
            if name_node is None:
                continue
            units.append((name_node.text.decode("utf-8", "replace"),
                          node.start_point[0] + 1, node.end_point[0] + 1))
    except Exception:
        return None
    if not units:
        return None
    parent = parent_cluster if parent_cluster is not None else {
        "file": path, "hunk_start": next(
            (e[3] for e in changed if len(e) > 3), 1),
        "change_type": change_type}
    by_post: dict[int, list] = {}
    rest: list = []
    # r15-m6 (documented, not "fixed"): '-' entries map by their
    # OLD-file line into POST-image unit ranges. A true PRE-image parse
    # (like ast_units' r5-M1 handling) would need the pre-image units
    # here too; ts_units is the single-image band path (the band's
    # before/after images differ only by the changed lines, and the
    # band is < 84k chars), so the drift is bounded by the deletion
    # offset above each unit — misassignment can only move a deletion
    # to a NEIGHBORING unit, never out of the file, and the union of
    # entries is preserved either way. ast_units keeps the strict
    # pre/post pairing (r5-M1) for the Python oversize path, where the
    # images are parsed separately.
    for e in entries:
        if e[0] == " ":
            rest.append(e)
            continue
        unit = next((i for i, (_n, s, en) in enumerate(units)
                     if s <= e[1] <= en), None)
        if unit is not None:
            by_post.setdefault(unit, []).append(e)
        else:
            rest.append(e)
    if not by_post:
        return None
    subs = []
    for i in sorted(by_post):
        # r16-M3: keep diff order (no per-image re-sort).
        subs.append(_subcluster(parent, by_post[i],
                                change_type=change_type,
                                hunk_start=parent["hunk_start"]))
    if len(subs) == 1:
        return None  # no boundary gain -> let the caller fall through
    if rest:
        # r16-M2 (Opus Task-10 round-2 review): `rest` is all-context —
        # sending it as its own sub-cluster means judging UNCHANGED code
        # under HUNK_QUESTIONS (false-positive risk + a wasted
        # --max-hunks slot). Glue it to the FIRST unit sub-cluster
        # instead; union == original is preserved.
        # r18-M1 (round-4): rebuild in the parent's DIFF order (filter
        # `entries` against the selected set), not `entries + rest`.
        selected = set(map(id, subs[0]["entries"] + rest))
        in_order = [e for e in entries if id(e) in selected]
        subs[0] = _subcluster(
            parent, in_order,
            change_type=change_type, hunk_start=parent["hunk_start"])
    return subs


def line_window_subclusters(path, entries, change_type="code-change",
                            parent_cluster=None,
                            window_lines=FALLBACK_WINDOW_LINES):
    """The always-works fallback (plan Task 3): cut the oversize cluster's
    entries into windows of at most `window_lines` lines each, at blank
    lines where possible, never mid-line. `window_lines` sizes the
    windows only — it is NEVER an engagement or skip test (r1-M4:
    engagement is token-based; the caller only invokes this for oversize
    clusters). Union == original, no overlap, deterministic."""
    changed = _changed_entries(entries)
    if not changed:
        return None
    parent = parent_cluster if parent_cluster is not None else {
        "file": path, "hunk_start": next(
            (e[3] for e in changed if len(e) > 3), 1),
        "change_type": change_type}
    # r16-M3: iterate in the parent's DIFF order (no re-sort); window
    # SIZING still uses _window_line (one coordinate system, r15-m5).
    ordered = list(entries)
    groups: list = []
    run: list = []
    run_start = None
    for e in ordered:
        line = _window_line(e)  # r15-m5: ONE sizing coordinate system
        if run_start is None:
            run_start = line
        if run and line - run_start + 1 > window_lines:
            # window would overflow: cut the PREVIOUS run at its last
            # blank line when one exists (blank-line preference), else
            # hard-cut at the overflow point; never mid-line.
            cut = len(run)
            for k in range(len(run) - 1, 0, -1):
                rk = _window_line(run[k])  # r15-m5
                if rk - run_start + 1 > window_lines:
                    break
                if not str(run[k][2]).strip():
                    cut = k + 1
                    break
            else:
                for k in range(len(run) - 1, 0, -1):
                    rk = _window_line(run[k])  # r15-m5
                    if rk - run_start + 1 <= window_lines:
                        cut = k + 1
                        break
            groups.append(run[:cut])
            run = run[cut:]
            if run:
                # an identical-entry overflow can empty the run (a window
                # cannot shrink below one line) — reset to the NEXT entry
                # and let the current `e` seed the new run instead.
                run_start = _window_line(run[0])  # r15-m5
            else:
                run_start = None
        run.append(e)
    if run:
        groups.append(run)
    # r16-M2 (Opus Task-10 round-2 review): a group with NO changed
    # entries is pure context (leading/trailing context past the last
    # window cut) — judging it scores UNCHANGED code. Merge it into the
    # NEIGHBORING group so no entry is lost (union == original holds;
    # the union assertion in the tests covers this).
    kept_groups: list[list] = []
    for g in groups:
        if _changed_entries(g) or not kept_groups:
            kept_groups.append(g)
        else:
            kept_groups[-1].extend(g)
    groups = kept_groups
    if len(groups) <= 1:
        return None  # a single window is no split at all
    subs = []
    for g in groups:
        if g:
            subs.append(_subcluster(parent, g, change_type=change_type,
                                    hunk_start=parent["hunk_start"]))
    return subs or None


# ---------- recursive oversize expansion (plan Task 4, r7-M2) ----------

MAX_EXPANSION_DEPTH = 6  # depth cap: bounded termination (brief hard constraint)


def _unit_oversize(unit):
    """The oversize test, defined EXACTLY once (r1-M4): the unit's own
    serialized state estimate exceeds SOFT_CAP_TOKENS."""
    return estimate_call_size(hunk_state(unit), HUNK_QUESTIONS) \
        > SOFT_CAP_TOKENS


def _unit_band(unit):
    """The BAND engagement test (option 2, Kurt ruling 2026-10-02): the
    unit's span exceeds BAND_ENGAGE_LINES while its estimate stays under
    the token cap. Band units route through the SAME cutter order as
    oversize ones (top-level AST -> tree-sitter -> line windows ->
    halving) but can never become unsplittable>cap leaves — under-cap
    content is legal to send, so an un-splittable band unit is judged
    WHOLE (the caller's band path never leaf-marks). Span is the
    unit's own line_start/line_end when present, else anchor-only."""
    if _unit_oversize(unit):
        return False  # oversize test is primary; band is additive
    lo = unit.get("line_start", unit.get("line", 1))
    hi = unit.get("line_end", lo)
    return hi - lo + 1 > BAND_ENGAGE_LINES


def stamp_wire_format(units):
    """D7 (plan Task 7): the run's wire_format stamp — `ast-units-v1` when
    ANY judgeable unit CAME FROM AST (carries its parent cluster; the key
    is absent on whole parents and only ever set by the Tasks 2/3
    cutters), else `hunk_state-v1` (the pre-AST shape). Deterministic on
    the post-expansion unit list; an empty run stamps the v1 baseline."""
    if any(u.get("parent_cluster") is not None for u in units):
        return "ast-units-v1"
    return "hunk_state-v1"


def _split_once(unit, images):
    """ONE expansion attempt on an oversize unit, in the plan's fixed
    order: top-level AST -> nested AST (deeper lines via line windows of
    the AST's own boundaries is the same cutter family) -> line windows
    -> halving. Returns (units, None) or (None, leaf) when the unit is a
    single changed line that cannot be split further (the leaf case the
    caller sets aside as unjudged)."""
    path = unit["file"] or ""
    entries = unit.get("entries") or []
    change_type = unit.get("change_type", "code-change")
    parent = unit.get("parent_cluster") or unit
    pre, post = images(path, parent)
    # 1. top-level AST (stdlib) — python files with a parseable post-image
    subs = ast_units(path, pre, post, entries, change_type=change_type,
                     parent_cluster=parent)
    if subs:
        return subs, None
    # 2. tree-sitter units (lazy; returns None without the package)
    subs = ts_units(path, pre, post, entries, change_type=change_type,
                    parent_cluster=parent)
    if subs:
        return subs, None
    # 3. line windows — the always-works fallback
    subs = line_window_subclusters(path, entries, change_type=change_type,
                                   parent_cluster=parent)
    if subs:
        return subs, None
    subs = None
    # 4. halving — cut the CHANGED entries into two halves by position.
    # Context (' ') entries ride with their run (union == original): a
    # 2-entry unit like [context, changed] must still halve (a runtime
    # 400 retry has no other cutter left). Halving requires >= 2 entries
    # total, not >= 2 changed entries — a single changed line with its
    # context CAN split at runtime (the plan's ±1-line leaf windows).
    # mid_line = the MEDIAN changed line (r15-M2: the first changed line
    # put every entry in `right` for units without leading context,
    # leaving `left` empty and the unit a false leaf); entries before it
    # (context or earlier changes) go left, the rest right. The median
    # changed entry itself goes RIGHT, so both halves are non-empty for
    # any unit with >= 2 changed entries.
    changed = _changed_entries(entries)
    if len(entries) > 1 and changed:
        # r18-M2 (round-4): split by CHANGED-ENTRY POSITION (index in the
        # diff-ordered changed list), not by line key — a deletion run's
        # keys are all identical (e[1] advances but e[4] doesn't, and
        # mixed runs mix coordinates), so a median KEY put every
        # deletion in `right` and left a context-only `left`.
        # Every entry (changed or context) goes by its INDEX in the
        # diff-ordered `entries` list vs the median changed entry's
        # index — leading context goes left, trailing goes right.
        med_i = len(changed) // 2
        med_entry = changed[med_i]
        med_entries_idx = next(i for i, e in enumerate(entries)
                               if e is med_entry or e == med_entry)
        # r20-M2 (round-6): a half with NO changed entries is context
        # glue, not a judgment unit — the old cut put pure context in
        # `left` and judged it under HUNK_QUESTIONS. When both halves
        # carry changed entries, emit both; when only one does, emit
        # ONLY the changed half (the context half's entries are dropped
        # from judgment, not from the union bookkeeping — a runtime
        # split exists to shrink the payload, and context-only halves
        # are exactly what should not be sent). A len(changed)==1 unit
        # still splits at runtime (the 400 is about tokens, not the
        # changed-line count): its changed half is the single line,
        # which is the plan's ±1-line leaf window.
        left = entries[:med_entries_idx]
        right = entries[med_entries_idx:]
        left_ch = _changed_entries(left)
        right_ch = _changed_entries(right)
        if left_ch and right_ch and left and right:
            return ([_subcluster(parent, left, change_type=change_type,
                                 hunk_start=parent["hunk_start"]),
                     _subcluster(parent, right,
                                 change_type=change_type,
                                 hunk_start=parent["hunk_start"])],
                    None)
        if (left_ch or right_ch) and left and right:
            kept_entries = left if left_ch else right
            return ([_subcluster(parent, kept_entries,
                                 change_type=change_type,
                                 hunk_start=parent["hunk_start"])],
                    None)
    # unsplittable: a single changed line still over cap (or no cutter
    # helped and halving has nothing to cut) — the leaf case
    return None, unit


def expand_oversize_units(units, images, depth=0):
    """Recursively expand oversize units until every unit fits (r7-M2).

    Fixed order per unit: STEP 0 (POST-ENRICHMENT re-expansion only,
    r12-n1/r13-n1 — the initial Task 4 pass holds no `ast_context`) —
    a unit over cap whose state carries `ast_context` is over cap
    BECAUSE of its context (every unit leaving step (1) is <=cap
    unenriched and attachment clamps the context at 40/20), so the
    context is DROPPED ENTIRELY and the unit returns to its <=cap
    unenriched state (r12-M1): NO split is attempted, the images (and
    thus any splitter) are never consulted, and enrichment can never
    cause a split on the jev path. NO PARTIAL TRIM is built (a partial
    trim that permits splitting while keeping some context would be a
    NEW design decision requiring Kurt's ruling). Then, for a unit
    still over cap: top-level AST -> nested AST -> line windows ->
    halving. A single changed line whose own estimate still exceeds
    SOFT_CAP_TOKENS is NEVER sent and never silently dropped: it is
    set aside as a leaf record {"hunk": unit, "parse_error": True,
    "raw": None, "reason": "unsplittable>cap"} (r11-m1) that main()
    appends to findings only AFTER judge() returns non-None.
    Depth-capped (bounded termination); at the cap a still-oversize
    unit becomes a leaf too.

    Returns (units, leaves) — `units` are judgeable, `leaves` unjudged.
    `depth` is internal; the initial (pre-enrichment) expansion has no
    step 0 — ast_context only exists post-enrichment (r12-n1/r13-n1),
    where Task 6's re-expansion drops it as its defensive clamp.
    """
    out: list = []
    leaves: list = []
    for unit in units:
        if _unit_oversize(unit) and "ast_context" in unit:
            # step 0 (r12-M1): the context IS the over-cap cause —
            # drop it entirely; the result is the <=cap step-(1)
            # state by construction, so never re-test and never
            # split here.
            unit = {k: v for k, v in unit.items()
                    if k != "ast_context"}
        if not _unit_oversize(unit) and not _unit_band(unit):
            out.append(unit)
            continue
        band = not _unit_oversize(unit)
        if depth >= MAX_EXPANSION_DEPTH:
            if band:
                out.append(unit)  # band units are never over-cap leaves
                continue
            leaves.append({"hunk": unit, "parse_error": True, "raw": None,
                           "reason": "unsplittable>cap"})
            continue
        subs, leaf = _split_once(unit, images)
        if leaf is not None:
            if band:
                # option 2: a band unit the cutters cannot split is under
                # cap and stays judgeable — judged WHOLE, never a leaf
                # (unlike an oversize unit, whose content is over cap).
                out.append(unit)
                continue
            leaves.append({"hunk": leaf, "parse_error": True, "raw": None,
                           "reason": "unsplittable>cap"})
            continue
        # every sub-unit inherits the parent's oversize test recursively
        sub_units, sub_leaves = expand_oversize_units(subs, images, depth + 1)
        out.extend(sub_units)
        leaves.extend(sub_leaves)
    return out, leaves


def reexpand_after_enrichment(units, images):
    """Task 6 step (3) (r11-M1/r12-M1): the POST-ENRICHMENT re-estimate
    + re-expansion pass. Runs the SAME machinery as the Task 4 pass,
    whose per-unit order terminates at step 0: DROP `ast_context` — an
    over-cap unit's context is the over-cap cause, so the context is
    dropped and NO split is ever attempted because of enrichment. The
    context-drop path DE-AliasS the unit (a fresh dict without the
    key), so the pass-1 leaf contract is preserved by construction:
    a unit that was a leaf at pass 1 never reaches this pass enriched
    (leaves are set aside in step (4) BEFORE attachment and are not in
    `units`), and a unit dropped here re-enters the normal oversize
    test with its step-(1) state, so the leaf/split outcomes for it are
    exactly the unenriched run's."""
    return expand_oversize_units(units, images)


def _runtime_split_unit_factory(repo, mode, head):
    """Task 5 (r6-m3): build the splitter judge() calls back into when a
    unit comes back 400 max_tokens_exceeded at runtime. main() owns the
    per-mode file images (mode_file_images) and the Task 2/3 extractors;
    judge() has none — hence injection. ONE _split_once attempt per
    call; deeper recursion happens through judge()'s own loop with its
    MAX_EXPANSION_DEPTH cap."""
    def split_unit(unit):
        subs, _leaf = _split_once(unit, lambda path, img_unit: (
            mode_file_images(repo, mode, head, path,
                             old_file=img_unit.get("old_file"))))
        return subs
    return split_unit


# ---------- per-mode file images (plan Task 4 helpers; not wired yet) ----------

def git_show_or_none(repo, rev, path):
    """`git show <rev>:<path>` that DEGRADES instead of dying (r1-M2): a
    missing image (added file, rename, binary, gitlink) is a normal case,
    so this returns None — never the sys.exit run_git would raise at
    :346. `rev == "worktree"` reads the working tree (the --uncommitted
    post-image, D4's documented diff-only exception)."""
    if rev == "worktree":
        full = os.path.join(repo, path)
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            return None
    else:
        try:
            if rev == ":":
                # staged-image rev (mode_file_images): ':<path>'
                argv = ["git", "-C", repo, "show", f":{path}"]
            else:
                argv = ["git", "-C", repo, "show", f"{rev}:{path}"]
            r = subprocess.run(
                argv,
                capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode != 0:
            return None
        data = r.stdout
    if b"\x00" in data[:8192]:
        return None  # binary / gitlink — no text image to parse
    return data.decode("utf-8", "replace")


_IMAGE_CACHE: dict = {}
_MERGE_BASE_CACHE: dict = {}  # r16-m6: (repo, base_ref, head) -> sha (immutable)


def clear_runtime_caches():
    """r19-m5 (round-5): drop per-run caches. Called at the top of
    main() — `_IMAGE_CACHE` keys are mode-aware but NOT repo-aware, so
    in-process reuse (tests, sweep scripts, a second main()) could serve
    another repo's image. Library callers doing multiple runs should
    call this between runs too."""
    _IMAGE_CACHE.clear()
    _MERGE_BASE_CACHE.clear()


def mode_file_images(repo, mode, head, path, old_file=None,
                     fetch=None, merge_base=None):
    """Fetch (pre_image, post_image) for a cluster's path under the run's
    mode (r2-M2/r2-m6). Modes:
      range:<spec> / pr:<n>  post = git show <head>:<path>
                             pre  = git show <merge_base>:<path>
                             (--pr base = origin/main; --range base =
                             the LEFT side of the triple-dot spec)
      staged                 post = git show :<path>
                             pre  = git show HEAD:<path>
      uncommitted            post = worktree read
                             pre  = git show :<path>
    `old_file` (package_hunks' rename-from field) is used for the
    pre-image when the path itself has none (renames). Missing images are
    None — the caller degrades, never dies. Cache key is the MODE-AWARE
    (mode, rev, path) triple (r2-m2): an --uncommitted post-image can
    never serve a --staged request in one process."""
    def _fetch(repo_, rev, path_):
        if fetch is not None:
            return fetch(repo_, rev, path_)
        return git_show_or_none(repo_, rev, path_)

    def _merge_base(repo_, base_ref, head_):
        # r15-m9 + r16-m6 (round-2): the cache lives at MODULE level so
        # it survives across mode_file_images() calls within the run —
        # it is keyed by (repo, base_ref, head), and a git merge-base
        # answer for a given key is immutable for the process lifetime,
        # so cross-RUN reuse is also correct (unlike image contents,
        # which are keyed mode-aware precisely because they are NOT
        # immutable across modes).
        key = (repo_, base_ref, head_)
        if key in _MERGE_BASE_CACHE:
            return _MERGE_BASE_CACHE[key]
        if merge_base is not None:
            mb = merge_base(repo_, base_ref, head_)
        else:
            try:
                r = subprocess.run(
                    ["git", "-C", repo_, "merge-base", base_ref, head_],
                    capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                mb = None
            else:
                out = r.stdout.strip()
                mb = out.splitlines()[0] if out else None  # FIRST (r2-m6)
        _MERGE_BASE_CACHE[key] = mb
        return mb

    def cached(rev):
        key = (mode, rev, path)
        if key not in _IMAGE_CACHE:
            _IMAGE_CACHE[key] = _fetch(repo, rev, path)
        return _IMAGE_CACHE[key]

    if mode.startswith("range:"):
        spec = mode[len("range:"):]
        if "..." in spec:
            left = spec.split("...", 1)[0] or "HEAD"
        elif ".." in spec:
            left = spec.split("..", 1)[0] or "HEAD"
        else:
            left = spec or "HEAD"
        base = _merge_base(repo, left, head)
        post = cached(head)
        pre = cached(base) if base else None
        if pre is None and old_file and base:
            pre = _fetch(repo, base, old_file)
        return pre, post
    if mode.startswith("pr:"):
        base = _merge_base(repo, "origin/main", head)
        post = cached(head)
        pre = cached(base) if base else None
        if pre is None and old_file and base:
            pre = _fetch(repo, base, old_file)
        return pre, post
    if mode == "staged":
        post = cached(":")
        pre = cached("HEAD")
        if pre is None and old_file:
            key = (mode, "HEAD", old_file)
            if key not in _IMAGE_CACHE:
                _IMAGE_CACHE[key] = _fetch(repo, "HEAD", old_file)
            pre = _IMAGE_CACHE[key]
        return pre, post
    if mode == "uncommitted":
        post = cached("worktree")
        pre = cached(":")
        if pre is None and old_file:
            pre = _fetch(repo, ":", old_file)
        return pre, post
    return None, None


def _span(h):
    """Cluster's window span (new-file lines) for corpus-side matching."""
    return {"line_start": h.get("line_start", h["line"]),
            "line_end": h.get("line_end", h["line"])}


def triage(hunks, provider="jev"):
    """Deterministic skip: lockfiles, generated dirs, docs-only runs.

    Step 0′ (hunk-size investigation, 2026-10-01): size-skipped records
    carry `change_type` so the verdict downgrade in main() can treat
    CODE-change size-skips as unjudged coverage while deletion/whole-file
    size-skips stay deliberate triage (Kurt-decision 3).

    r5-M4 (AST-units plan Task 4): the size gate is MECHANICAL via the
    `provider` param. Under jev (the default) no cluster is ever
    size-skipped — oversize clusters stay in `kept` and main() routes
    them through the Task 2/3 cutter. LAYA KEEPS TODAY'S EXACT BEHAVIOR:
    the `hunk>` skip append stays live for laya, whose whole-cluster
    transport has no splitter. `whole-file-deleted>cap` (r5-M3) is the
    one jev-side size skip: a whole-file deletion has no post-image to
    parse and no lines to window, so the skip is deliberate triage —
    and `size_skipped_code()` matches only the `hunk>` prefix, so it
    never counts toward n_size_skipped_code (r6-m4).
    """
    kept, skipped = [], []
    for h in hunks:
        f = h["file"] or ""
        if SKIP_PATTERNS.search(f) or DOC_EXT.search(f):
            skipped.append({"file": f, "reason": "docs/generated/lockfile",
                            **_span(h)})
        elif DATA_EXT.search(f):
            skipped.append({"file": f, "reason": "data/snapshot", **_span(h)})
        elif provider == "laya" and h["too_large"]:
            skipped.append({"file": f, "reason": f"hunk>{MAX_HUNK_LINES} lines",
                            "change_type": h.get("change_type", "code-change"),
                            **_span(h)})
        elif (provider == "jev" and h["too_large"]
                and h.get("change_type") == "whole-file-deleted"):
            # r5-M3: over-cap whole-file deletion — deliberate triage,
            # never a size-skip counter entry (no 'hunk>' prefix).
            skipped.append({"file": f, "reason": "whole-file-deleted>cap",
                            "change_type": "whole-file-deleted",
                            **_span(h)})
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
        "instructions": ("Should a human reviewer look at this change set "
                         "beyond this automated report?")},
}

# F1 (field evals 2026-09-28): deletion-only clusters have no surviving
# code to be "buggy", so the generic severity question ("most serious
# problem in this hunk") systematically over-scores pure removals — the
# #45 field run put six harmless file deletions at BLOCKER-level severity.
# The questions ask what a deletion can actually be guilty of. v0.3b
# (Kurt review): the model judges ONE cluster and cannot see the rest of
# the tree, so cross-file questions ("does remaining code still reference
# it?") are answered deterministically — references_remaining is computed
# in hunk_state() (grep of the post-state) and fed in as fact, not asked.
# The rubric below scores only what a single-cluster view can know: the
# internal consistency of the removal.
DELETION_QUESTIONS = {
    "severity": {
        "type": "score",
        "instructions": ("This hunk only REMOVES code. Judge the removal "
                         "as it stands within this hunk; whether other "
                         "code still uses what was removed is measured "
                         "separately and not your concern here. How "
                         "risky is the removal on its face?"),
        "criteria": [
            "Safe removal: dead code, unused asset, or superseded logic",
            ("Minor: removal is fine but leaves small debris (stale doc "
             "reference, unused import elsewhere)"),
            ("Major: the removed code carried behavior nothing in this hunk "
             "replaces — a caller, config, or behavior disappears"),
            ("Blocker: the removal takes down builds, tests, or security "
             "handling on its face (e.g. deletes the only test for a kept "
             "feature)"),
        ]},
    "is_real_issue": {
        "type": "noul",
        "instructions": ("Does this removal itself warrant a reviewer "
                         "comment (independent of whether other files "
                         "reference the deleted code)?")},
    "category": {
        "type": "choice",
        "instructions": "What kind of issue is it, if any?",
        "criteria": {
            "bug-risk": "The removed code carried behavior nothing in this hunk replaces",
            "security": "The removed code was load-bearing for security or secret handling",
            "style": "Debris the removal leaves behind (stale references, dead imports)",
            "performance": "The removal hurts performance (e.g. a needed cache was deleted)",
            "test-gap": "The removal took away coverage the system still needs",
            "other": "Any other removal-related issue worth noting",
        }},
}


# ---------- judge + compose ----------

def references_remaining(h, after_texts):
    """Deterministic corroboration signal for deletion clusters (v0.3b,
    Kurt review; semantics corrected per Opus v03b r1 M1): do the
    cluster's SURVIVING lines (its ±4-line context) still mention a name
    the removal declared — the def/class/function/const names and import
    targets taken out by the deleted lines?

    Scope is honest and deliberately narrow: the cluster window only.
    'False' means nothing IN VIEW references the removal — it is NOT a
    tree-wide claim. For whole-file deletions the window's post-state is
    empty by construction, so the answer is vacuously False; dangling
    imports elsewhere in the tree are NOT measured here (that would need
    a tree grep the diff-only tool does not do).
    """
    ct = h.get("change_type", "code-change")
    if ct not in ("deletion-only", "whole-file-deleted"):
        return None
    corpus = "\n".join(after_texts)
    if not corpus:
        return False  # vacuous: nothing survives in view (whole-file deletions)
    removed_names = set()
    for w in h["entries"]:
        if w[0] != "-":
            continue
        text = w[2]
        # DECLARED names only (v0.3b M1 fix): def/class (Python),
        # function/const/let/var/class (JS/TS). Matching every ≥3-char
        # token matched keywords like def/return/self and made the signal
        # fire on almost anything. Names shorter than 3 chars are skipped
        # (Opus r2 m2: removing `let i = 0` must not open the gate via
        # `\bi\b` matching every surviving loop).
        for m in re.finditer(
                r"\b(?:def|class|function|const|let|var)\s+([A-Za-z_]\w*)",
                text):
            if len(m.group(1)) >= 3:
                removed_names.add(m.group(1))
        # import targets: 'from mod import a, b' / 'import mod'. Skip
        # non-identifier fragments (Opus r2 m3: `import React from 'react'`
        # and multiline `from x import (` produce junk names).
        imp = re.match(r"\s*(?:from\s+([\w.]+)\s+import\s+(.+)|import\s+([\w.,\s]+))",
                     text)
        if imp:
            for part in (imp.group(2) or imp.group(3) or "").split(","):
                nm = part.strip().split(" as ")[0].strip()
                if nm and re.fullmatch(r"[A-Za-z_]\w*", nm):
                    removed_names.add(nm.split(".")[-1])
            mod = (imp.group(1) or imp.group(3) or "").strip()
            # v03b r3 M1 (Opus): relative imports (`from .utils import x`,
            # `from . import x`) yield empty first segments; an empty name
            # makes `\b\b` match ANY word boundary — reopening the #45 FP
            # path. Skip empty names entirely.
            mod = mod.lstrip(".")
            if mod and re.fullmatch(r"[\w.]+", mod):
                removed_names.add(mod.split(".")[0])
    if not removed_names:
        return False
    # Whole-word match only (v0.3b M1 fix): 'def' must not match 'default'.
    return any(re.search(rf"\b{re.escape(n)}\b", corpus)
               for n in removed_names)


def hunk_state(h):
    """Structured before/after state, read from `entries` only (never the
    rendered lines, which can corrupt text containing ': + ').

    change_type (F1, field evals 2026-09-28) is computed at packaging time
    from the cluster's own run: 'deletion-only' when the run has no '+'
    entries — the cluster only removes code, so the model gets the
    deletion-adapted question set (DELETION_QUESTIONS: removal-risk
    scoring) instead of the generic code-bug questions. Context lines ride
    in code_before/after regardless; they describe the surviving file, not
    the change. On the #45 field run, six deletion-only clusters scored
    severity 2.73-2.82 under the generic questions and the one crossing
    the is_real gate flipped the verdict to "Changes requested" on a clean
    cleanup PR.
    """
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
    ct = h.get("change_type", "code-change")
    state = {
        "file": h["file"],
        "location": f"around line {h['line']}",
        "change_type": ct,
        "code_before_change": before,
        "code_after_change": after,
    }
    if ct in ("deletion-only", "whole-file-deleted"):
        # v0.3b: cross-file-ness is MEASURED, not asked (see
        # references_remaining). True ⇒ the surviving context still
        # mentions removed identifiers — that is the corroboration
        # compose() requires before a lone deletion finding flips the
        # verdict; False ⇒ nothing in view references the removal.
        state["references_remaining"] = references_remaining(h, after)
    # Task 6 (r5-m3): the ast_context key is ATTACHED by main() on the
    # jev path only (attach_ast_context); hunk_state is provider-
    # agnostic and reads the key WHEN PRESENT. A laya state (or any
    # unit whose enrichment was dropped at re-expansion step 0,
    # r12-M1) simply never carries it.
    if "ast_context" in h:
        state["ast_context"] = h["ast_context"]
    return state


def _judge_unit(h, ask, split_unit, depth):
    """Judge ONE unit with the Task 5 runtime-split loop (r6-m3).

    Returns a flat 7-tuple:
        (records, added_units, latencies, tokens_sum, tokens_n,
         transport_fail, shape_fail)

    `records` are the unit's finding records (judged or explicit
    unjudged budget leaves); `added_units` is the NET unit growth from
    runtime splits (leaves - 1 per split parent, r7-m1 — the parent is
    REPLACED, not kept); `latencies`/`tokens_sum`/`tokens_n` aggregate
    successful call latency and usage.input_tokens; `transport_fail` is
    the repr of an ordinary transport error (None when none — an
    _OverBudget NEVER reaches here, it is converted to an explicit
    unjudged leaf); `shape_fail` is the bad-response-shape error repr
    (None when the answers parsed).

    Flow: the SEND gate first (defense-in-depth, r1-m2 — an over-
    HARD-cap payload is never sent); then the ask; an _OverBudget
    raised by jev_ask (the provider's 400 max_tokens_exceeded) drives
    a halve-and-retry through the INJECTED `split_unit` callable (the
    images + extractors live in main(), not here). split_unit None or
    returning None/[] => the unit is marked unjudged via the SAME leaf
    shape Task 4 established (parse_error True, reason
    'unsplittable>cap') — never a crash, never fail-open on one unit.
    Depth-capped (bounded termination, r2-m2): a still-splitting unit
    at MAX_EXPANSION_DEPTH becomes a leaf too.
    """
    state = hunk_state(h)
    # v0.3b: whole-file deletions are still deletions for question
    # routing; only code-change clusters get the generic set.
    questions = (DELETION_QUESTIONS
                 if state["change_type"] in ("deletion-only",
                                             "whole-file-deleted")
                 else HUNK_QUESTIONS)
    zero = (0.0, 0)
    leaf = _budget_leaf(h, "unsplittable>cap")
    # SEND gate (r1-m2): state + ALL questions <= HARD_CAP_TOKENS or the
    # payload is never sent. Defense-in-depth behind the pre-judge
    # soft-cap pass; the unit becomes an explicit unjudged leaf (NO
    # consecutive-failure count: the provider was never contacted).
    if payload_over_hard_cap(state, questions):
        return ([leaf], 0, [], *zero, None, None)
    try:
        payload, ms = ask(state, questions)
    except _OverBudget:
        # runtime over-budget (r6-m3): halve-and-retry via the injected
        # splitter. No splitter (or an unsplittable unit) => unjudged.
        # The outcome NEVER counts toward the consecutive-failure
        # counter (r3-M5 "one attempt"): the explicit leaf feeds the
        # incomplete-review downgrade instead — a budget chain is not a
        # dead provider, so consecutive over-budget units must not
        # fail the run open (test_consecutive_accounting_single).
        if split_unit is None or depth >= MAX_EXPANSION_DEPTH:
            # depth 0: the unit IS the leaf (count unchanged). depth > 0:
            # the leaf replaces a split-allocated sub-unit (+1).
            return ([leaf], 1 if depth > 0 else 0, [], *zero, None, None)
        try:
            subs = split_unit(h)
        except (RecursionError, MemoryError) as split_exc:
            # r19-MAJOR-1 (round-5): the splitter runs INSIDE this
            # `except _OverBudget:` handler — a sibling clause can never
            # catch what raises here (Python semantics), so the splitter
            # needs its own guard. A crashed split becomes the explicit
            # leaf, exactly like an unsplittable unit; never a crash.
            return ([_budget_leaf(h, f"splitter-failed: {split_exc!r}"
                                  [:120])],
                    1 if depth > 0 else 0, [], *zero, None, None)
        if not subs:
            return ([leaf], 1 if depth > 0 else 0, [], *zero, None, None)
        records: list = []   # carriers + leaf records, in unit order
        sub_added_list: list = []  # r20-M3: nested growth deltas, kept
        # the parent is REPLACED by len(subs) units (r7-m1): base NET is
        # len(subs) - 1; recursion adds each sub's own nested delta.
        added = len(subs) - 1
        lat: list = []
        tok_sum = 0.0
        tok_n = 0
        for sub in subs:
            (sub_records, sub_added, sub_lat, sub_tok, sub_n,
             sub_fail, sub_shape) = _judge_unit(sub, ask, split_unit,
                                                depth + 1)
            if sub_fail is not None:
                # an ordinary transport error below the split bubbles up
                # as this chain's failure (judge() counts it once).
                # r15-m3: the leaf's reason names the TRANSPORT failure
                # shape, not `unsplittable>cap` — the digest must say
                # the provider call failed (and the fail-open check must
                # see a real transport failure, not a budget leaf).
                # r16-m2: siblings judged BEFORE the failure are kept —
                # discarding real findings (and their latencies) made the
                # failure strictly more destructive than the bug it
                # guards against. The chain still reports transport_fail
                # exactly once, so the consecutive-failure accounting is
                # unchanged; the leaf record is dropped (the failure
                # itself feeds judge()'s parse_error record).
                if sub_records:
                    records.extend(r for r in sub_records
                                   if "_payload" in r)
                # r19-m3 (round-5): the failing sub AND every later
                # (untried) sibling get an explicit leaf record — the
                # run's coverage accounting must see them, not silently
                # drop them. Growth stays the chain base `len(subs)-1`
                # (the parent slot is replaced by the records we emit:
                # judged carriers + leaves for the rest).
                failed_i = subs.index(sub)
                for s in subs[failed_i:]:
                    records.append(_budget_leaf(
                        s, "transport-failure-below-split"))
                # r20-M3 (round-6): the nested deltas (sub_added) are real
                # units already created below the split — zeroing them
                # under-reported the growth and broke the depth-cap
                # termination math whenever sub 1 split before sub 2
                # failed. Sum the nested deltas into the chain base.
                return (records, (len(subs) - 1) + sum(sub_added_list),
                        lat, tok_sum, tok_n, sub_fail, None)
            if sub_shape is not None:
                # a shape error below the split bubbles up the same way.
                # r16-m2: keep already-judged siblings here too.
                if sub_records:
                    records.extend(r for r in sub_records
                                   if "_payload" in r)
                sleaf = _budget_leaf(sub, "shape-failure-below-split")
                failed_i = subs.index(sub)
                for s in subs[failed_i + 1:]:
                    records.append(_budget_leaf(
                        s, "shape-failure-below-split"))
                return (records + [sleaf], len(subs) - 1, lat, tok_sum,
                        tok_n, None, sub_shape)
            records.extend(sub_records)
            sub_added_list.append(
                0 if (sub_records and len(sub_records) == 1
                      and sub_records[0].get("parse_error")
                      and sub_records[0].get("reason")) else sub_added)
            # r16-m1 (round-2): a sub at depth+1 that resolves to its own
            # explicit leaf reports sub_added = 1 ("the leaf replaces a
            # split-allocated sub-unit"), but this chain's base
            # `len(subs) - 1` ALREADY counted that slot — the bonus
            # double-counted it. A leaf-resolved sub is NET-ZERO growth.
            added += 0 if (sub_records and len(sub_records) == 1
                           and sub_records[0].get("parse_error")
                           and sub_records[0].get("reason")) else sub_added
            lat.extend(sub_lat)
            tok_sum += sub_tok
            tok_n += sub_n
        return (records, added, lat, tok_sum, tok_n, None, None)
    except Exception as exc:
        # The ask itself failed with an ordinary (non-over-budget) error.
        # r19-MAJOR-1 CORRECTION (round-5): the earlier r15-m4 note here
        # was WRONG — an exception raised inside the `except _OverBudget:`
        # handler above (splitter crash, a sub's hunk_state exploding) is
        # NOT matched by this sibling clause. That path now has its own
        # guards: the splitter is wrapped (leaf on RecursionError/
        # MemoryError) and the AST helpers catch RecursionError/
        # MemoryError alongside SyntaxError/ValueError, so nothing
        # escapes _judge_unit.
        return ([], 0, [], *zero, repr(exc)[:300], None)
    # sentinel dict: distinguishes "transport success" from leaf records;
    # `_hunk` carries the ACTUAL unit judged (r15-M4: runtime-split subs
    # previously reported at the parent's anchor, losing per-window
    # anchoring — judge() reads `_hunk` when present).
    return ([{"_payload": payload, "_ms": ms, "_state": state,
              "_hunk": h}], 0, [ms], *zero, None, None)


def _budget_leaf(h, reason):
    """The Task-4 leaf-record shape, reused at runtime (plan Task 5)."""
    return {"hunk": h, "parse_error": True, "raw": None,
            "reason": reason, "latency_ms": 0.0}


def judge(hunks, ask, errors=None, *, split_unit=None):
    """ask is the wired provider's ask(state, questions) (E8 contract).

    errors, if given, collects a short repr of every failed call (transport
    or response shape) so a fail-open run can say WHY — the first live
    install failed open on an SSL CA error that the report never showed.

    F1: deletion-only clusters (no '+' in the cluster's own run) get
    DELETION_QUESTIONS — removal-risk scoring instead of code-bug scoring;
    all other clusters get HUNK_QUESTIONS. The response contract and
    compose() gating are identical for both sets.

    Plan Task 5: split_unit is INJECTED by main() (keyword-only, r7-m2 —
    main() owns the file images + Tasks 2/3 extractors; judge() has
    none). When the provider answers 400 max_tokens_exceeded, judge()
    halves-and-retries through it; split_unit=None marks the unit
    unjudged instead (never a crash). Returns (findings, latencies,
    meta) where meta = {"added_units": net runtime-split growth,
    "avg_input_tokens": float|None from payload usage.input_tokens}
    (r5-m6) — EVERY return path, fail-open included, carries the 3rd
    element.
    """
    findings, latencies, failures = [], [], 0
    parse_failures = 0  # M1 (r8): consecutive shape errors, separate counter
    kept_hunks = len(hunks)
    added_units = 0
    tokens_sum = 0.0
    tokens_n = 0
    for h in hunks:
        (records, added, lat, tok, n_tok,
         transport_fail, shape_fail) = _judge_unit(h, ask, split_unit, 0)
        added_units += added
        latencies.extend(lat)
        tokens_sum += tok
        tokens_n += n_tok
        if transport_fail is not None:
            # ordinary transport failure — counts toward the consecutive
            # limit exactly as before. An _OverBudget arrives here with
            # its explicit unjudged leaf in `records` and counts ONCE
            # toward the counter for the WHOLE chain (r3-M5).
            # r17-B1 (Opus Task-10 round-3): `records` may hold raw
            # sentinel CARRIERS ({"_payload", ...}) from sub-units that
            # were judged BEFORE a sibling's transport failure (r16-m2
            # keeps them). Extending them into `findings` leaked dicts
            # with no "hunk" key — a KeyError in _digest_label/main.
            # PARSE each successful carrier here (same shape contract as
            # the main path) so its real judgment survives; a carrier
            # that does not parse becomes a parse_error record on its
            # own sub-unit. Conversion-only was wrong: it discarded a
            # successful judgment and could trip the all-failed check.
            for r in records:
                if "_payload" not in r:
                    findings.append(r)
                    continue
                pl, r_ms, r_state = r["_payload"], r["_ms"], r["_state"]
                r_hunk = r.get("_hunk", h)
                r_usage = pl.get("usage") if isinstance(pl, dict) else None
                if isinstance(r_usage, dict):
                    it = r_usage.get("input_tokens")
                    if isinstance(it, (int, float)) and \
                            math.isfinite(float(it)):
                        tokens_sum += float(it)
                        tokens_n += 1
                try:
                    r_ans = pl["answers"]
                    r_sev = r_ans["severity"]
                    r_real = r_ans["is_real_issue"]
                    r_cat = r_ans["category"]
                    r_score = float(r_sev.get("score", 0))
                    r_noul = r_real.get("noul")
                    if not math.isfinite(r_score):
                        raise ValueError(f"non-finite severity: {r_score!r}")
                    if not isinstance(r_noul, (int, float, bool)) or \
                            not math.isfinite(float(r_noul)):
                        raise ValueError(f"non-numeric noul: {r_noul!r}")
                    findings.append({
                        "hunk": r_hunk, "severity": r_score,
                        "sev_dist": r_sev.get("probabilities"),
                        "confidence": r_sev.get("confidence"),
                        "is_real": r_noul,
                        "category": r_cat.get("choice"),
                        "cat_dist": r_cat.get("probabilities"),
                        "rubric": ("deletion"
                                   if r_state["change_type"] in
                                   ("deletion-only", "whole-file-deleted")
                                   else "code-change"),
                        "references_remaining":
                            r_state.get("references_remaining"),
                        "change_type": r_state["change_type"],
                        "latency_ms": round(r_ms, 1),
                    })
                except (KeyError, TypeError, AttributeError,
                        ValueError) as r_exc:
                    if errors is not None:
                        errors.append(f"bad response shape: {r_exc!r}"[:300])
                    findings.append({"hunk": r_hunk, "parse_error": True,
                                     "raw": pl,
                                     "latency_ms": round(r_ms, 1),
                                     "reason":
                                         "shape-failure-below-split"})
            if errors is not None:
                errors.append(transport_fail)
            failures += 1
            if failures >= CALL_FAIL_LIMIT:
                meta = {"added_units": added_units,
                        "avg_input_tokens": None}
                return None, latencies, meta  # fail-open signal
            # M2 (r9): record the failed call so the incomplete-review
            # downgrade can see it (a 1-cluster diff can never reach the
            # consecutive limit, but its failure must not vanish) —
            # unless the unit already carries its own explicit leaf.
            if not records:
                findings.append({"hunk": h, "parse_error": True,
                                 "raw": None, "latency_ms": 0.0})
            continue
        # transport success resets the shared counter BEFORE parsing
        # starts (m3 (r11) semantics preserved); r19-m4: the reset moved
        # into the carriers-nonempty branch above — an all-leaf chain
        # (no provider contact) no longer resets it.
        if shape_fail is not None:
            if errors is not None:
                errors.append(shape_fail)
            parse_failures += 1
            failures += 1
            if parse_failures >= CALL_FAIL_LIMIT or failures >= CALL_FAIL_LIMIT:
                meta = {"added_units": added_units,
                        "avg_input_tokens": None}
                return None, latencies, meta  # fail-open signal
            findings.append({"hunk": h, "parse_error": True,
                             "raw": None, "latency_ms": 0.0})
            continue
        # r18-B1 (Opus Task-10 round-4): the old `records[0]` shortcut
        # leaked carriers whenever a LEAF came FIRST in the split order
        # (sub1 -> leaf, sub2 -> judged): both records extended raw, the
        # carrier without a 'hunk' key -> KeyError in _digest_label.
        # Always partition; leaves extend, carriers parse (the loop
        # below handles 0, 1, or N carriers uniformly).
        leaf_part = [r for r in records if "_payload" not in r]
        findings.extend(leaf_part)
        carriers = [r for r in records if "_payload" in r]
        # r18-B1: an all-leaf chain (nothing was ever judged) has no
        # carrier to parse — its leaves already carry the coverage.
        # r19-m4 (round-5): such a chain NEVER CONTACTED the provider, so
        # it must NOT reset the consecutive-failure counter (a dead
        # provider interleaved with send-gate leaves would otherwise
        # never reach CALL_FAIL_LIMIT).
        if not carriers:
            continue
        failures = 0
        carrier = carriers[0]
        pending_carriers = carriers[1:]
        payload, ms, state = carrier["_payload"], carrier["_ms"], \
            carrier["_state"]
        rec_hunk = carrier.get("_hunk", h)  # r15-M4: actual sub-unit
        # (r17-M1: the parse_failures reset that stood here defeated the
        # consecutive shape-error counter — main() resets ONLY after a
        # successful parse, at the `parse_failures = 0` inside the try.)
        # Task 5 (r2-M4): the call's usage.input_tokens reaches the
        # ledger via meta.avg_input_tokens (jev payloads carry `usage`;
        # laya's do not — None, never fabricated).
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            it = usage.get("input_tokens")
            if isinstance(it, (int, float)) and math.isfinite(float(it)):
                tokens_sum += float(it)
                tokens_n += 1
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
                "hunk": rec_hunk,  # r15-M4: the actual sub-unit judged
                "severity": score,
                "sev_dist": sev.get("probabilities"),
                "confidence": sev.get("confidence"),
                "is_real": noul,
                "category": cat.get("choice"),
                "cat_dist": cat.get("probabilities"),
                # v0.3b: rubric provenance + the deterministic
                # corroboration signal ride on the finding so compose()
                # can apply the deletion rubric's own threshold and the
                # corroboration gate without re-deriving anything.
                "rubric": ("deletion"
                           if state["change_type"] in ("deletion-only",
                                                       "whole-file-deleted")
                           else "code-change"),
                "references_remaining": state.get("references_remaining"),
                "change_type": state["change_type"],
                "latency_ms": round(ms, 1),
            }
            findings.append(rec)
            parse_failures = 0
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            if errors is not None:
                errors.append(f"bad response shape: {exc!r}"[:300])
            # M1 (r7)/m2 (r9): shape errors count toward fail-open — a wrong
            # response shape on every call is a broken/changed API, not a
            # set of harmless per-hunk misses. ValueError covers non-numeric
            # scores ("high"), which would otherwise kill the whole run.
            # The counter is separate from transport failures: transport
            # success resets `failures`, so a run of 200-with-garbage
            # responses could otherwise never reach the limit.
            parse_failures += 1
            # m3 (r11), reworded per r12 MINOR 1: `failures` is deliberately
            # SHARED between transport and parse failures, but transport
            # success resets it BEFORE parsing starts — so the shared
            # counter only fails open for parse→transport orderings (1+1),
            # not transport→parse (each sits at 1). That residual case is
            # caught downstream instead: a parse_error finding triggers the
            # incomplete-review downgrade, and all-parse-failed triggers
            # full fail-open. `parse_failures` catches consecutive
            # same-cause shape errors in every ordering.
            failures += 1
            if parse_failures >= CALL_FAIL_LIMIT or failures >= CALL_FAIL_LIMIT:
                meta = {"added_units": added_units,
                        "avg_input_tokens": None}
                return None, latencies, meta  # fail-open signal
            findings.append({"hunk": rec_hunk, "parse_error": True,
                             "raw": payload, "latency_ms": round(ms, 1)})
        # remaining carriers from this unit's runtime split parse with
        # the same shape contract (usage extraction + answers parsing).
        for carrier in pending_carriers:
            payload = carrier["_payload"]
            ms = carrier["_ms"]
            state = carrier["_state"]
            pc_hunk = carrier.get("_hunk", h)  # r15-M4: actual sub-unit
            usage = payload.get("usage") if isinstance(payload, dict) \
                else None
            if isinstance(usage, dict):
                it = usage.get("input_tokens")
                if isinstance(it, (int, float)) and \
                        math.isfinite(float(it)):
                    tokens_sum += float(it)
                    tokens_n += 1
            try:
                ans = payload["answers"]
                sev = ans["severity"]
                real = ans["is_real_issue"]
                cat = ans["category"]
                score = float(sev.get("score", 0))
                noul = real.get("noul")
                if not math.isfinite(score):
                    raise ValueError(f"non-finite severity score: {score!r}")
                if not isinstance(noul, (int, float, bool)) or \
                        not math.isfinite(float(noul)):
                    raise ValueError(f"non-numeric noul: {noul!r}")
                findings.append({
                    "hunk": pc_hunk, "severity": score,  # r15-M4
                    "sev_dist": sev.get("probabilities"),
                    "confidence": sev.get("confidence"),
                    "is_real": noul,
                    "category": cat.get("choice"),
                    "cat_dist": cat.get("probabilities"),
                    "rubric": ("deletion"
                               if state["change_type"] in
                               ("deletion-only", "whole-file-deleted")
                               else "code-change"),
                    "references_remaining":
                        state.get("references_remaining"),
                    "change_type": state["change_type"],
                    "latency_ms": round(ms, 1),
                })
                parse_failures = 0
            except (KeyError, TypeError, AttributeError, ValueError) as exc:
                if errors is not None:
                    errors.append(f"bad response shape: {exc!r}"[:300])
                parse_failures += 1
                failures += 1
                if parse_failures >= CALL_FAIL_LIMIT or \
                        failures >= CALL_FAIL_LIMIT:
                    meta = {"added_units": added_units,
                            "avg_input_tokens": None}
                    return None, latencies, meta  # fail-open signal
                findings.append({"hunk": pc_hunk, "parse_error": True,
                                 "raw": payload,
                                 "latency_ms": round(ms, 1)})
    # M2 (r9), the reviewer's stronger option: if EVERY call failed
    # (nothing was ever judged), that is a dead provider — full fail-open
    # regardless of the consecutive-counter arithmetic. m1 (r11): a
    # 200-with-garbage provider never appends a latency either, so
    # "nothing judged" means no successful parse, not just no transport
    # success. Task 5: a reason-marked BUDGET leaf is an EXPLICIT unjudged
    # skip (the gate refused / the cutters exhausted), not a dead
    # provider. r16-m3 (round-2): a leaf whose reason names a TRANSPORT
    # or shape failure is the opposite — it must NOT suppress fail-open
    # (a run whose every call failed must read "Unavailable", not
    # "incomplete"), so those reasons are excluded from the skip check.
    # r17-B1 (round-3): records converted FROM carriers at a below-split
    # transport failure carry no reason, so the same exclusion needs a
    # marker — those conversions carry reason
    # "transport-failure-below-split" too (set at the conversion site).
    _failure_reasons = ("transport-failure-below-split",
                        "shape-failure-below-split")
    if kept_hunks and not any(not f.get("parse_error") for f in findings) \
            and not any(f.get("reason")
                        and f.get("reason") not in _failure_reasons
                        for f in findings):
        meta = {"added_units": added_units, "avg_input_tokens": None}
        return None, latencies, meta
    meta = {"added_units": added_units,
            "avg_input_tokens": (tokens_sum / tokens_n) if tokens_n else None}
    return findings, latencies, meta


def _digest_label(f):
    """One PR-level digest line per finding (r11-m1): a parse_error record
    with a reason marker is an EXPLICIT unjudged skip (an unsplittable
    leaf), never "provider call failed" — which would be false."""
    if f.get("parse_error"):
        if f.get("reason"):
            return (f"- {f['hunk']['file']}:{f['hunk']['line']} unjudged "
                    f"(skipped: {f['reason']})")
        return (f"- {f['hunk']['file']}:{f['hunk']['line']} unjudged "
                f"(provider call failed)")
    return (f"- {f['hunk']['file']}:{f['hunk']['line']} "
            f"severity={SEV_NAME[sev_level(f.get('severity'))]} "
            f"category={f.get('category')}")


def judge_pr_level(findings, ask, size_skipped_code=None):
    """One extra round-trip: PR-level risk from the per-hunk digest.

    Step 0′ (hunk-size investigation, 2026-10-01): size-skipped
    CODE-change clusters appear as explicit unjudged lines, so the
    risk model learns the core files were never judged. (compose()
    never reads pr_level, so this is report-only — the digest change
    is what justifies eventual version-bump handling, per the doc.)
    """
    prov_name = _PROVIDER_NAME  # r9 m1: the wired provider, not the env
    # m2 (r10): failed calls must not look like clean hunks — label them
    # "unjudged" so the PR-level model can't read them as severity=none.
    # r11-m1: parse_error records carrying a reason marker (unsplittable
    # leaves) label as "skipped: <reason>", not "provider call failed".
    # Task 6 (r2-M2): a parse_error record whose hunk carries ast_context
    # is a leaf from the RE-expansion pass (post-enrichment, depth-capped
    # at the initial pass already — the context can only be present when
    # this leaf came from Task 6's step-3 recursion); r12-M1 makes that
    # path unreachable in practice, but the label must still be right if
    # a future depth-cap change ever produces one.
    lines = []
    for f in findings:
        line = _digest_label(f)
        if f.get("parse_error") and "ast_context" in f.get("hunk", {}):
            line += " (from enriched re-expansion)"
        lines.append(line)
    for s in size_skipped_code or []:
        lines.append(f"- {s['file']}:{s.get('line_start', '?')} unjudged "
                     f"(skipped: {s.get('reason')})")
    digest = "\n".join(lines) or "no per-hunk findings"
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


def compose(findings, skipped, pr_level, threshold=REAL_THRESHOLD,
            deletion_threshold=DELETION_REAL_THRESHOLD):
    """Thresholds in code. Plateau rule: 0.50 sits >=0.05 from 0.80/0.90.

    v0.3b (Kurt review, implements the F1 corroboration proposal; M2 fix
    extends the gate to MAJORs): a deletion-rubric finding drives the
    verdict ONLY when corroborated — references_remaining True (surviving
    context mentions a removed name) OR a reported CODE-CHANGE finding
    exists in the run. Deletion findings corroborating each other do NOT
    count: #45 had six deletion clusters all wrong together. An
    uncorroborated deletion finding is still REPORTED (the human sees it)
    but cannot push the verdict to "Changes requested" — at any severity.

    deletion_threshold: sweep hook (F2 executability plan, step b). The
    sweep replays logged runs through compose() to measure candidate
    deletion-rubric thresholds; without this parameter the 0.70 knob is a
    hardcoded module constant no external caller can move. Default keeps
    the shipped behavior byte-identical.
    """
    reported, jitter = [], []
    for f in findings:
        if f.get("parse_error"):
            continue
        rubric = f.get("rubric", "code-change")
        t = deletion_threshold if rubric == "deletion" else threshold
        r = f.get("is_real")
        if near(r, t):
            jitter.append({"file": f["hunk"]["file"], "is_real": r})
        if r is not None and r >= t and (f.get("severity") or 0) >= 1:
            reported.append(f)
    # Corroboration pool (v0.3b M2 fix, Opus r2 M2, r3 m2/r4 m1): a
    # reported CODE-CHANGE finding corroborates a deletion finding when
    # it is itself sev>=2 (any category — a sev>=2 "style" flag is a
    # serious claim, not a nit), OR same-file with a non-style category
    # (a real issue in the deletion's own neighborhood, any severity).
    # category=None is treated as style-like for the same-file path.
    # A sev<2 style finding — anywhere — never unlocks the gate (#45
    # shape: six wrong deletion findings must stay report-only).
    def _corroborates(cf, df):
        same_file = cf["hunk"]["file"] == df["hunk"]["file"]
        if same_file:
            return (sev_level(cf.get("severity")) >= 2
                    or cf.get("category") not in ("style", None))
        return sev_level(cf.get("severity")) >= 2

    corroboration_pool = [f for f in reported
                          if f.get("rubric", "code-change") != "deletion"]
    blockers: list[dict] = []
    majors: list[dict] = []
    for f in reported:
        lvl = sev_level(f.get("severity"))
        if lvl >= 2:
            if (f.get("rubric", "code-change") == "deletion"
                    and not f.get("references_remaining")
                    and not any(_corroborates(c, f)
                                for c in corroboration_pool)):
                continue  # uncorroborated deletion finding: report, not verdict
            (blockers if lvl == 3 else majors).append(f)
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
        for j, (gfile, gline, _gdesc) in enumerate(golden):
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

def size_skipped_code(skipped):
    """Size-skipped CODE-change clusters (Step 0′): unjudged coverage, not
    deliberate triage. Deletion/whole-file size-skips stay triage. Single
    source for both the PR-level digest and the incomplete-review counters,
    which must agree."""
    return [s for s in skipped
            if str(s.get("reason", "")).startswith("hunk>")
            and s.get("change_type", "code-change")
            not in ("deletion-only", "whole-file-deleted")]


def render(reported, skipped, verdict, pr_level, jitter, meta, n_sent=None):
    """Render the human report.

    n_sent (AST-units Task 4 seam): judged model-call count when it
    differs from len(meta["latencies"]) — Task 5's split loop judges
    MORE calls than units. Defaults to meta's call count (today's
    behavior) so current callers are unchanged.
    """
    prov = meta.get("provider", "jev")
    model = meta.get("model")
    prov_name = f"{prov}/{model}" if (prov == "laya" and model) else prov
    out = ["SYSTEM-ONE REVIEW (experimental local reviewer — advisory only, "
           f"provider: {prov_name})"]
    out.append(f"repo={meta['repo']} mode={meta['mode']} head={meta['head'][:10]}")
    # r7-m3/r14-n2 (AST-units Task 4): "analyzed" = accounted UNITS (whole
    # parents + sub-clusters + leaves), NOT model calls; judged-call count
    # is separate. Ceiling drops are counted OUTSIDE `skipped` (a ceiling
    # drop is not triage — r14-n2); laya's legacy single-number label is
    # byte-identical (no ceiling entries exist there — r5-M4).
    n_ceiling = sum(1 for s in skipped
                    if s.get("reason") == "max-hunks>ceiling")
    triage_skipped = len(skipped) - n_ceiling
    out.append(f"analyzed={meta['n_analyzed']} units "
               f"({n_sent if n_sent is not None else meta['jev_calls']} "
               f"judged calls), "
               f"skipped={triage_skipped}, "
               f"total_latency={meta['total_latency_ms']:.0f}ms")
    if n_ceiling:
        ceiling_items = [f"{s['file']}" for s in skipped
                         if s.get("reason") == "max-hunks>ceiling"]
        counts_c: dict[str, int] = {}
        for cf in ceiling_items:
            counts_c[cf] = counts_c.get(cf, 0) + 1
        parts = [f"{cf}" + (f" x{n}" if n > 1 else "")
                 for cf, n in counts_c.items()]
        out.append(f"Not judged (run ceiling): {n_ceiling} "
                   f"unit(s) over --max-hunks — {', '.join(parts)}")
    if meta.get("fail_open"):
        out.append(f"!! {prov_name} unavailable after repeated failures — "
                   "heuristic-only run, treat as triage not review")
        if meta.get("fail_reason"):
            out.append(f"!! last error: {meta['fail_reason']}")
    out.append("")
    if meta.get("n_hunks") == 0:
        out.append("Empty diff — nothing to review (check the range/mode).")
    elif not reported:
        out.append("No findings above threshold.")
    # Most severe first; stable, so equal severities keep compose() order.
    for f in sorted(reported, key=lambda f: -(f.get("severity") or 0)):
        sev = SEV_NAME.get(sev_level(f.get("severity")), "?")
        out.append(f"[{sev}] {f['hunk']['file']}:{f['hunk']['line']} "
                   f"({f.get('category')}, is_real={f.get('is_real')})")
        out.append(f"  hunk: {f['hunk']['header']}")
        for line in f["hunk"]["lines"][:6]:
            out.append("    " + line)
        out.append("")
    if jitter:
        out.append("Jitter-zone scores (within 0.03 of threshold — do not trust):")
        for j in jitter:
            out.append(f"  {j['file']} is_real={j['is_real']}")
        out.append("")
    if pr_level and pr_level.get("overall_risk") is not None:
        out.append(f"PR-level risk: {pr_level['overall_risk']}/3, "
                   f"needs_human_review={pr_level.get('needs_human_review')}")
    # r14-m1: ceiling entries NEVER appear under Skipped-triage — they have
    # their own "Not judged (run ceiling)" line above (a drop is not triage).
    triage_skips = [s for s in skipped
                    if s.get("reason") != "max-hunks>ceiling"]
    if triage_skips:
        # One entry per (file, reason): an oversized file or a lockfile
        # yields one skip per hunk, which buried the distinct entries.
        counts: dict[tuple[str, str], int] = {}
        for s in triage_skips:
            key = (s["file"], s["reason"])
            counts[key] = counts.get(key, 0) + 1
        items = [f"{f} ({r})" + (f" x{n}" if n > 1 else "")
                 for (f, r), n in counts.items()]
        more = f" (+{len(items) - 10} more)" if len(items) > 10 else ""
        out.append("Skipped (deterministic triage): " +
                   ", ".join(items[:10]) + more)
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
    clear_runtime_caches()  # r19-m5: per-run caches, never across runs
    ap = argparse.ArgumentParser(prog="system-one-reviewer")
    ap.add_argument("--version", action="version",
                    version=f"%(prog)s {__version__}")
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
    # Task 6 (r5-m2): a MEASUREMENT knob for Task 8's mandatory
    # enrichment-off arm, not a user feature — it skips the
    # ast_context attachment entirely.
    ap.add_argument("--no-enrichment", dest="no_enrichment",
                    action="store_true",
                    help="disable AST enclosing-symbol enrichment "
                         "(measurement arm; states stay v03b-shaped)")
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
    # r5-M4: the size gate is mechanical via the provider param. jev (the
    # default) never size-skips — oversize clusters route through the
    # Task 2/3 cutter below; laya keeps today's exact behavior.
    kept, skipped = triage(hunks, provider=provider)
    n_triaged = len(hunks) - len(kept)  # deliberate skips, NOT drops (r10 M1)

    # AST-units plan Task 4 — BINDING pre-judge pipeline (r11-M1/r12/r13):
    #   (1) route + expand (token-gated, recursive r7-M2)
    #   (2) attach ast_context (jev only, unless --no-enrichment; Task 6)
    #   (3) re-estimate + RE-expand (step 0: DROP ast_context, r12-M1)
    #   (4) set leaves aside — EXEMPT from --max-hunks, BEFORE truncation
    #   (5) truncate to the ceiling in FIRST-COME-ACROSS-FILES order
    #   (6) freeze n_units_pre / n_dropped
    if provider == "jev" and kept:
        # r2-M2: per-mode pre/post file images for the cutter; a missing
        # image degrades (mode_file_images returns None) — never exits.
        images = lambda path, unit: mode_file_images(  # noqa: E731
            args.repo, mode, head, path,
            old_file=unit.get("old_file"))
        kept, leaves = expand_oversize_units(kept, images)
        # Task 6 step (2) (r5-m3): attach ast_context AFTER the
        # pre-judge expansion, jev only and never under
        # --no-enrichment; hunk_state reads the key WHEN PRESENT, so
        # the attachment point is the whole mechanism and a laya state
        # can never carry it.
        if not args.no_enrichment:
            kept = attach_ast_context(kept, images)
            # Task 6 step (3) (r2-M2/r12-M1): re-estimate and RE-expand
            # BEFORE the counters freeze — an over-cap unit is over
            # BECAUSE of its context, so the re-expansion order
            # TERMINATES AT STEP 0 (context dropped, no split); the
            # leaves-aside → truncate → freeze ordering below stands as
            # a guard. The pass-1 `leaves` stay the run's leaf set:
            # attachment only touches `kept`, so a pass-1 leaf can
            # neither gain nor lose its record here.
            kept, reexp_leaves = reexpand_after_enrichment(kept, images)
            # r15-m8: pass 2 is NOT provably a no-op — a band unit that
            # hit the depth cap in pass 1 restarts at depth 0 here and
            # can still split (step 0 only guarantees no SPLIT caused by
            # the context, not no split at all). Any leaf it produces is
            # a real unjudged unit and joins the run's leaf set.
            if reexp_leaves:
                leaves = leaves + reexp_leaves
        n_leaf_unjudged = len(leaves)
    else:
        leaves = []
        n_leaf_unjudged = 0
    # r9-M1/r13-M1: n_units_pre is recorded BEFORE truncation and INCLUDES
    # leaves (they were set aside in step 4, so the pre-truncation list
    # alone would under-count the denominator).
    n_units_pre = len(kept) + n_leaf_unjudged
    # r1-m8: units-per-run ceiling in first-come-across-files order — NO
    # size sort (which could drop arbitrary sub-clusters of one parent).
    # LAYA KEEPS TODAY'S size sort + truncate (r6-m1); laya never emits
    # ceiling entries — its truncation stays the legacy counter math.
    if provider == "jev":
        n_ceiling_dropped = max(0, len(kept) - args.max_hunks)
        if n_ceiling_dropped:
            skipped = skipped + [
                {"file": u["file"] or "", "reason": "max-hunks>ceiling",
                 **_span(u)}
                for u in kept[args.max_hunks:]]
            kept = kept[:args.max_hunks]
        n_dropped = n_units_pre - n_leaf_unjudged - len(kept)
    else:
        kept.sort(key=lambda h: -h["size"])
        kept = kept[: args.max_hunks]
        n_ceiling_dropped = 0
        n_dropped = len(hunks) - n_triaged - len(kept)

    call_errors: list[str] = []
    # Task 5 (r6-m3): main() owns the file images + Tasks 2/3 extractors,
    # so it INJECTS the runtime splitter as a keyword-only argument.
    # judge() catches _OverBudget (jev's 400 max_tokens_exceeded) and
    # halves-and-retries through this closure; laya never sees either.
    jev_splitter = (_runtime_split_unit_factory(args.repo, mode, head)
                    if provider == "jev" else None)
    findings, latencies, judge_meta = judge(kept, ask, errors=call_errors,
                                            split_unit=jev_splitter)
    fail_open = findings is None
    pr_level = None  # set below unless the run failed open or the diff is empty
    fail_reason = call_errors[-1] if fail_open and call_errors else None
    if fail_open:
        findings = []
    else:
        # r10-m1 INSERTION WINDOW (plan Task 4), Amended r15-B1/M1 (Opus
        # Task-10 review): leaf records join findings BEFORE
        # judge_pr_level/compose see the run — the digest gets its
        # `unjudged (skipped: unsplittable>cap)` lines and a run whose
        # every unit is a leaf can never compose to a clean "Approved"
        # (an all-leaf diff is an incomplete review, not a pass).
        # fail-open discards leaves with everything else (findings == []
        # above; its verdict is forced to "Unavailable" regardless).
        # judge() never saw them (set aside pre-judge), so they are
        # never SENT.
        if leaves:
            findings = findings + leaves
    if not fail_open and hunks:  # empty diff: nothing for PR-level to judge
        # r14-m2: ceiling-dropped units reach the digest explicitly — on
        # jev no `hunk>` records exist, so today's hunk>-only filter would
        # hide a ceiling drop from the PR-level model entirely.
        pr_level = judge_pr_level(
            findings, ask,
            size_skipped_code=size_skipped_code(skipped)
            + [s for s in skipped if s.get("reason") == "max-hunks>ceiling"])
    # M1 (r9): a fail-open run must never carry a clean "Approved" — the
    # verdict is forced to "Unavailable" and flows into JSON/metrics/last
    # line, so nothing downstream reads it as a pass.
    # M2 (r9): on a non-fail-open run, unjudged clusters (parse errors or
    # dropped over max-hunks) downgrade the verdict so partial reviews are
    # never mistaken for complete ones.
    reported, jitter, verdict = compose(findings, skipped,
                                        pr_level if not fail_open else None)
    # r15-M1: leaves now join BEFORE judge_pr_level/compose (see the
    # amended insertion window above); the old post-compose insert is
    # gone. n_unjudged counts them unchanged.
    n_unjudged = sum(1 for f in findings if f.get("parse_error"))
    # Step 0′ (hunk-size investigation, 2026-10-01): a size-skipped
    # CODE-change cluster is unjudged coverage, not deliberate triage —
    # it joins the downgrade trigger and the denominator, never the
    # numerator. Deletion/whole-file size-skips stay deliberate triage
    # (Kurt-decision 3: ≤1/52 observed clusters, holds zero goldens).
    n_size_skipped_code = len(size_skipped_code(skipped))
    # r9-M1 two-phase counters (Task 5 WIRED via judge_meta — r5-m6):
    #   n_units_total = n_units_pre + added_units (post-judge total)
    #   n_analyzed    = len(kept) + added_units + n_leaf_unjudged
    #   numerator     = n_analyzed − n_unjudged (leaf records feed it)
    #   denominator   = n_units_total + n_size_skipped_code
    # added_units is the NET runtime-split growth (leaves − 1 per split
    # parent, r7-m1: the over-budget parent is REPLACED, not kept).
    # A fail-open run discards runtime-split bookkeeping with everything
    # else (findings == [] above) — meta stays unread.
    added_units = judge_meta["added_units"] if judge_meta else 0
    n_units_total = n_units_pre + added_units
    n_analyzed = len(kept) + added_units + n_leaf_unjudged
    if fail_open:
        verdict = "Unavailable — provider failed (fail-open)"
    elif n_unjudged or n_dropped or n_size_skipped_code:
        verdict += (f" (incomplete review — "
                    f"{n_analyzed - n_unjudged} of "
                    f"{n_units_total + n_size_skipped_code} "
                    f"clusters judged)")
    # Step 0′: the raw compose() verdict, before any suffix. Downstream
    # structured consumers (sweep gate_run, shadow tally) read THIS, not
    # the suffixed string — the suffix retires as an API.
    base_verdict = verdict.split(" (incomplete review")[0] \
        if not fail_open else verdict

    total = sum(latencies)
    judged = [
        {"file": f["hunk"]["file"], "line": f["hunk"]["line"],
         **_span(f["hunk"]),
         "severity": f.get("severity"), "is_real": f.get("is_real"),
         "category": f.get("category"), "confidence": f.get("confidence"),
         # v03b (Opus r2 B1): the fields compose()'s gate reads MUST ride
         # into the ledger, or sweep replay falls back to code-change and
         # computes the wrong curve.
         "rubric": f.get("rubric", "code-change"),
         "references_remaining": f.get("references_remaining"),
         "change_type": f["hunk"].get("change_type", "code-change"),
         # Task 6 (r1-M1): per-unit enrichment presence in the JUDGED
         # state (r12-M1: a dropped unit logs "none" — the flag records
         # presence in the judged state, never the attempt).
         "enrichment": ("ast" if "ast_context" in f["hunk"] else "none"),
         "reported": f in reported}
        for f in findings if not f.get("parse_error")]
    meta = {"repo": os.path.basename(os.path.realpath(args.repo)),
            "mode": mode, "head": head,
            "provider": provider, "model": model,  # M3 (r11): report/metadata
            "n_hunks": len(hunks),
            # Task 6: the run-level enrichment stamp (r1-M1: the D7
            # run-level stamp stays; judged entries also carry their own
            # per-unit value). "ast" iff ANY unit state carries
            # ast_context; "none" under --no-enrichment / laya / when no
            # unit's file yielded a symbol table.
            "enrichment": ("ast" if any("ast_context" in u
                                        for u in kept) else "none"),
            # Task 7 (D7): the record-version rides in meta too, so the
            # JSON output and the ledger agree on what produced the run.
            "record_version": PACKAGING_VERSION,
            # r10-m2/r9-M1: the POST-judge formula — never bare len(kept),
            # or a runtime-split run logs n_analyzed short by added_units
            # and sweep :98 rejects a legal run. added_units=0 in Task 4
            # (Task 5 injects); n_leaf_unjudged is 0 unless leaves exist.
            "n_analyzed": n_analyzed,
            "total_latency_ms": total, "jev_calls": len(latencies),
            "fail_open": fail_open, "fail_reason": fail_reason}

    result = {"meta": meta, "pr_level": pr_level if not fail_open else None,
              "findings": [
                  {"file": f["hunk"]["file"], "line": f["hunk"]["line"],
                   **_span(f["hunk"]),
                   "severity": f.get("severity"), "is_real": f.get("is_real"),
                   "category": f.get("category"), "header": f["hunk"]["header"]}
                  for f in reported],
              "skipped": skipped, "jitter": jitter, "verdict": verdict,
              # Step 0′: structured verdict for downstream consumers —
              # gate_run keys on this + explicit counts, never the string.
              "base_verdict": base_verdict,
              "n_dropped": n_dropped, "n_unjudged": n_unjudged,
              "n_size_skipped_code": n_size_skipped_code}

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

    # F7 (field evals, 2026-09-28): label hygiene — an empty label weakens
    # the ledger (several field runs logged label:""). Default to the mode,
    # marked auto: so a sweep with a short user prefix can never collide
    # with generated labels (v0.3b, Kurt review).
    log_run({"label": args.label or f"auto:{mode}", "repo": meta["repo"], "mode": mode,
             "head": head[:10], "n_hunks": meta["n_hunks"],
             # r10-m2: the same post-judge n_analyzed as meta (r9-M1) —
             # the logged record is what sweep gate_run :98 checks.
             "n_analyzed": meta["n_analyzed"], "verdict": verdict,
             # Step 0′: structured completeness — gate_run reads these
             # (never defaulting a missing count to 0 when base_verdict
             # exists), so truncation stays rejected and size-skips don't
             # disqualify.
             "base_verdict": base_verdict,
             "n_dropped": n_dropped, "n_unjudged": n_unjudged,
             "n_size_skipped_code": n_size_skipped_code,
             "fail_open": fail_open, "fail_reason": fail_reason,
             "total_latency_ms": round(total, 1),
             "avg_call_ms": round(total / len(latencies), 1) if latencies else None,
             # Task 5 (r2-M4): mean usage.input_tokens across jev calls
             # (judge()'s meta) — recalibration data for CHARS_PER_TOKEN;
             # None for laya (whose payloads carry no `usage`).
             "avg_input_tokens": judge_meta["avg_input_tokens"]
             if judge_meta else None,
             "judged": judged,
             # Task 7 (D7): the ledger contract stamps — transport (D5:
             # per-cluster calls unchanged), wire_format (ast-units-v1 iff
             # any unit came from the Tasks 2/3 cutters), the run-level
             # enrichment stamp (above; judged entries carry per-unit
             # values), and the record-version (the gate_run key — also
             # stamped as record_version so old ledgers read distinctly
             # from the packaging_version field's sweep-gate role).
             "transport": "per-cluster",
             "wire_format": stamp_wire_format(kept),
             # D7 run-level enrichment stamp (same value as meta's; judged
             # entries carry their own per-unit values).
             "enrichment": meta["enrichment"],
             "record_version": PACKAGING_VERSION,
             "packaging_version": PACKAGING_VERSION,
             "tool_version": __version__,
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
