#!/usr/bin/env python3
"""On/off A/B for ast_context enrichment, with a vacuity guard.

    enrichment_ab.py --repo DIR --range A..B --sample NAME --expect ts-ast
        [--golden G.tsv | --negative-golden N.tsv] [--must-enrich FILE ...]
        [--repeats 3] [--outdir D]

Runs the reviewer on the same range with enrichment on and with
--no-enrichment, K repeats each, labels `exp:enrich:{on,off}:<sample>:r<k>`,
always with --out, ledger isolated under --outdir. (Real model calls and
real cost: run it deliberately, a handful of ranges at a time.)

    enrichment_ab.py --combine SAMPLE1.json [SAMPLE2.json ...]
        [--expect-samples NAME ...]

VACUITY GUARD. The 2026-10-02 enrichment A/B compared two unenriched arms.
After every on-arm run this aborts (exit 2) unless the run-level
`enrichment` stamp contains --expect, the wheels needed for it are
available, the run status is ok (no fail-open, no incomplete review: partial
coverage would confound enrichment), and every file listed in --golden, every
enrichable code file of --negative-golden (GONE rows and extensions the
--expect value does not cover are ignored) and every --must-enrich file has
at least one unit stamped with --expect (a file with none never engaged,
e.g. a parse failure). Partial enrichment is NOT an abort: the over-cap
context drop legitimately turns some units to "none", so the per-file
enriched share is reported as `golden_file_enriched_share` (mean over
repeats). Every golden row must also be reachable by a unit anchor (the
+-1 line match eval_against_golden uses), in both arms.

COUNTS. The tool caps `--out` `findings` and `golden_eval` at the top 5,
which saturates on large goldens. So the surfaced list is rebuilt, uncapped,
from the ledger `judged` entries by the tool's own compose() at REFLEX_GATE
(rubric threshold, severity >= 1), and scored with the tool's
eval_against_golden. False positives are surfaced - true positives; on a
clean sample (no golden) every surfaced finding is one. Test-file findings
are held, as in the tool; --include-test-findings is forwarded to both arms
and counts them.

`decide` encodes the pre-registered rules: precision first (false
positives POOLED over the repeats may exceed the off-arm's by at most
MARGIN; a per-repeat comparison killed identical arms about half the time
on Poisson noise), recall only counts as signal if on beats off by >= 2
true positives in every repeat, and a systematic is_real drop on identical
units (paired by file:line:line_end; per-unit mean over repeats, more
units worse than better, sign test p < 0.05) is a kill even if both pass.

`combine_verdicts` merges the per-sample results (the JSON this prints,
which carries `golden`): any KILL kills; SIGNAL only if every golden
sample is SIGNAL and none KILL; otherwise NO-DETECTABLE-EFFECT. Clean
samples can only veto (KILL), never be required to signal. `--combine
FILE...` reads those JSON outputs and prints the combined verdict;
`--expect-samples NAME...` downgrades SIGNAL to NO-DETECTABLE-EFFECT when a
named sample (e.g. one that aborted) has no result, and lists it as
`missing`.
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
# pooled false positives (on - off) tolerated before the precision rule kills
MARGIN = 1
ENRICHABLE_EXTS = {"ts-ast": ("ts", "tsx", "js", "jsx", "mjs", "cjs"),
                   "ast": ("py",)}


_TOOL_MOD: Any = None


def load_tool() -> Any:
    """The reviewer module, loaded lazily and once."""
    global _TOOL_MOD
    if _TOOL_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "system_one_reviewer", TOOL[1])
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _TOOL_MOD = mod
    return _TOOL_MOD


def surfaced(judged: list[dict], include_test: bool = False) -> list[dict]:
    """Findings the tool would surface from these ledger entries, uncapped:
    the tool's own compose() at REFLEX_GATE (rubric threshold and
    severity >= 1), so the harness never re-implements the rule. Test-class
    entries are held unless include_test, like the tool's default."""
    tool = load_tool()
    findings = [{"rubric": j.get("rubric", "code-change"),
                 "is_real": j.get("is_real"), "severity": j.get("severity"),
                 "reflex_class": j.get("reflex_class", "code"),
                 "hunk": {"file": j["file"], "line": j["line"]}}
                for j in judged]
    reported, _jitter, _ = tool.compose(findings, [], None,
                                        threshold=tool.REFLEX_GATE,
                                        hold_classes=() if include_test else ("test",))
    return list(reported)


