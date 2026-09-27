#!/usr/bin/env python3
"""jev-review — local PR review powered by deterministic code + TypeSafe Jev.

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
Fail-open: 2 consecutive Jev failures -> report ships with a JEV-UNAVAILABLE
banner, never dies.

Usage:
  jev-review --repo <path> (--range A..B | --pr N | --staged | --uncommitted)
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
    sys.exit("jev-review: set TYPESAFE_API_KEY (env) or put TYPESAFE_API_KEY=... "
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
            payload = json.loads(resp.read())
            break
        except Exception:
            _drop_conn()
            if attempt == 2:
                raise
    return payload, (time.perf_counter() - t0) * 1000.0


# ---------- deterministic stages ----------

def run_git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"jev-review: git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout


def resolve_diff(repo, args):
    """Return (diff_text, head_sha, mode)."""
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
    sys.exit("jev-review: pick one of --range/--pr/--staged/--uncommitted")


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def package_hunks(diff):
    """Cluster-level packaging: contiguous changed lines form a cluster, each
    with +/-4 context lines. Windows are clamped at @@ hunk boundaries (a
    cluster never crosses an @@ header), so one change never dilutes another.
    Anchors: first '+' in the cluster's own run -> else the first context
    entry with a lineno at/after the run -> else the run's hunk_start (a
    deletion-only cluster never collapses to line 1). Deterministic."""
    CTX = 4
    per_file, cur_file, entries = [], None, []
    old_line = new_line = hunk_start = 1
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            if cur_file is not None:
                per_file.append((cur_file, entries))
            cur_file, entries = line[6:], []
        elif line.startswith("---") or line.startswith("diff "):
            continue
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            old_line = int(m.group(1)) if m else 1
            new_line = int(m.group(2)) if m else 1
            hunk_start = new_line
        elif cur_file is not None:
            if line.startswith("+") and not line.startswith("+++"):
                entries.append(("+", new_line, line[1:], hunk_start))
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                entries.append(("-", None, line[1:], hunk_start))
                old_line += 1
            elif not line.startswith("\\"):
                entries.append((" ", new_line, line[1:], hunk_start))
                new_line += 1
                old_line += 1
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
                lo, hi = max(0, g[0] - CTX), min(len(seg), g[-1] + CTX + 1)
                window = seg[lo:hi]
                # anchor chain (plan Task 2): first '+' in the cluster's own
                # run, never a neighbouring cluster's window; then the first
                # context entry with a lineno at/after the run; then the run's
                # hunk_start
                anchor = next((e[1] for e in seg[g[0]:g[-1] + 1]
                               if e[0] == "+" and e[1] is not None), None)
                if anchor is None:
                    anchor = next((e[1] for e in seg[g[-1] + 1:hi]
                                   if e[0] == " " and e[1] is not None), None)
                if anchor is None:
                    anchor = seg_hunk_start
                lines, n_changed = [], 0
                for k, n, t, _ in window:
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
    for kind, _n, text, _hs in h["entries"]:
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


def judge(hunks, api_key):
    findings, latencies, failures = [], [], 0
    for h in hunks:
        state = hunk_state(h)
        try:
            payload, ms = jev_ask(state, HUNK_QUESTIONS, api_key)
            latencies.append(ms)
            failures = 0
        except Exception:
            failures += 1
            if failures >= CALL_FAIL_LIMIT:
                return None, latencies  # fail-open signal
            continue
        try:
            ans = payload["answers"]
            sev = ans["severity"]
            real = ans["is_real_issue"]
            cat = ans["category"]
            rec = {
                "hunk": h,
                "severity": float(sev.get("score", 0)),
                "sev_dist": sev.get("probabilities"),
                "confidence": sev.get("confidence"),
                "is_real": real.get("noul"),
                "category": cat.get("choice"),
                "cat_dist": cat.get("probabilities"),
                "latency_ms": round(ms, 1),
            }
            findings.append(rec)
        except (KeyError, TypeError, AttributeError):
            findings.append({"hunk": h, "parse_error": True,
                             "raw": payload, "latency_ms": round(ms, 1)})
    return findings, latencies


def judge_pr_level(findings, api_key):
    """One extra round-trip: PR-level risk from the per-hunk digest."""
    digest = "\n".join(
        f"- {f['hunk']['file']}:{f['hunk']['line']} severity={SEV_NAME[sev_level(f.get('severity'))]} "
        f"category={f.get('category')}" for f in findings) or "no per-hunk findings"
    try:
        payload, ms = jev_ask(
            "Change set under review, per-hunk automated digest:\n" + digest,
            PR_QUESTIONS, api_key)
        ans = payload["answers"]
        return {"overall_risk": float(ans["overall_risk"].get("score", 0)),
                "needs_human_review": ans["needs_human_review"].get("noul"),
                "latency_ms": round(ms, 1)}
    except Exception as exc:
        return {"overall_risk": None, "needs_human_review": None,
                "error": f"pr-level Jev call failed: {exc!r}"[:300]}


def near(v, t, zone=0.03):
    return v is not None and abs(v - t) <= zone


def compose(findings, skipped, pr_level):
    """Thresholds in code. Plateau rule: 0.50 sits >=0.05 from 0.80/0.90."""
    reported, jitter = [], []
    for f in findings:
        if f.get("parse_error"):
            continue
        r = f.get("is_real")
        if near(r, REAL_THRESHOLD):
            jitter.append({"file": f["hunk"]["file"], "is_real": r})
        if r is not None and r >= REAL_THRESHOLD and (f.get("severity") or 0) >= 1:
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
    matches = []  # (reported_idx, golden_idx, distance)
    for i, f in enumerate(reported):
        for j, (gfile, gline, gdesc) in enumerate(golden):
            if j in matched_golden:
                continue
            if f["hunk"]["file"] == gfile and abs(f["hunk"]["line"] - gline) <= 1:
                matches.append((abs(f["hunk"]["line"] - gline), i, j))
    matches.sort(key=lambda m: (m[0], golden[m[2]][1], m[1]))
    # nearest first; distance ties -> lower golden line -> earlier reported
    for _d, i, j in matches:
        if i in matched_reported or j in matched_golden:
            continue
        matched_reported.add(i)
        matched_golden.add(j)
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
            "matched": [(golden[j][0], golden[j][1]) for _d, i, j in
                        sorted(matches, key=lambda m: m[1])
                        if i in matched_reported and j in matched_golden],
            "missed": [g for j, g in enumerate(golden) if j not in matched_golden]}


# ---------- report ----------

def render(reported, skipped, verdict, pr_level, jitter, meta):
    out = []
    out.append("JEV REVIEW (experimental local reviewer — advisory only)")
    out.append(f"repo={meta['repo']} mode={meta['mode']} head={meta['head'][:10]}")
    out.append(f"analyzed={meta['n_analyzed']} hunks, "
               f"skipped={len(skipped)}, "
               f"total_latency={meta['total_latency_ms']:.0f}ms, "
               f"jev_calls={meta['jev_calls']}")
    if meta.get("fail_open"):
        out.append("!! Jev unavailable after repeated failures — "
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
    out.append(verdict)  # fixed last line for grep-ledgering
    return "\n".join(out)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(prog="jev-review")
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
    ap.add_argument("--json", action="store_true", help="JSON-only stdout")
    args = ap.parse_args()

    api_key = load_api_key()
    diff, head, mode = resolve_diff(args.repo, args)
    hunks = package_hunks(diff)
    kept, skipped = triage(hunks)
    kept.sort(key=lambda h: -h["size"])
    kept = kept[: args.max_hunks]

    findings, latencies = judge(kept, api_key)
    fail_open = findings is None
    if fail_open:
        findings = []
    else:
        pr_level = judge_pr_level(findings, api_key)
    reported, jitter, verdict = compose(findings, skipped,
                                        pr_level if not fail_open else None)

    total = sum(latencies)
    judged = [
        {"file": f["hunk"]["file"], "line": f["hunk"]["line"],
         "severity": f.get("severity"), "is_real": f.get("is_real"),
         "category": f.get("category"), "confidence": f.get("confidence"),
         "reported": f in reported}
        for f in findings if not f.get("parse_error")]
    meta = {"repo": os.path.basename(args.repo), "mode": mode, "head": head,
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
