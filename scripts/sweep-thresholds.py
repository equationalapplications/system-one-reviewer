#!/usr/bin/env python3
"""E5: threshold sweep over already-logged metrics runs.

Reads metrics.jsonl, selects runs by label prefix, gates them on the
committed expected fixture SHAs and packaging_version=v03b, replays each
run's `judged` array through jev-review's own `compose` at every threshold
(no logic duplication), combines runs per threshold by MINIMUM F1 (the
worst-run figure), picks the candidate by argmax with a documented tie rule
(odd tie -> middle; even tie -> lower middle), and evaluates the change
rule: candidate must beat 0.50 in EVERY positive run by >= 0.20 F1 AND not
increase FPs on ANY negative run vs the shipped threshold.

Providers (E8): runs are only comparable within one (provider, model)
group; mixed providers among the selected runs is a hard error.

Usage:
  sweep-thresholds.py --metrics FILE --label PREFIX --golden POS.tsv \
      --negative-golden NEG.tsv --shas FILE [--packaging-version v03b]

--shas file format: lines `positive=<full40sha>` / `negative=<full40sha>`
(the same constants as examples/fixture-shas.txt).
"""

import argparse
import json
import sys

POSITIVE = "positive"
NEGATIVE = "negative"
SHIPPED_THRESHOLD = 0.50
MARGIN_FLOOR = 0.20

# Versions whose judged ledger entries carry rubric/references_remaining
# (first: v03b, Opus r2 B1). rewrap() dies on a run from one of these
# versions whose entries lack `rubric`. Bump PACKAGING_VERSION? Add the
# new tag here if it still carries the fields (Opus r5 m5).
RUBRIC_VERSIONS = {"v03b"}

# 0.30 + 0.05*k, k = 0..8 (top of grid: 0.70; 0.75+ excluded by the plateau rule).
GRID = [round(0.30 + 0.05 * k, 2) for k in range(9)]


def die(msg):
    raise SystemExit(f"sweep: {msg}")


