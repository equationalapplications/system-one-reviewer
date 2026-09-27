#!/usr/bin/env python3
"""E5: threshold sweep over already-logged metrics runs.

Reads metrics.jsonl, selects runs by label prefix, gates them on the
committed expected fixture SHAs and packaging_version=v02, replays each
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
      --negative-golden NEG.tsv --shas FILE [--packaging-version v02]

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

# 0.30 + 0.05*k, k = 0..8; 0.75 excluded by the plateau rule (|t-0.80|<=0.05).
GRID = [round(0.30 + 0.05 * k, 2) for k in range(9) if abs(0.30 + 0.05 * k - 0.80) > 0.05 + 1e-9]


def die(msg):
    raise SystemExit(f"sweep: {msg}")


def load_tool():
    """Load jev-review.py the same way the test suite does (spec loader)."""
    import importlib.util
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "jev-review.py")
    spec = importlib.util.spec_from_file_location("jev-review-sweep", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- selection + gates ----------

def threshold_grid():
    return list(GRID)


def gate_run(rec, expected):
    if "judged" not in rec:
        die(f"run {rec.get('label')!r}: no judged array (run with --golden)")
    if rec.get("packaging_version") != "v02":
        die(f"run {rec.get('label')!r}: packaging_version "
            f"{rec.get('packaging_version')!r} != v02 (stale or pre-E2 run)")
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


def select_runs(recs, expected, label_prefix):
    sel = [r for r in recs if str(r.get("label", "")).startswith(label_prefix)]
    if not sel:
        die(f"no runs with label prefix {label_prefix!r}")
    check_single_provider_group(sel)
    pos, neg = [], []
    for r in sel:
        try:
            gate_run(r, expected.get(r.get("fixture"), ""))
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
    return pos, neg


# ---------- replay through compose ----------

def rewrap(j):
    """Flat judged entry -> the `f['hunk'][...]` shape compose consumes."""
    return {"hunk": {"file": j["file"], "line": j["line"]},
            "is_real": j["is_real"], "severity": j["severity"],
            "category": j.get("category"), "parse_error": None}


def replay(jr, run, t):
    """Reported findings for this run at threshold t, via compose itself."""
    reported, _, _ = jr.compose([rewrap(j) for j in run["judged"]], [], None,
                                threshold=t)
    return reported


def negative_fp(jr, run, t):
    """FP census at threshold t on a negative fixture, via the tool's own
    eval_negative: blocker_major + other_fp (minor style notes don't count;
    E5 formula)."""
    counts = jr.eval_negative(replay(jr, run, t))
    return counts["blocker_major"] + counts["other_fp"]


# ---------- golden eval + curve ----------

def _eval(jr, run, t, golden_path):
    return jr.eval_against_golden(replay(jr, run, t), golden_path)


def _f1(res):
    f1 = res["f1"]
    return 0.0 if f1 is None else f1


def sweep(jr, pos_runs, neg_runs, golden_path, neg_golden_path=None):
    rows = []
    for t in threshold_grid():
        evals = [_eval(jr, run, t, golden_path) for run in pos_runs]
        f1s = [_f1(e) for e in evals]
        # FP_pos: unmatched reported at this threshold; FP_neg: per negative
        # run, then averaged across the N runs (E5 formula).
        fp_neg_each = [negative_fp(jr, r, t) for r in neg_runs]
        fp_pos_lo = min(e["reported"] - e["true_positives"] for e in evals)
        fp_pos_hi = max(e["reported"] - e["true_positives"] for e in evals)
        tp_lo = min(e["true_positives"] for e in evals)
        tp_hi = max(e["true_positives"] for e in evals)
        fp_neg_mean = sum(fp_neg_each) / len(fp_neg_each)
        rows.append({"t": t,
                     "tp": (tp_lo, tp_hi), "tp_range": f"{tp_lo}-{tp_hi}",
                     "fp_pos_range": f"{fp_pos_lo}-{fp_pos_hi}",
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
    neg_fp_ok = cand["fp_neg_each"] == base["fp_neg_each"]

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
    for line in open(path):
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
    ap.add_argument("--negative-golden")
    ap.add_argument("--shas", required=True, help="expected fixture SHA file")
    ap.add_argument("--packaging-version", default="v02")
    args = ap.parse_args(argv)

    expected = load_shas(args.shas)
    recs = [json.loads(line) for line in open(args.metrics) if line.strip()]
    pos, neg = select_runs(recs, expected, args.label)
    provider, model = check_single_provider_group(pos + neg)
    jr = load_tool()
    res = sweep(jr, pos, neg, args.golden, args.negative_golden)
    print(render(res, provider, model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
