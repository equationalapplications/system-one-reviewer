"""Task 3: golden eval rewrite — nearest-distance matching, +/-1 tolerance,
tp_severities. Synthetic TSVs in tmp_path (real TSV is Task 4's deliverable).
"""

import pytest


def _golden(tmp_path, rows):
    p = tmp_path / "g.tsv"
    p.write_text("".join(f"{f}\t{l}\t{d}\n" for f, l, d in rows))
    return str(p)


def _rep(file, line, sev=2):
    return {"hunk": {"file": file, "line": line}, "severity": sev}


def test_three_lines_apart_are_distinct_matches(jr, tmp_path):
    reported = [_rep("a.py", 10), _rep("a.py", 13)]
    res = jr.eval_against_golden(
        reported, _golden(tmp_path, [("a.py", 10, "x"), ("a.py", 13, "y")]))
    assert res["true_positives"] == 2
    assert res["precision"] == 1.0 and res["recall"] == 1.0


def test_nearest_golden_wins_and_each_golden_used_once(jr, tmp_path):
    # reported 10 sits between goldens 9 and 11 -> must match 9 (nearest);
    # then reported 11 cannot reuse golden 9
    reported = [_rep("a.py", 10), _rep("a.py", 11)]
    res = jr.eval_against_golden(
        reported, _golden(tmp_path, [("a.py", 9, "x"), ("a.py", 11, "y")]))
    assert res["true_positives"] == 2
    assert res["recall"] == 1.0


def test_tie_goes_to_lower_golden_line(jr, tmp_path):
    # reported 10 is distance 1 from both 9 and 11 -> lower line wins
    reported = [_rep("a.py", 10)]
    res = jr.eval_against_golden(
        reported, _golden(tmp_path, [("a.py", 11, "y"), ("a.py", 9, "x")]))
    assert res["true_positives"] == 1
    assert res["matched"][0] == ("a.py", 9)


def test_tolerance_rejects_distance_two(jr, tmp_path):
    reported = [_rep("a.py", 10)]
    res = jr.eval_against_golden(
        reported, _golden(tmp_path, [("a.py", 12, "far")]))
    assert res["true_positives"] == 0
    assert res["precision"] == 0.0
    assert res["recall"] == 0.0


def test_tp_severities_captured(jr, tmp_path):
    reported = [_rep("a.py", 10, sev=3), _rep("a.py", 20, sev=1),
                _rep("a.py", 30, sev=2)]
    res = jr.eval_against_golden(
        reported, _golden(tmp_path, [("a.py", 10, "x"), ("a.py", 20, "y")]))
    assert res["true_positives"] == 2
    assert sorted(res["tp_severities"]) == [1, 3]


def test_fp_f1_and_empty_cases(jr, tmp_path):
    res = jr.eval_against_golden(
        [_rep("a.py", 10), _rep("a.py", 99)],
        _golden(tmp_path, [("a.py", 10, "x")]))
    assert res["true_positives"] == 1 and res["reported"] == 2
    assert res["precision"] == 0.5 and res["recall"] == 1.0
    assert res["f1"] == 2 * 0.5 * 1.0 / 1.5
    # nothing reported at all
    res2 = jr.eval_against_golden([], _golden(tmp_path, [("a.py", 5, "m")]))
    assert res2["precision"] is None and res2["recall"] == 0.0
    assert res2["f1"] is None
