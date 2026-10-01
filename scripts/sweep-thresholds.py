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
from typing import NoReturn

POSITIVE = "positive"
NEGATIVE = "negative"
SHIPPED_THRESHOLD = 0.50
MARGIN_FLOOR = 0.20
# The shipped deletion-rubric threshold in system_one_reviewer.py
# (DELETION_REAL_THRESHOLD; v0.3b made it provisional pending this sweep).
DELETION_SHIPPED = 0.70

# Versions whose judged ledger entries carry rubric/references_remaining
# (first: v03b, Opus r2 B1). rewrap() dies on a run from one of these
# versions whose entries lack `rubric`. Bump PACKAGING_VERSION? Add the
# new tag here if it still carries the fields (Opus r5 m5).
RUBRIC_VERSIONS = {"v03b"}

# 0.30 + 0.05*k, k = 0..8 (top of grid: 0.70; 0.75+ excluded by the plateau rule).
GRID = [round(0.30 + 0.05 * k, 2) for k in range(9)]


def die(msg) -> NoReturn:
    raise SystemExit(f"sweep: {msg}")


def load_tool():
    """Load system_one_reviewer.py the same way the test suite does (spec loader)."""
    import importlib.util
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "system_one_reviewer.py")
    spec = importlib.util.spec_from_file_location("jev-review-sweep", path)
    if spec is None or spec.loader is None:
        die(f"cannot load {path}")
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

    Step 0′ (hunk-size investigation, 2026-10-01): records carrying
    `base_verdict` are gated on STRUCTURED counts, not the suffixed
    string — `n_dropped > 0` or `n_unjudged > 0` still rejects, while
    `n_size_skipped_code` alone is ADMITTED (a size-skipped run is a
    candidate for the windowing fix, not a broken run). A ledger with
    `base_verdict` but missing any count is malformed → die (never
    default a missing count to 0 — that would re-open the r12 hole).
    Legacy ledgers (no `base_verdict`) fall back to the suffix check.
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
    if "base_verdict" in rec:
        # Step 0′ structured gate: counts are the authority.
        missing = [k for k in ("n_dropped", "n_unjudged",
                               "n_size_skipped_code") if k not in rec]
        if missing:
            die(f"run {rec.get('label')!r}: malformed — has base_verdict "
                f"but missing counts {missing} (re-run with the current "
                "tool)")
        if rec["n_dropped"] > 0 or rec["n_unjudged"] > 0:
            die(f"run {rec.get('label')!r}: incomplete review "
                f"(n_dropped={rec['n_dropped']}, "
                f"n_unjudged={rec['n_unjudged']}) — re-run without "
                "truncation")
        # n_size_skipped_code alone: ADMITTED (Step 0′ semantics).
    else:
        # Legacy fallback: the suffixed string is the only signal.
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


def replay(jr, run, t, deletion_threshold=None):
    """Reported findings for this run at threshold t, via compose itself.

    deletion_threshold=None keeps compose's shipped default (fixture
    sweeps never move the deletion knob); field mode passes the candidate
    explicitly.
    """
    version = run.get("packaging_version")
    kwargs = {"threshold": t}
    if deletion_threshold is not None:
        kwargs["deletion_threshold"] = deletion_threshold
    reported, _, _ = jr.compose(
        [rewrap(j, run_version=version) for j in run["judged"]], [], None,
        **kwargs)
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
        for e, fp_pos in zip(evals, fp_pos_each, strict=True):
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
                 and all(c - b >= MARGIN_FLOOR for c, b in zip(cand["f1s"], base_f1s, strict=True)))
    # change rule 2 per spec: Delta-FP-neg <= 0 per run (a candidate that
    # REDUCES negative FPs must not be blocked)
    neg_fp_ok = all(c <= b for c, b in zip(cand["fp_neg_each"], base["fp_neg_each"],
                                              strict=True))

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