def golden_tp(surfaced_findings: list[dict], golden: str | None) -> int:
    """True positives of the uncapped surfaced list; 0 without a golden."""
    if not golden:
        return 0
    return int(load_tool().eval_against_golden(
        surfaced_findings, golden)["true_positives"])


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
    if args.include_test_findings:
        cmd.append("--include-test-findings")
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
    status = meta.get("status", "ok")
    # a fail-open run (provider outage) still carries its enrichment stamp
    # but reports zero findings, which decide() would score as a real result
    if meta.get("fail_open") or meta.get("status") == "fail-open":
        return f"{arm}-arm failed open: {meta.get('fail_reason')!r}"
    if status != "ok":
        return f"{arm}-arm status {status!r}, not 'ok' (incomplete coverage)"
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


def _data_lines(path: str) -> list[tuple[int, list[str]]]:
    """(line number, tab-split columns) of every non-blank, non-comment line,
    stripped first like the tool's own golden readers."""
    out = []
    with open(path) as f:
        for n, ln in enumerate(f, 1):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                out.append((n, ln.split("\t")))
    return out


def golden_rows(path: str) -> list[tuple[str, int]]:
    """Positive golden rows (file<TAB>line<TAB>description)."""
    rows: list[tuple[str, int]] = []
    for n, parts in _data_lines(path):
        try:
            rows.append((parts[0], int(parts[1])))
        except (IndexError, ValueError):
            sys.exit(f"enrichment_ab: {path}:{n}: expected file<TAB>line, "
                     f"got {parts!r}")
    return rows


def negative_golden_files(path: str, expect: str) -> set[str]:
    """Files of a negative golden (file<TAB>verify-substring, `GONE` for a
    file that must not exist) that enrichment should engage: not GONE and an
    extension the `expect` cutter covers."""
    exts = ENRICHABLE_EXTS[expect]
    files = set()
    for _n, parts in _data_lines(path):
        ext = os.path.splitext(parts[0])[1].lower().lstrip(".")
        if (len(parts) < 2 or parts[1] != "GONE") and ext in exts:
            files.add(parts[0])
    return files


def guard_file_set(args: argparse.Namespace) -> set[str]:
    files = set(args.must_enrich or [])
    if args.golden:
        files |= {fpath for fpath, _ in golden_rows(args.golden)}
    if args.negative_golden:
        files |= negative_golden_files(args.negative_golden, args.expect)
    return files


