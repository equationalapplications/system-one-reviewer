#!/usr/bin/env python3
"""On/off A/B for ast_context enrichment, with a vacuity guard.

    enrichment_ab.py --repo DIR --range A..B --sample NAME --expect ts-ast
        [--golden G.tsv | --negative-golden N.tsv] [--repeats 3] [--outdir D]

Runs the reviewer on the same range with enrichment on and with
--no-enrichment, K repeats each, labels `exp:enrich:{on,off}:<sample>:r<k>`,
always with --out, ledger isolated under --outdir. (Real model calls and
real cost: run it deliberately, a handful of ranges at a time.)

VACUITY GUARD. The 2026-10-02 enrichment A/B compared two unenriched arms.
After every on-arm run this aborts (exit 2) unless the run-level
`enrichment` stamp contains --expect and the wheels needed for it are
available, so an arm that never engaged can never be scored.

`decide` encodes the pre-registered rules: precision first (the on-arm may
not surface more findings than the off-arm on a clean sample in any
repeat), recall only counts as signal if on beats off by >= 2 true
positives in every repeat, and a systematic is_real drop on identical
units (paired by file:line:line_end) is a kill even if both pass.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [sys.executable, os.path.join(REPO_ROOT, "system_one_reviewer.py")]


def run_one(args: argparse.Namespace, arm: str, k: int) -> dict:
    label = f"exp:enrich:{arm}:{args.sample}:r{k}"
    out = os.path.join(args.outdir, f"{arm}-{args.sample}-r{k}.json")
    cmd = [*TOOL, "--repo", args.repo, "--range", args.range, "--json",
           "--label", label, "--out", out]
    if args.golden:
        cmd += ["--golden", args.golden]
    if args.negative_golden:
        cmd += ["--negative-golden", args.negative_golden]
    if arm == "off":
        cmd.append("--no-enrichment")
    env = dict(os.environ,
               JEV_REVIEW_METRICS=os.path.join(args.outdir, "metrics.jsonl"))
    if os.path.exists(out):
        os.remove(out)  # never score a stale file if this run dies early
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if not os.path.exists(out):
        sys.exit(f"enrichment_ab: {label} produced no --out file "
                 f"(rc={p.returncode}): {p.stderr[-400:]}")
    with open(out) as f:
        return json.load(f)


def guard(result: dict, arm: str, expect: str) -> str | None:
    """Reason the run must not be scored, or None when it is valid."""
    meta = result.get("meta", {})
    stamp = meta.get("enrichment", "none")
    if arm == "off":
        return None if stamp == "none" else f"off-arm stamped {stamp!r}"
    if expect not in stamp.split("+"):
        return f"on-arm stamped {stamp!r}, expected {expect!r}"
    if expect == "ts-ast" and not meta.get("wheels", {}).get("ts", {}).get(
            "available"):
        return "TS wheels unavailable (interpreter gotcha in AGENTS.md)"
    return None


def read_ledger(path: str) -> dict[str, list[dict]]:
    by_label: dict[str, list[dict]] = {}
    if os.path.exists(path):
        with open(path) as f:
            for ln in f:
                rec = json.loads(ln)
                by_label[rec.get("label", "")] = rec.get("judged", [])
    return by_label


def paired_is_real_deltas(on: list[dict], off: list[dict]) -> list[float]:
    key = lambda j: (j["file"], j["line"], j.get("line_end"))  # noqa: E731
    off_by = {key(j): j.get("is_real") for j in off}
    return [j["is_real"] - off_by[key(j)] for j in on
            if j.get("is_real") is not None
            and off_by.get(key(j)) is not None]


def sign_test_p(deltas: list[float]) -> float:
    """Two-sided exact sign test p-value over non-zero deltas."""
    nz = [d for d in deltas if d != 0]
    n, pos = len(nz), sum(d > 0 for d in nz)
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(pos, n - pos) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def decide(rows: list[dict], clean: bool = False) -> dict:
    """rows: one dict per repeat with on/off reported counts and true
    positives plus the paired is_real deltas. `clean` marks a sample with
    no known defects, where ANY surfaced finding is a false positive; on a
    golden sample the on-arm may surface more findings (true positives) and
    only its false positives (reported - tp) are compared. "Any NEW false
    positive class is a kill" is a judgment on the adjudicated findings and
    is checked by hand, not here."""
    def fps(r: dict, arm: str) -> int:
        return r[f"{arm}_reported"] - (0 if clean else r[f"{arm}_tp"])
    precision_ok = all(fps(r, "on") <= fps(r, "off") for r in rows)
    recall_signal = bool(rows) and all(
        r["on_tp"] >= r["off_tp"] + 2 for r in rows)
    deltas = [d for r in rows for d in r["deltas"]]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    softened = mean_delta < 0 and sign_test_p(deltas) < 0.05
    if not precision_ok or softened:
        verdict = "KILL"
    elif recall_signal:
        verdict = "SIGNAL"
    else:
        verdict = "NO-DETECTABLE-EFFECT"
    return {"verdict": verdict, "precision_ok": precision_ok,
            "recall_signal": recall_signal, "mean_is_real_delta": mean_delta,
            "sign_test_p": sign_test_p(deltas), "n_paired_units": len(deltas)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--range", required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--expect", required=True, choices=["ast", "ts-ast"],
                    help="stamp the on-arm must carry")
    ap.add_argument("--golden")
    ap.add_argument("--negative-golden", dest="negative_golden")
    ap.add_argument("--clean", action="store_true",
                    help="sample has no known defects (negative head/fixture)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--outdir", help="default: corpus/work/enrich-ab/<sample>-<epoch>, "
                    "fresh per invocation so the append-only ledger and --out "
                    "files can never be a previous run's")
    args = ap.parse_args(argv)
    if not args.outdir:
        args.outdir = os.path.join(REPO_ROOT, "corpus", "work", "enrich-ab",
                                   f"{args.sample}-{int(time.time())}")
    if args.repeats < 1:
        ap.error("--repeats must be >= 1")
    os.makedirs(args.outdir, exist_ok=True)
    runs: dict[str, list[Any]] = {"on": [], "off": []}
    for k in range(1, args.repeats + 1):
        for arm in ("on", "off"):
            res = run_one(args, arm, k)
            bad = guard(res, arm, args.expect)
            if bad:
                print(f"enrichment_ab: ABORT, vacuous {arm}-arm r{k}: {bad}",
                      file=sys.stderr)
                return 2
            runs[arm].append(res)
    ledger = read_ledger(os.path.join(args.outdir, "metrics.jsonl"))
    rows = []
    for k, (on, off) in enumerate(zip(runs["on"], runs["off"], strict=True), 1):
        tp = lambda r: (r.get("golden_eval") or {}).get("true_positives", 0)  # noqa: E731
        rows.append({
            "on_reported": len(on["findings"]), "off_reported": len(off["findings"]),
            "on_tp": tp(on), "off_tp": tp(off),
            "deltas": paired_is_real_deltas(
                ledger.get(f"exp:enrich:on:{args.sample}:r{k}", []),
                ledger.get(f"exp:enrich:off:{args.sample}:r{k}", []))})
    print(json.dumps({"sample": args.sample, "repeats": rows,
                      **decide(rows, clean=args.clean)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
