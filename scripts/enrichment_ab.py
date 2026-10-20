#!/usr/bin/env python3
"""On/off A/B for ast_context enrichment, with a vacuity guard.

    enrichment_ab.py --repo DIR --range A..B --sample NAME --expect ts-ast
        [--golden G.tsv | --negative-golden N.tsv] [--repeats 3] [--outdir D]

Runs the reviewer on the same range with enrichment on and with
--no-enrichment, K repeats each, labels `exp:enrich:{on,off}:<sample>:r<k>`,
always with --out, ledger isolated under --outdir. (Real model calls and
real cost: run it deliberately, a handful of ranges at a time.)

    enrichment_ab.py --combine SAMPLE1.json [SAMPLE2.json ...]

VACUITY GUARD. The 2026-10-02 enrichment A/B compared two unenriched arms.
After every on-arm run this aborts (exit 2) unless the run-level
`enrichment` stamp contains --expect, the wheels needed for it are
available, the run did not fail open, and every golden file has at least
one unit stamped with --expect (a file with none never engaged, e.g. a
parse failure). Partial enrichment is NOT an abort: the over-cap context
drop legitimately turns some units to "none", so the per-file enriched
share is reported as `golden_file_enriched_share` (mean over repeats).

COUNTS. Reported findings are the ledger `judged` entries with
is_real >= REFLEX_GATE (the tool's constant, 0.80), not the `--out`
`findings` list, which is capped at 5 and saturates on large goldens.
False positives are reported - true positives (true positives still come
from golden_eval); on a clean sample every reported finding is one.

`decide` encodes the pre-registered rules: precision first (the on-arm may
not surface more findings than the off-arm on a clean sample in any
repeat), recall only counts as signal if on beats off by >= 2 true
positives in every repeat, and a systematic is_real drop on identical
units (paired by file:line:line_end) is a kill even if both pass.

`combine_verdicts` merges the per-sample results (the JSON this prints,
which carries `golden`): any KILL kills; SIGNAL only if every golden
sample is SIGNAL and none KILL; otherwise NO-DETECTABLE-EFFECT. Clean
samples can only veto (KILL), never be required to signal. `--combine
FILE...` reads those JSON outputs and prints the combined verdict.
"""

import argparse
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = [sys.executable, os.path.join(REPO_ROOT, "system_one_reviewer.py")]


_GATE: float | None = None


def reflex_gate() -> float:
    """REFLEX_GATE from the tool module (0.80), loaded lazily and once."""
    global _GATE
    if _GATE is None:
        spec = importlib.util.spec_from_file_location(
            "system_one_reviewer", TOOL[1])
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _GATE = float(mod.REFLEX_GATE)
    return _GATE


def reported_count(judged: list[dict]) -> int:
    """Judged units crossing the reflex gate: what a reader would be shown."""
    gate = reflex_gate()
    return sum(1 for j in judged
               if j.get("is_real") is not None and j["is_real"] >= gate)


def label_for(arm: str, sample: str, k: int) -> str:
    return f"exp:enrich:{arm}:{sample}:r{k}"


def run_one(args: argparse.Namespace, arm: str, k: int) -> dict:
    label = label_for(arm, args.sample, k)
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
    # a fail-open run (provider outage) still carries its enrichment stamp
    # but reports zero findings, which decide() would score as a real result
    if meta.get("fail_open") or meta.get("status") == "fail-open":
        return f"{arm}-arm failed open: {meta.get('fail_reason')!r}"
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


def unit_key(j: dict) -> str:
    return f"{j['file']}:{j['line']}:{j.get('line_end')}"


def paired_is_real_deltas(on: list[dict], off: list[dict]) -> dict[str, float]:
    """is_real(on) - is_real(off) per identical unit, keyed file:line:end."""
    off_by = {unit_key(j): j.get("is_real") for j in off}
    return {unit_key(j): j["is_real"] - off_by[unit_key(j)] for j in on
            if j.get("is_real") is not None
            and off_by.get(unit_key(j)) is not None}


def golden_files(path: str) -> set[str]:
    out: set[str] = set()
    with open(path) as f:
        for ln in f:
            if ln.strip() and not ln.startswith("#"):
                out.add(ln.split("\t")[0])
    return out


def golden_file_shares(judged: list[dict], files: set[str],
                       expect: str) -> dict[str, float]:
    """Per golden file, the share of its judged units stamped `expect`
    (0.0 when the file was not judged at all)."""
    shares: dict[str, float] = {}
    for fpath in sorted(files):
        units = [j for j in judged if j.get("file") == fpath]
        shares[fpath] = (sum(j.get("enrichment") == expect for j in units)
                         / len(units)) if units else 0.0
    return shares