def load_field_goldens(path):
    """CJ field goldens: lines `pr<TAB>full40sha<TAB>expected_issues`.

    expected_issues > 0 needs positive-style golden rows (file/line TSV) to
    score recall against — not supported yet; die loudly instead of
    silently treating a positive PR as a clean-FP run (the #46 v0.2 FN is
    exactly the case that would corrupt).
    """
    goldens: dict[int, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                die(f"{path}: expected `pr<TAB>sha<TAB>expected` lines: {line!r}")
            pr, sha, exp = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if not pr.isdigit() or len(sha) != 40:
                die(f"{path}: bad field golden line {line!r}")
            if int(exp) != 0:
                die(f"{path}: PR #{pr} expects {exp} issues — nonzero "
                    "expectations need positive golden rows (unsupported "
                    "in --field mode yet)")
            if int(pr) in goldens:
                die(f"{path}: duplicate PR #{pr}")
            if sha in goldens.values():
                die(f"{path}: duplicate SHA {sha[:8]} (PR #{pr}) — one run "
                    "would be counted for two PRs")
            goldens[int(pr)] = sha
    if not goldens:
        die(f"{path}: no field golden rows")
    return goldens


def select_field_runs(recs, goldens, label_prefix, packaging_version="v03b"):
    """Map field runs to their PR via fixture_head SHA; gate like fixtures.

    The CJ field runs carry fixture=None, so the fixture selector ignores
    them; here fixture_head IS the identity — the run whose head matches
    PR N's squash SHA reviews PR N. Each PR needs exactly one run (re-runs
    with the same label prefix are ambiguous -> die, make labels unique).
    """
    sel = [r for r in recs if str(r.get("label", "")).startswith(label_prefix)]
    if not sel:
        die(f"no runs with label prefix {label_prefix!r}")
    by_sha: dict[str, list] = {}
    for r in sel:
        # expected=head neutralizes gate_run's fixture-SHA equality check
        # (field runs have no committed fixture); the SHA->PR mapping below
        # is the real gate. All other gates (fail_open, truncation,
        # packaging_version, judged completeness) still run.
        head = r.get("fixture_head")
        gate_run(r, expected=head, packaging_version=packaging_version)
        if head not in goldens.values():
            die(f"run {r.get('label')!r}: fixture_head {head} matches no "
                "field golden SHA")
        by_sha.setdefault(head, []).append(r)
    runs = {}
    for pr, sha in goldens.items():
        found = by_sha.get(sha, [])
        if len(found) != 1:
            die(f"PR #{pr}: expected exactly 1 run with head {sha[:8]}, "
                f"found {len(found)}")
        runs[pr] = found[0]
    return runs


def field_fp(jr, run, t, dt):
    """FP census for a clean field run at (code t, deletion dt).

    Same counting as negative_fp (eval_negative; MINOR-style exempt), but
    split by rubric: the deletion-knob sweep must attribute FPs to the
    knob it moves. A code-rubric FP at pinned t=0.50 is the CODE
    threshold's pressure (a separate calibration question — it cannot be
    fixed by moving dt, and counting it here would fake a signal).
    """
    reported = replay(jr, run, t, deletion_threshold=dt)

    def is_del(f):
        return f.get("rubric", "code-change") == "deletion"

    def fp(findings):
        counts = jr.eval_negative(findings)
        return counts["blocker_major"] + counts["other_fp"]

    return (fp([f for f in reported if not is_del(f)]),
            fp([f for f in reported if is_del(f)]))


# ---------- field-mode sweep (F2 executability plan, step b) ----------

def sweep_field(jr, field_runs, grid=None):
    """Deletion-threshold sweep over clean field runs (expected_issues=0).

    The five v03b CJ runs are all ground-truth clean, so per threshold the
    measurement is pure FP census (eval_negative counting; MINOR-style
    notes exempt, per E5). The code-change threshold stays at its shipped
    plateau while the deletion knob moves: a code-threshold candidate
    change remains gated on a future positive field golden (nonzero
    expectations), which load_field_goldens refuses until real rows exist.

    Decision semantics (differs from the fixture sweep ON PURPOSE): for a
    `is_real >= t` gate the FP count is monotonically NON-INCREASING in t,
    so "fewer FPs than shipped" is structurally unpassable — the fixture
    sweep can reward a lower threshold through RECALL, but an all-clean
    field cohort has no recall signal. What clean field data CAN decide:

    - 0 FPs at the shipped 0.70 -> KEEP (clean-side validated; the FP
      curve below shows how much headroom a lower knob would burn).
    - FPs at 0.70 -> RAISE_ABOVE_GRID: 0.70 is demonstrably too
      permissive, but 0.70 is the grid ceiling (plateau rule), so no
      auto-candidate exists — the value is a Kurt decision informed by
      the per-PR curve.

    The lower half of the curve is still reported: it documents the FP
    pressure a future lower threshold would face if positive field
    evidence ever motivates one.
    """
    grid = grid or threshold_grid()
    if DELETION_SHIPPED not in grid:
        die(f"field sweep grid lacks shipped {DELETION_SHIPPED:.2f} — no "
            "baseline row to decide KEEP/RAISE from")
    rows = []
    for dt in grid:
        fps = {pr: field_fp(jr, run, SHIPPED_THRESHOLD, dt)
               for pr, run in field_runs.items()}
        del_total = sum(v[1] for v in fps.values())
        code_total = sum(v[0] for v in fps.values())
        rows.append({"dt": dt, "fps": fps, "deletion_total": del_total,
                     "code_total": code_total})
    base = next(r for r in rows if r["dt"] == DELETION_SHIPPED)
    fps_at_shipped = base["deletion_total"]
    decision = "KEEP" if fps_at_shipped == 0 else "RAISE_ABOVE_GRID"
    return {"rows": rows, "shipped": DELETION_SHIPPED,
            "fps_at_shipped": fps_at_shipped, "decision": decision,
            "code_total_at_shipped": base["code_total"]}


def render_field(res, provider, model, prs):
    prov = provider + (f"/{model}" if model else "")
    header = " | ".join(f"#{p}" for p in prs)
    lines = [f"deletion-threshold sweep, field mode (provider/model: {prov}; "
             f"code threshold pinned at {SHIPPED_THRESHOLD})",
             f"dt | deletion-rubric FPs | code-rubric FPs (pinned t) | "
             f"deletion FP per-PR ({header})"]
    for r in res["rows"]:
        per = " | ".join(str(r["fps"][p][1]) for p in prs)
        lines.append(f"{r['dt']:.2f} | {r['deletion_total']} | "
                     f"{r['code_total']} | {per}")
    if res["decision"] == "KEEP":
        lines.append(f"deletion FPs at shipped {res['shipped']:.2f}: 0 — "
                     "every clean field run stays clean at the shipped knob")
        lines.append(f"decision: KEEP {res['shipped']:.2f} (clean-side "
                     "validated; recall-side evidence needs a positive "
                     "field golden, see load_field_goldens)")
    else:
        lines.append(f"deletion FPs at shipped {res['shipped']:.2f}: "
                     f"{res['fps_at_shipped']} — the knob is too permissive "
                     "on clean PRs")
        lines.append("decision: RAISE above "
                     f"{res['shipped']:.2f} (grid ceiling — pick the value "
                     "from the per-PR curve; human call)")
    if res["code_total_at_shipped"]:
        lines.append(f"note: {res['code_total_at_shipped']} code-rubric FPs "
                     f"at pinned t={SHIPPED_THRESHOLD} are CODE-threshold "
                     "pressure — a separate calibration question (needs a "
                     "positive field golden to evaluate), not this knob")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="E5 threshold sweep")
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--label", required=True, help="run label prefix")
    ap.add_argument("--golden", help="positive golden TSV (fixture mode)")
    ap.add_argument("--negative-golden",
                    help="negative golden TSV — drives the must-skip "
                         "triage-leakage guard; required (fixture mode) so "
                         "the guard cannot silently turn off (r3 m2)")
    ap.add_argument("--shas", help="expected fixture SHA file (fixture mode)")
    ap.add_argument("--field", action="store_true",
                    help="field mode: sweep the DELETION threshold over "
                         "clean CJ runs selected via --field-goldens; "
                         "requires --field-goldens, forbids fixture args")
    ap.add_argument("--field-goldens",
                    help="field golden TSV: pr<TAB>full40sha<TAB>expected")
    ap.add_argument("--packaging-version", default="v03b")
    args = ap.parse_args(argv)

    if args.field:
        if not args.field_goldens:
            die("--field needs --field-goldens")
        for bad, name in ((args.golden, "--golden"),
                          (args.negative_golden, "--negative-golden"),
                          (args.shas, "--shas")):
            if bad:
                die(f"--field forbids {name}")
    else:
        for need, name in ((args.golden, "--golden"),
                           (args.negative_golden, "--negative-golden"),
                           (args.shas, "--shas")):
            if not need:
                die(f"fixture mode needs {name}")

    jr = load_tool()
    with open(args.metrics) as f:
        recs = [json.loads(line) for line in f if line.strip()]

    if args.field:
        goldens = load_field_goldens(args.field_goldens)
        runs = select_field_runs(recs, goldens, args.label,
                                 args.packaging_version)
        provider, model = check_single_provider_group(list(runs.values()))
        res = sweep_field(jr, runs)
        print(render_field(res, provider, model, sorted(runs)))
        return 0

    expected = load_shas(args.shas)
    pos, neg, provider, model = select_runs(recs, expected, args.label,
                                            args.packaging_version)
    res = sweep(jr, pos, neg, args.golden, args.negative_golden)
    print(render(res, provider, model))
    return 0


if __name__ == "__main__":
    sys.exit(main())