def guard_rows(judged: list[dict], rows: list[tuple[str, int]]) -> str | None:
    """Every golden row must be reachable by a judged unit's ANCHOR line
    (`line` +-1, the match eval_against_golden uses). A row inside a unit's
    span but away from its anchor can never score a hit, so the reported
    unit would count as a false positive in both arms."""
    for fpath, line in rows:
        if not any(j.get("file") == fpath and abs(j["line"] - line) <= 1
                   for j in judged):
            return (f"golden row {fpath}:{line} is not reachable by any "
                    f"judged unit anchor (line +-1): fix the golden or the "
                    f"cutting")
    return None


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
    positives plus the paired is_real deltas ({unit: delta}). `clean` marks a
    sample with no known defects, where ANY surfaced finding is a false
    positive; on a golden sample the on-arm may surface more findings (true
    positives) and only its false positives (reported - tp) are compared.
    Precision is POOLED: total on-arm FPs may exceed total off-arm FPs by at
    most MARGIN. Softening needs a negative mean per-unit delta, strictly
    more worsened than improved units, and a sign test p < 0.05. "Any NEW
    false positive class is a kill" is a judgment on the adjudicated
    findings and is checked by hand, not here."""
    def fps(r: dict, arm: str) -> int:
        return r[f"{arm}_reported"] - (0 if clean else r[f"{arm}_tp"])
    precision_ok = (sum(fps(r, "on") for r in rows)
                    <= sum(fps(r, "off") for r in rows) + MARGIN)
    recall_signal = bool(rows) and all(
        r["on_tp"] >= r["off_tp"] + 2 for r in rows)
    # repeats of one unit are not independent: average each unit's delta
    # across repeats, then sign-test the per-unit means
    per_unit: dict[str, list[float]] = {}
    for r in rows:
        for key, d in r["deltas"].items():
            per_unit.setdefault(key, []).append(d)
    deltas = [round(sum(v) / len(v), 9) for v in per_unit.values()]
    mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
    nonzero = sum(1 for d in deltas if d != 0)
    worse = sum(d < 0 for d in deltas)
    better = sum(d > 0 for d in deltas)
    # n < 6 non-zero pairs can never reach p < 0.05, so the softening kill
    # is untestable on a sample that small; say so instead of implying it
    underpowered = nonzero < 6
    softened = mean_delta < 0 and worse > better and sign_test_p(deltas) < 0.05
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


def missing_samples(results: list[dict], expect: list[str]) -> list[str]:
    have = {r.get("sample") for r in results}
    return [name for name in expect if name not in have]


def combine_verdicts(results: list[dict],
                     expect_samples: list[str] | None = None) -> str:
    """Spec rule over per-sample outputs (each has `verdict` and `golden`).
    A named sample with no result (an aborted run) can veto but never let
    the combination signal."""
    verdicts = [r["verdict"] for r in results]
    if "KILL" in verdicts:
        return "KILL"
    if missing_samples(results, expect_samples or []):
        return "NO-DETECTABLE-EFFECT"
    golden = [r["verdict"] for r in results if r["golden"]]
    if golden and all(v == "SIGNAL" for v in golden):
        return "SIGNAL"
    return "NO-DETECTABLE-EFFECT"


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--combine":
        rest = argv[1:]
        expect: list[str] = []
        if "--expect-samples" in rest:
            at = rest.index("--expect-samples")
            rest, expect = rest[:at], rest[at + 1:]
        results = []
        for path in rest:
            with open(path) as f:
                results.append(json.load(f))
        print(json.dumps({"combined_verdict": combine_verdicts(results, expect),
                          "samples": [r.get("sample") for r in results],
                          "missing": missing_samples(results, expect)},
                         indent=2))
        return 0
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--range", required=True)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--expect", required=True, choices=["ast", "ts-ast"],
                    help="stamp the on-arm must carry")
    ap.add_argument("--include-test-findings", dest="include_test_findings",
                    action="store_true",
                    help="forwarded to both arms; test-file findings count as surfaced")
    ap.add_argument("--golden")
    ap.add_argument("--negative-golden", dest="negative_golden")
    ap.add_argument("--must-enrich", dest="must_enrich", nargs="+", metavar="FILE",
                    help="files that must have an enriched unit, in any mode")
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
    if args.clean and args.golden:
        ap.error("--clean and --golden conflict: a golden sample has known "
                 "defects, so its true positives would be scored as false "
                 "positives")
    clean = args.clean or bool(args.negative_golden and not args.golden)
    gfiles = guard_file_set(args)
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
            if not bad and (gfiles or args.golden):
                judged = read_ledger(os.path.join(
                    args.outdir, "metrics.jsonl")).get(
                        label_for(arm, args.sample, k), [])
                if args.golden:
                    bad = guard_rows(judged, golden_rows(args.golden))
                if not bad and arm == "on":
                    bad = guard_files(judged, gfiles, args.expect)
                    if not bad:
                        shares.append(
                            golden_file_shares(judged, gfiles, args.expect))
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
    tp_golden = None if clean else args.golden
    for k in range(1, args.repeats + 1):
        on_s = surfaced(ledger[label_for("on", args.sample, k)],
                      args.include_test_findings)
        off_s = surfaced(ledger[label_for("off", args.sample, k)],
                       args.include_test_findings)
        rows.append({
            "on_reported": len(on_s), "off_reported": len(off_s),
            "on_tp": golden_tp(on_s, tp_golden),
            "off_tp": golden_tp(off_s, tp_golden),
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