def guard_files(judged: list[dict], files: set[str], expect: str) -> str | None:
    """The run-level stamp reads `ts-ast` as soon as ANY unit is enriched, so
    a golden file that failed to parse would run unenriched in both arms
    and the A/B would report "no effect". Abort when a golden file has no
    unit stamped with the expected value. Some-but-not-all is fine (the
    over-cap context drop); see golden_file_shares for the reported share."""
    for fpath in sorted(files):
        units = [j for j in judged if j.get("file") == fpath]
        if not units:
            return f"golden file {fpath} was not judged"
        if not any(j.get("enrichment") == expect for j in units):
            return (f"golden file {fpath}: 0/{len(units)} unit(s) stamped "
                    f"{expect!r} (parse error or never engaged?)")
    return None


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
    positives plus the paired is_real deltas ({unit: delta}). `clean` marks a sample with
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
    # repeats of one unit are not independent: average each unit's delta
    # across repeats, then sign-test the per-unit means
    per_unit: dict[str, list[float]] = {}
    for r in rows:
        for key, d in r["deltas"].items():
            per_unit.setdefault(key, []).append(d)
    deltas = [sum(v) / len(v) for v in per_unit.values()]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    nonzero = sum(1 for d in deltas if d != 0)
    # n < 6 non-zero pairs can never reach p < 0.05, so the softening kill
    # is untestable on a sample that small; say so instead of implying it
    underpowered = nonzero < 6
    softened = mean_delta < 0 and sign_test_p(deltas) < 0.05
    if not precision_ok or softened:
        verdict = "KILL"
    elif recall_signal:
        verdict = "SIGNAL"
    else:
        verdict = "NO-DETECTABLE-EFFECT"
    return {"verdict": verdict, "precision_ok": precision_ok,
            "recall_signal": recall_signal, "mean_is_real_delta": mean_delta,
            "sign_test_p": sign_test_p(deltas), "n_paired_units": len(deltas),
            "softening_test_underpowered": underpowered}


def combine_verdicts(results: list[dict]) -> str:
    """Spec rule over per-sample outputs (each has `verdict` and `golden`)."""
    verdicts = [r["verdict"] for r in results]
    if "KILL" in verdicts:
        return "KILL"
    golden = [r["verdict"] for r in results if r["golden"]]
    if golden and all(v == "SIGNAL" for v in golden):
        return "SIGNAL"
    return "NO-DETECTABLE-EFFECT"


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--combine":
        results = []
        for path in argv[1:]:
            with open(path) as f:
                results.append(json.load(f))
        print(json.dumps({"combined_verdict": combine_verdicts(results),
                          "samples": [r.get("sample") for r in results]},
                         indent=2))
        return 0
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
    clean = args.clean or bool(args.negative_golden and not args.golden)
    if not (clean or args.golden):
        ap.error("give --golden (a sample with known defects) or --clean / "
                 "--negative-golden (a clean sample); otherwise every "
                 "finding would be scored as a false positive")
    os.makedirs(args.outdir, exist_ok=True)
    runs: dict[str, list[Any]] = {"on": [], "off": []}
    shares: list[dict[str, float]] = []
    for k in range(1, args.repeats + 1):
        for arm in ("on", "off"):
            res = run_one(args, arm, k)
            bad = guard(res, arm, args.expect)
            if not bad and not clean and res.get("golden_eval") is None:
                bad = "no golden_eval in the result"
            if not bad and arm == "on" and args.golden:
                judged = read_ledger(os.path.join(
                    args.outdir, "metrics.jsonl")).get(
                        label_for(arm, args.sample, k), [])
                gfiles = golden_files(args.golden)
                bad = guard_files(judged, gfiles, args.expect)
                if not bad:
                    shares.append(golden_file_shares(judged, gfiles, args.expect))
            if bad:
                print(f"enrichment_ab: ABORT, vacuous {arm}-arm r{k}: {bad}",
                      file=sys.stderr)
                return 2
            runs[arm].append(res)
    ledger = read_ledger(os.path.join(args.outdir, "metrics.jsonl"))
    for k in range(1, args.repeats + 1):
        for arm in ("on", "off"):
            if label_for(arm, args.sample, k) not in ledger:
                print(f"enrichment_ab: ABORT, no ledger record for "
                      f"{label_for(arm, args.sample, k)}", file=sys.stderr)
                return 2
    rows = []
    for k, (on, off) in enumerate(zip(runs["on"], runs["off"], strict=True), 1):
        tp = lambda r: (r.get("golden_eval") or {}).get("true_positives", 0)  # noqa: E731
        rows.append({
            "on_reported": reported_count(ledger[label_for("on", args.sample, k)]),
            "off_reported": reported_count(ledger[label_for("off", args.sample, k)]),
            "on_tp": tp(on), "off_tp": tp(off),
            "deltas": paired_is_real_deltas(
                ledger.get(label_for("on", args.sample, k), []),
                ledger.get(label_for("off", args.sample, k), []))})
    share = {f: sum(s[f] for s in shares) / len(shares)
             for f in sorted(shares[0])} if shares else {}
    print(json.dumps({"sample": args.sample, "golden": not clean, "repeats": rows,
                      "golden_file_enriched_share": share,
                      **decide(rows, clean=clean)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
