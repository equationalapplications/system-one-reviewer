"""Field-mode deletion-threshold sweep (F2 executability plan, step b).

Synthetic CJ-style runs: fixture=None, fixture_head = a PR squash SHA, all
runs ground-truth clean (expected_issues=0) — the shape of the v03b
curated-journal re-runs. The sweep module receives the already-loaded tool
(the `jr` fixture from conftest) so nothing here touches the network.
"""

import importlib.util
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP_PATH = os.path.join(REPO_ROOT, "scripts", "sweep-thresholds.py")

# PR squash SHAs (synthetic, but full 40-char like the real goldens)
PR43 = "c" * 40
PR44 = "d" * 40
PR45 = "e" * 40
FIELD_GOLDENS = {43: PR43, 44: PR44, 45: PR45}


@pytest.fixture
def sw():
    spec = importlib.util.spec_from_file_location("sweep-field-under-test", SWEEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _judged(file, line, real, sev, rubric="code-change", cat="bug-risk",
            conf=None, reported=False, refs=None):
    return {"file": file, "line": line, "severity": sev, "is_real": real,
            "category": cat, "confidence": conf, "reported": reported,
            "rubric": rubric, "references_remaining": refs}


def _field_run(label, head, judged, pv="v03b", provider="jev", model=None,
               verdict="Approved"):
    return {"label": label, "fixture": None, "fixture_head": head,
            "head": head[:10], "packaging_version": pv,
            "provider": provider, "model": model, "judged": judged,
            "verdict": verdict, "fail_open": False, "n_analyzed": len(judged)}


# ---------- golden loading ----------

def test_load_field_goldens_parses_pr_sha_expected(sw, tmp_path):
    p = tmp_path / "fg.tsv"
    p.write_text(f"43\t{PR43}\t0\n44\t{PR44}\t0\n")
    assert sw.load_field_goldens(str(p)) == {43: PR43, 44: PR44}


def test_load_field_goldens_rejects_duplicate_pr(sw, tmp_path):
    p = tmp_path / "fg.tsv"
    p.write_text(f"43\t{PR43}\t0\n43\t{PR44}\t0\n")
    with pytest.raises(SystemExit, match="duplicate PR #43"):
        sw.load_field_goldens(str(p))


def test_load_field_goldens_rejects_duplicate_sha(sw, tmp_path):
    """Two PRs sharing a SHA would map one run to both and count it twice."""
    p = tmp_path / "fg.tsv"
    p.write_text(f"43\t{PR43}\t0\n44\t{PR43}\t0\n")
    with pytest.raises(SystemExit, match="duplicate SHA"):
        sw.load_field_goldens(str(p))


def test_load_field_goldens_rejects_nonzero_expectations(sw, tmp_path):
    p = tmp_path / "fg.tsv"
    p.write_text(f"43\t{PR43}\t2\n")
    with pytest.raises(SystemExit, match="nonzero"):
        sw.load_field_goldens(str(p))


def test_load_field_goldens_rejects_short_sha(sw, tmp_path):
    p = tmp_path / "fg.tsv"
    p.write_text(f"43\t{'c' * 39}\t0\n")
    with pytest.raises(SystemExit, match="bad field golden"):
        sw.load_field_goldens(str(p))


# ---------- run selection ----------

def test_select_field_runs_maps_by_sha_and_gates(sw):
    recs = [
        _field_run("v03bcj-pr43-x", PR43,
                   [_judged("a.ts", 1, 0.9, 0.1)], verdict="Changes requested"),
        _field_run("v03bcj-pr44-x", PR44, []),
        _field_run("v03bcj-pr45-x", PR45, []),
    ]
    # Task 7: the select default is v08-ast now; these synthetic records
    # are v03b-tagged, so the version is explicit (r1-m1).
    runs = sw.select_field_runs(recs, FIELD_GOLDENS, "v03bcj-",
                                packaging_version="v03b")
    assert set(runs) == {43, 44, 45}


def test_select_field_runs_dies_on_unknown_head(sw):
    recs = [_field_run("v03bcj-pr99-x", "f" * 40, [])]
    with pytest.raises(SystemExit, match="matches no"):
        sw.select_field_runs(recs, FIELD_GOLDENS, "v03bcj-",
                             packaging_version="v03b")


def test_select_field_runs_dies_on_duplicate_run(sw):
    recs = [_field_run("v03bcj-pr43-a", PR43, []),
            _field_run("v03bcj-pr43-b", PR43, []),
            _field_run("v03bcj-pr44-x", PR44, []),
            _field_run("v03bcj-pr45-x", PR45, [])]
    with pytest.raises(SystemExit, match="exactly 1"):
        sw.select_field_runs(recs, FIELD_GOLDENS, "v03bcj-",
                             packaging_version="v03b")


def test_select_field_runs_still_gates_fail_open(sw):
    bad = _field_run("v03bcj-pr43-x", PR43, [])
    bad["fail_open"] = True
    with pytest.raises(SystemExit, match="fail_open"):
        sw.select_field_runs([bad], FIELD_GOLDENS, "v03bcj-")


def test_select_field_runs_still_gates_packaging_version(sw):
    bad = _field_run("v03bcj-pr43-x", PR43, [], pv="v02")
    with pytest.raises(SystemExit, match="packaging_version"):
        sw.select_field_runs([bad], FIELD_GOLDENS, "v03bcj-")


# ---------- FP census + sweep decision ----------

def test_field_fp_uses_both_knobs(jr, sw):
    """A deletion finding is_real 0.75: FP at dt=0.50, clean at dt=0.80."""
    run = _field_run("x", PR43, [_judged("gone.ts", 1, 0.75, 1.0,
                                         rubric="deletion", refs=False)])
    assert sw.field_fp(jr, run, 0.50, 0.50) == (0, 1)
    assert sw.field_fp(jr, run, 0.50, 0.80) == (0, 0)


def test_field_fp_splits_by_rubric(jr, sw):
    """Code-rubric FPs at pinned t are CODE pressure, not deletion-knob
    pressure — the split is what keeps the deletion sweep honest."""
    run = _field_run("x", PR43, [
        _judged("a.ts", 1, 0.9, 2.0),                      # code FP at t
        _judged("gone.ts", 1, 0.75, 1.0, rubric="deletion", refs=False)])
    assert sw.field_fp(jr, run, 0.50, 0.70) == (1, 1)
    assert sw.field_fp(jr, run, 0.50, 0.80) == (1, 0)


def test_field_fp_exempts_minor_style(jr, sw):
    run = _field_run("x", PR43, [_judged("a.ts", 3, 0.9, 1.0, cat="style")])
    assert sw.field_fp(jr, run, 0.50, 0.70) == (0, 0)


def test_sweep_field_keeps_when_zero_fp_everywhere(jr, sw):
    """The real-data shape: 0.70 already produces 0 FPs — clean-side
    validated, KEEP."""
    runs = {pr: _field_run(f"v03bcj-pr{pr}", sha, [])
            for pr, sha in FIELD_GOLDENS.items()}
    res = sw.sweep_field(jr, runs)
    assert res["shipped"] == 0.70
    assert res["fps_at_shipped"] == 0
    assert res["decision"] == "KEEP"


def test_sweep_field_raise_when_fps_at_shipped(jr, sw):
    """A deletion finding with is_real 0.75 reports even at dt=0.70 — the
    knob is too permissive on clean PRs -> RAISE_ABOVE_GRID (no
    auto-candidate: the grid ceiling IS the shipped value)."""
    judged = [_judged("gone.ts", 1, 0.75, 1.0, rubric="deletion", refs=False)]
    runs = {pr: _field_run(f"v03bcj-pr{pr}", sha,
                           judged if pr == 43 else [])
            for pr, sha in FIELD_GOLDENS.items()}
    res = sw.sweep_field(jr, runs)
    assert res["fps_at_shipped"] == 1
    assert res["decision"] == "RAISE_ABOVE_GRID"


def test_sweep_field_fp_curve_monotone_in_dt(jr, sw):
    """`is_real >= t` gates are monotone non-increasing in t — the FP
    curve must never rise as dt grows (this is WHY the fixture sweep's
    fewer-FPs rule is structurally unpassable in field mode)."""
    judged = [_judged("gone.ts", 1, 0.45, 1.0, rubric="deletion", refs=False),
              _judged("a.ts", 1, 0.9, 2.0)]  # code rubric: dt must not touch
    runs = {pr: _field_run(f"v03bcj-pr{pr}", sha,
                           judged if pr == 43 else [])
            for pr, sha in FIELD_GOLDENS.items()}
    res = sw.sweep_field(jr, runs)
    totals = [r["deletion_total"] for r in res["rows"]]
    assert totals == sorted(totals, reverse=True)  # monotone non-increasing
    assert totals[-1] == 0   # the deletion FP vanishes at high dt...
    # ...while the code-rubric FP stays at every dt (dt never gates it)
    assert res["code_total_at_shipped"] == 1


# ---------- CLI wiring ----------

def test_field_mode_end_to_end(jr, sw, tmp_path, capsys):
    metrics = tmp_path / "m.jsonl"
    judged43 = [_judged("gone.ts", 1, 0.75, 1.0, rubric="deletion", refs=False)]
    recs = [_field_run("v03bcj-pr43-x", PR43, judged43),
            _field_run("v03bcj-pr44-x", PR44, []),
            _field_run("v03bcj-pr45-x", PR45, [])]
    metrics.write_text("".join(json.dumps(r) + "\n" for r in recs))
    fg = tmp_path / "fg.tsv"
    fg.write_text("".join(f"{pr}\t{sha}\t0\n" for pr, sha in FIELD_GOLDENS.items()))
    rc = sw.main(["--metrics", str(metrics), "--label", "v03bcj-",
                  "--field", "--field-goldens", str(fg),
                  # Task 7: the CLI default gate is v08-ast; this synthetic
                  # metrics file is v03b-tagged (r1-m1).
                  "--packaging-version", "v03b"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "field mode" in out
    assert "decision: RAISE above 0.70" in out  # 1 deletion FP at 0.70


def test_field_mode_requires_field_goldens(sw, tmp_path):
    with pytest.raises(SystemExit, match="--field needs --field-goldens"):
        sw.main(["--metrics", str(tmp_path / "m.jsonl"), "--label", "x",
                 "--field"])


def test_field_mode_forbids_fixture_args(sw, tmp_path):
    g = tmp_path / "g.tsv"
    g.write_text("")
    with pytest.raises(SystemExit, match="forbids --golden"):
        sw.main(["--metrics", str(tmp_path / "m.jsonl"), "--label", "x",
                 "--field", "--field-goldens", str(g), "--golden", str(g)])


def test_fixture_mode_still_requires_goldens(sw, tmp_path):
    with pytest.raises(SystemExit, match="fixture mode needs"):
        sw.main(["--metrics", str(tmp_path / "m.jsonl"), "--label", "x"])


def test_sweep_field_grid_without_shipped_dies_loudly(jr, sw):
    """A custom grid that omits the shipped 0.70 has no baseline row to
    decide from — named die(), not a bare StopIteration."""
    runs = {pr: _field_run(f"v03bcj-pr{pr}", sha, [])
            for pr, sha in FIELD_GOLDENS.items()}
    with pytest.raises(SystemExit, match="lacks shipped"):
        sw.sweep_field(jr, runs, grid=[0.40, 0.50, 0.60])