def load_tool():
    """Load system_one_reviewer.py the same way the test suite does (spec loader)."""
    import importlib.util
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "system_one_reviewer.py")
    spec = importlib.util.spec_from_file_location("jev-review-sweep", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- selection + gates ----------

def threshold_grid():
    return list(GRID)


def gate_run(rec, expected, packaging_version="v03b"):
    """Reject stale, hand-edited, fail-open, or incomplete runs loudly.

    r12 MINOR 2: the verdict is checked too — `n_analyzed` counts
    post-truncation clusters, so a `--max-hunks`-truncated run passed the
    judged==n_analyzed check while its verdict said "(incomplete review)".
    """
    if not isinstance(rec.get("judged"), list):
        die(f"run {rec.get('label')!r}: no judged array (pre-v0.1 record — "
            "re-run with the current tool)")
    # M1 (r3): fail-open and incomplete runs must not enter the sweep.
    # A fail-open run (model unavailable) logs judged: [] and would read as
    # zero FPs (negative) / zero TPs (positive) — valid-looking garbage.
    if rec.get("fail_open"):
        die(f"run {rec.get('label')!r}: fail_open=true (model unavailable "
            "during the run) — re-run")
    n_analyzed = rec.get("n_analyzed")
    if isinstance(n_analyzed, int) and len(rec["judged"]) != n_analyzed:
        die(f"run {rec.get('label')!r}: incomplete — judged has "
            f"{len(rec['judged'])} entries but n_analyzed={n_analyzed} "
            "(clusters dropped: parse errors or transient judge failures) "
            "— re-run")
    # r12 MINOR 2: n_analyzed counts post-truncation clusters, so a
    # --max-hunks-truncated run passes the check above. The verdict is the
    # authority on completeness.
    verdict = rec.get("verdict") or ""
    if "(incomplete" in verdict:
        die(f"run {rec.get('label')!r}: incomplete review ({verdict!r}) "
            "— re-run without truncation")
    if rec.get("packaging_version") != packaging_version:
        die(f"run {rec.get('label')!r}: packaging_version "
            f"{rec.get('packaging_version')!r} != {packaging_version!r} "
            "(stale or pre-E2 run)")
    head = rec.get("fixture_head") or ""
    if not head:
        die(f"run {rec.get('label')!r}: no fixture_head logged")
    if head != expected:
        die(f"run {rec.get('label')!r}: fixture_head does not match the "
            "committed expected SHA — rebuild the fixture and re-run")


def check_single_provider_group(recs):
    """One (provider, model) per sweep; mixed providers = hard error (E8)."""
    groups = {(r.get("provider"), r.get("model")) for r in recs}
    if len(groups) != 1:
        detail = ", ".join(sorted(f"provider={p!r} model={m!r}" for p, m in groups))
        die(f"mixed providers among selected runs — sweep groups by "
            f"(provider, model): {detail}")
    return groups.pop()


def select_runs(recs, expected, label_prefix, packaging_version="v03b"):
    sel = [r for r in recs if str(r.get("label", "")).startswith(label_prefix)]
    if not sel:
        die(f"no runs with label prefix {label_prefix!r}")
    pos, neg = [], []
    for r in sel:
        try:
            gate_run(r, expected.get(r.get("fixture"), ""), packaging_version)
        except SystemExit as e:
            # Reject = excluded from the sweep, loudly (E5: a stale or
            # hand-edited fixture fails loudly instead of silently
            # collapsing recall); the >= 3-per-fixture bar still applies.
            print(f"sweep: skipping {e}", file=sys.stderr)
            continue
        if r.get("fixture") == POSITIVE:
            pos.append(r)
        elif r.get("fixture") == NEGATIVE:
            neg.append(r)
    if len(pos) < 3 or len(neg) < 3:
        die(f"need >= 3 runs per fixture (found {len(pos)} positive / "
            f"{len(neg)} negative) — make fresh runs first")
    # m3 (r2): the mixed-provider check runs AFTER the stale-run gate, so a
    # stale run with a different provider is skipped, not fatal.
    # m4 (r11): select_runs returns the (provider, model) of the group so
    # main doesn't have to run check_single_provider_group a second time.
    provider, model = check_single_provider_group(pos + neg)
    return pos, neg, provider, model


# ---------- replay through compose ----------

def rewrap(j, run_version=None):
    """Flat judged entry -> the `f['hunk'][...]` shape compose consumes.

    rubric/references_remaining ride through; older records (no rubric
    key) replay as code-change — correct, because pre-v03b runs never
    sent deletion questions. The RUN's packaging_version decides that:
    judged entries never carry it (Opus r4 M1 — the entry-level check
    previously here could never fire). Callers pass the run's version;
    any rubric-era run (RUBRIC_VERSIONS) whose judged entries lack
    `rubric` was written by a broken build and dies loudly instead of
    replaying wrong logic. Future versions: add to RUBRIC_VERSIONS when
    they carry the rubric fields, so the gate survives version bumps
    (Opus r5 m5)."""
    if run_version in RUBRIC_VERSIONS and "rubric" not in j:
        die(f"{run_version} run record entry {j.get('file')} has no "
            "rubric — ledger written by a broken build; re-run")
    return {"hunk": {"file": j["file"], "line": j["line"]},
            "is_real": j["is_real"], "severity": j["severity"],
            "category": j.get("category"), "parse_error": None,
            "rubric": j.get("rubric", "code-change"),
            "references_remaining": j.get("references_remaining")}


def replay(jr, run, t):
    """Reported findings for this run at threshold t, via compose itself."""
    version = run.get("packaging_version")
    reported, _, _ = jr.compose(
        [rewrap(j, run_version=version) for j in run["judged"]], [], None,
        threshold=t)
    return reported


def negative_fp(jr, run, t, benign_files=frozenset()):
    """FP census at threshold t on a negative fixture, via the tool's own
    eval_negative: blocker_major + other_fp (minor style notes don't count;
    E5 formula). `benign_files` names files in the negative golden that the
    tool's deterministic triage MUST skip (docs/lockfile patterns) — a
    reported finding on one of them is triage leakage and dies loudly.
    Files the golden names that triage keeps (source files) are judged on
    purpose and are NOT leakage."""
    reported = replay(jr, run, t)
    for f in reported:
        if f["hunk"]["file"] in benign_files:
            die(f"run {run.get('label')!r}: reported a finding on "
                f"{f['hunk']['file']} which the negative golden marks "
                "must-skip (triage leakage)")
    counts = jr.eval_negative(reported)
    return counts["blocker_major"] + counts["other_fp"]


def benign_files_from_negative_golden(path, jr=None):
    """Files named in the negative golden TSV that deterministic triage
    must skip (docs extensions / skip patterns). Golden lines for kept
    source files are benign-content checks, not must-skip markers."""
    if not path:
        return frozenset()
    files = set()
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line and not line.startswith("#"):
                files.add(line.split("\t")[0])
    if jr is None:
        return frozenset(files)
    return frozenset(f for f in files
                     if jr.SKIP_PATTERNS.search(f) or jr.DOC_EXT.search(f))


# ---------- golden eval + curve ----------
# (r9 m5: `_eval`/`_fp_pos` were folded into sweep()'s single
# replay+matching per (run, t); `_load_golden_lines` was dead and removed.)

def _fp_pos_from_eval(jr, reported, e):
    """FP_pos from an already-computed eval_against_golden result (M5, r9:
    no duplicate replay/matching work; TP and FP_pos share one matching)."""
    matched = set(e["matched_reported"])
    return sum(1 for i, f in enumerate(reported)
               if i not in matched
               and not (jr.sev_level(f.get("severity")) == 1
                        and f.get("category") == "style"))


def sweep(jr, pos_runs, neg_runs, golden_path, neg_golden_path=None):
    benign = benign_files_from_negative_golden(neg_golden_path, jr)
    rows = []
    for t in threshold_grid():
        # m5 (r9): one replay + matching per (run, t), shared by the F1
        # curve and the FP_pos census.
        evals, reported_each, fp_pos_each = [], [], []
        for run in pos_runs:
            reported = replay(jr, run, t)
            e = jr.eval_against_golden(reported, golden_path)
            evals.append(e)
            reported_each.append(reported)
            fp_pos_each.append(_fp_pos_from_eval(jr, reported, e))
        # spec R5 / plan Task 7: the published per-run figure is
        # precision_i = TP_i / (TP_i + FP_pos_i + FP_neg_mean), folded into
        # an F1 against recall_i — negative FPs enter the curve.
        # FP_neg per negative run, then averaged (E5).
        fp_neg_each = [negative_fp(jr, r, t, benign) for r in neg_runs]
        f1s = []
        for e, fp_pos in zip(evals, fp_pos_each):
            tp = e["true_positives"]
            golden_n = e["golden_issues"]
            recall = tp / golden_n if golden_n else 0.0
            denom = tp + fp_pos + (sum(fp_neg_each) / len(fp_neg_each))
            precision = tp / denom if denom > 0 else (1.0 if recall == 1.0 else 0.0)
            f1s.append(2 * precision * recall / (precision + recall)
                       if precision + recall > 0 else 0.0)
        tp_lo = min(e["true_positives"] for e in evals)
        tp_hi = max(e["true_positives"] for e in evals)
        fp_neg_mean = sum(fp_neg_each) / len(fp_neg_each)
        rows.append({"t": t,
                     "tp": (tp_lo, tp_hi), "tp_range": f"{tp_lo}-{tp_hi}",
                     "fp_pos_each": fp_pos_each,
                     "fp_pos_range": f"{min(fp_pos_each)}-{max(fp_pos_each)}",
                     "fp_neg_each": fp_neg_each, "fp_neg_mean": fp_neg_mean,
                     "f1s": f1s,
                     "f1_range": f"{min(f1s):.2f}-{max(f1s):.2f}",
                     "min_f1": min(f1s)})
    base = next(r for r in rows if r["t"] == SHIPPED_THRESHOLD)
    for r in rows:
        r["d_fp_neg_vs_050"] = r["fp_neg_mean"] - base["fp_neg_mean"]

    best = max(r["min_f1"] for r in rows)
    tied = [r["t"] for r in rows if r["min_f1"] == best]
    m = len(tied)
    candidate = tied[m // 2] if m % 2 else tied[(m - 1) // 2]

    cand = next(r for r in rows if r["t"] == candidate)
    base_f1s = base["f1s"]
    margin_ok = (candidate != SHIPPED_THRESHOLD
                 and len(base_f1s) == len(cand["f1s"])
                 and all(c - b >= MARGIN_FLOOR for c, b in zip(cand["f1s"], base_f1s)))
    # change rule 2 per spec: Delta-FP-neg <= 0 per run (a candidate that
    # REDUCES negative FPs must not be blocked)
    neg_fp_ok = all(c <= b for c, b in zip(cand["fp_neg_each"], base["fp_neg_each"]))

    return {"rows": rows, "candidate": candidate, "tied": tied,
            "rule_margin_ok": margin_ok, "rule_neg_fp_ok": neg_fp_ok,
            "shipped": SHIPPED_THRESHOLD, "change": margin_ok and neg_fp_ok}


# ---------- reporting ----------

def render(res, provider, model):
    prov = provider + (f"/{model}" if model else "")
    lines = [f"threshold sweep (provider/model: {prov})",
             "t | TP | FP_pos | FP_neg (each / mean) | dFP_neg vs 0.50 | "
             "per-run F1 | min F1"]
    for r in res["rows"]:
        lines.append(
            f"{r['t']:.2f} | {r['tp_range']} | {r['fp_pos_range']} | "
            f"{r['fp_neg_each']} / {r['fp_neg_mean']:.2f} | "
            f"{r['d_fp_neg_vs_050']:+.2f} | {r['f1_range']} | {r['min_f1']:.2f}")
    cand = res["candidate"]
    lines.append(f"candidate: {cand:.2f} (tied: "
                 f"{', '.join(f'{t:.2f}' for t in res['tied'])})")
    lines.append(f"rule 1 (>= {MARGIN_FLOOR:.2f} F1 over 0.50 in EVERY "
                 f"positive run): {'PASS' if res['rule_margin_ok'] else 'FAIL'}")
    lines.append(f"rule 2 (no FP increase on ANY negative run): "
                 f"{'PASS' if res['rule_neg_fp_ok'] else 'FAIL'}")
    verdict = "CHANGE" if res["change"] else "KEEP 0.50"
    lines.append(f"decision: {verdict}")
    return "\n".join(lines)


def load_shas(path):
    expected = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                die(f"{path}: expected `name=<sha>` lines")
            name, _, sha = line.partition("=")
            if len(sha) != 40:
                die(f"{path}: {name}=... is not a full 40-char sha")
            expected[name.strip()] = sha
    if POSITIVE not in expected or NEGATIVE not in expected:
        die(f"{path}: needs positive= and negative= lines")
    return expected


def main(argv=None):
    ap = argparse.ArgumentParser(description="E5 threshold sweep")
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--label", required=True, help="run label prefix")
    ap.add_argument("--golden", required=True, help="positive golden TSV")
    ap.add_argument("--negative-golden", required=True,
                    help="negative golden TSV — drives the must-skip "
                         "triage-leakage guard; required so the guard "
                         "cannot silently turn off (r3 m2)")
    ap.add_argument("--shas", required=True, help="expected fixture SHA file")
    ap.add_argument("--packaging-version", default="v03b")
    args = ap.parse_args(argv)

    expected = load_shas(args.shas)
    with open(args.metrics) as f:
        recs = [json.loads(line) for line in f if line.strip()]
    pos, neg, provider, model = select_runs(recs, expected, args.label,
                                            args.packaging_version)
    jr = load_tool()
    res = sweep(jr, pos, neg, args.golden, args.negative_golden)
    print(render(res, provider, model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
