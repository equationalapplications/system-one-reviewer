"""Task 7 (E5): threshold sweep — gates, re-wrap, curve combination, ties.

Synthetic metrics records only: gates and math are tested against fake runs
with fake SHAs; the sweep module receives the already-loaded tool (the `jr`
fixture) so nothing here touches real state or the network.
"""

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP_PATH = os.path.join(REPO_ROOT, "scripts", "sweep-thresholds.py")

POS_SHA = "a" * 40
NEG_SHA = "b" * 40
EXPECTED = {"positive": POS_SHA, "negative": NEG_SHA}


@pytest.fixture
def sw():
    spec = importlib.util.spec_from_file_location("sweep-under-test", SWEEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _judged(line, real, sev=2.2, cat="bug-risk", file="a.py"):
    return {"file": file, "line": line, "severity": sev, "is_real": real,
            "category": cat, "confidence": None, "reported": True}


def _run(label, fixture, judged, pv="v02", provider="jev", model=None):
    head = EXPECTED[fixture]
    return {"label": label, "fixture": fixture, "fixture_head": head,
            "head": head[:10], "packaging_version": pv,
            "provider": provider, "model": model, "judged": judged}


def _pos_runs(judged, n=3, **kw):
    return [_run(f"v02-test-baseline-{i}", "positive", judged, **kw)
            for i in range(1, n + 1)]


def _neg_runs(judged, n=3, **kw):
    return [_run(f"v02-test-negative-{i}", "negative", judged, **kw)
            for i in range(1, n + 1)]


def _golden(tmp_path, rows):
    p = tmp_path / "g.tsv"
    p.write_text("".join(f"{f}\t{l}\t{d}\n" for f, l, d in rows))
    return str(p)


# ---------- threshold grid ----------

def test_grid_is_030_to_070_and_drops_the_075_plateau(sw):
    grid = sw.threshold_grid()
    assert grid == [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    assert 0.75 not in grid and 0.80 not in grid


# ---------- gates ----------

def test_gate_rejects_wrong_packaging_version(sw):
    with pytest.raises(SystemExit, match="packaging_version"):
        sw.gate_run(_run("x", "positive", [], pv="v01"), EXPECTED)


def test_gate_rejects_sha_mismatch(sw):
    bad = _run("x", "positive", [])
    bad["fixture_head"] = "c" * 40
    with pytest.raises(SystemExit, match="fixture_head"):
        sw.gate_run(bad, EXPECTED)


def test_gate_rejects_missing_judged(sw):
    rec = _run("x", "positive", [])
    del rec["judged"]
    with pytest.raises(SystemExit, match="judged"):
        sw.gate_run(rec, EXPECTED)


def test_select_runs_requires_three_per_fixture(sw, tmp_path):
    recs = _pos_runs([_judged(10, 0.9)], n=2) + _neg_runs([])
    with pytest.raises(SystemExit, match="3 runs per fixture"):
        sw.select_runs(recs, EXPECTED, "v02-test-")


def test_select_runs_gates_and_splits(sw):
    recs = _pos_runs([_judged(10, 0.9)]) + _neg_runs([])
    stale = _run("v02-test-baseline-9", "positive", [], pv="v01")
    pos, neg = sw.select_runs(recs + [stale], EXPECTED, "v02-test-")
    assert len(pos) == 3 and len(neg) == 3


# ---------- re-wrap + replay through compose ----------

def test_rewrap_builds_compose_shape(sw):
    f = sw.rewrap(_judged(10, 0.9))
    assert f["hunk"]["file"] == "a.py" and f["hunk"]["line"] == 10
    assert f["is_real"] == 0.9 and f["severity"] == 2.2
    assert f["category"] == "bug-risk" and not f["parse_error"]


def test_replay_reuses_compose_threshold(jr, sw):
    run = _run("r", "positive", [_judged(10, 0.90)])
    assert len(sw.replay(jr, run, 0.50)) == 1
    assert sw.replay(jr, run, 0.95) == []


# ---------- negative FP census on replayed data ----------

def test_negative_fp_counts_blocker_major(jr, sw):
    run = _run("n", "negative", [_judged(5, 0.60, sev=2.3)])
    assert sw.negative_fp(jr, run, 0.50) == 1
    assert sw.negative_fp(jr, run, 0.65) == 0


# ---------- curve combination, candidate, tie rule ----------

def test_candidate_is_argmax_of_min_f1_with_even_tie_rule(jr, sw, tmp_path):
    golden = _golden(tmp_path, [("a.py", 10, "x"), ("a.py", 20, "y")])
    judged = [_judged(10, 0.90), _judged(20, 0.55)]
    res = sw.sweep(jr, _pos_runs(judged), _neg_runs([]), golden)
    # F1=1.0 for t<=0.55 (6 tied thresholds) -> even tie -> lower middle
    assert res["candidate"] == 0.40
    assert res["rows"][0]["t"] == 0.30
    assert max(r["min_f1"] for r in res["rows"]) == 1.0


def test_odd_sized_tie_takes_the_middle(jr, sw, tmp_path):
    golden = _golden(tmp_path, [("a.py", 10, "x")])
    judged = [_judged(10, 0.60)]
    res = sw.sweep(jr, _pos_runs(judged), _neg_runs([]), golden)
    # F1=1.0 for the 7 thresholds 0.30..0.60 -> odd tie -> middle = 0.45
    assert res["candidate"] == 0.45


def test_change_rule_needs_margin_and_no_extra_neg_fps(jr, sw, tmp_path):
    # a 0.45-scored true issue: F1 jumps from 2/3 at 0.50 to 1.0 at <=0.45
    golden = _golden(tmp_path, [("a.py", 10, "x")])
    judged = [_judged(10, 0.45)]
    res = sw.sweep(jr, _pos_runs(judged), _neg_runs([]), golden)
    assert res["candidate"] == 0.35  # 4-way tie 0.30..0.45 -> lower middle
    assert res["rule_margin_ok"] is True
    assert res["rule_neg_fp_ok"] is True


def test_negative_fp_increase_blocks_the_change(jr, sw, tmp_path):
    # candidate threshold (0.35) sits BELOW a negative finding's score
    # (0.48): at the candidate every negative run has 1 FP, at 0.50 none —
    # dFP-neg > 0 per run, so rule 2 must block the change
    golden = _golden(tmp_path, [("a.py", 10, "x"), ("a.py", 20, "y")])
    pos = _pos_runs([_judged(10, 0.90), _judged(20, 0.45)])
    neg = _neg_runs([_judged(7, 0.48, sev=2.1)])
    res = sw.sweep(jr, pos, neg, golden)
    assert res["candidate"] == 0.35
    assert res["rows"][-1]["t"] == 0.70
    cand = next(r for r in res["rows"] if r["t"] == res["candidate"])
    base = next(r for r in res["rows"] if r["t"] == 0.50)
    assert cand["fp_neg_each"] == [1, 1, 1] and base["fp_neg_each"] == [0, 0, 0]
    assert res["rule_neg_fp_ok"] is False
    assert res["change"] is False


def test_candidate_that_reduces_negative_fps_passes_rule_2(jr, sw, tmp_path):
    # m3: the rule is dFP-neg <= 0 per run, NOT equality — a candidate
    # (0.65) that escapes a negative run's FP (scored 0.60, above 0.50)
    # must NOT be blocked by rule 2
    golden = _golden(tmp_path, [("a.py", 10, "x")])
    pos = _pos_runs([_judged(10, 0.75)])
    neg = _neg_runs([_judged(7, 0.60, sev=2.1)])
    res = sw.sweep(jr, pos, neg, golden)
    cand = next(r for r in res["rows"] if r["t"] == res["candidate"])
    base = next(r for r in res["rows"] if r["t"] == 0.50)
    assert res["candidate"] == 0.65  # tied 0.65/0.70 -> lower middle
    assert cand["fp_neg_each"] == [0, 0, 0] and base["fp_neg_each"] == [1, 1, 1]
    assert res["rule_neg_fp_ok"] is True


# ---------- provider grouping (E8) ----------

def test_mixed_providers_are_a_hard_error(sw):
    recs = (_pos_runs([_judged(10, 0.9)])
            + _neg_runs([], provider="laya", model="convaiinnovations/rl-agent"))
    with pytest.raises(SystemExit, match="provider"):
        sw.check_single_provider_group(recs)


def test_same_provider_group_passes(sw):
    recs = _pos_runs([_judged(10, 0.9)]) + _neg_runs([])
    assert sw.check_single_provider_group(recs) == ("jev", None)


def test_main_end_to_end_on_synthetic_metrics(jr, sw, tmp_path, capsys):
    golden = _golden(tmp_path, [("a.py", 10, "x")])
    judged = [_judged(10, 0.9)]
    recs = _pos_runs(judged) + _neg_runs([])
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text("".join(__import__("json").dumps(r) + "\n" for r in recs))
    shas = tmp_path / "shas.txt"
    shas.write_text(f"positive={POS_SHA}\nnegative={NEG_SHA}\n")
    rc = sw.main(["--metrics", str(metrics), "--label", "v02-test-",
                  "--golden", golden, "--shas", str(shas)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "candidate" in out and "0.50" in out
