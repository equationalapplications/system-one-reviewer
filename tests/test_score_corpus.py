"""score_corpus: replay through compose(), matching, miss buckets, variance, loader isolation.

All runs are synthetic ledger records + --out JSON written under tmp_path;
the tool comes from the `jr` fixture (offline, isolated).
"""

import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402
import run_corpus as rc  # noqa: E402
import score_corpus as sc  # noqa: E402

PRE, FIN = "o/r#1@pre", "o/r#1@final"


def _j(file, line, lo, hi, sev, real, cat="bug-risk", rubric="code-change"):
    return {"file": file, "line": line, "line_start": lo, "line_end": hi, "severity": sev,
            "is_real": real, "category": cat, "confidence": 0.8, "rubric": rubric,
            "references_remaining": None, "change_type": "code-change", "reported": False}


def _write_corpus(root, issues, dismissed=()):
    prs = []
    for sid, kind, head in ((PRE, "positive", "b"), (FIN, "clean", "c")):
        prs.append({"sample_id": sid, "repo": "o/r", "base_sha": "a" * 40,
                    "head_sha": head * 40, "kind": kind, "split": cl.split_for("o/r", 1),
                    "source": "fix-pr"})
    base = {"verify_substring": "x", "category": "bug-risk", "evidence": "e",
            "fix_sha": "", "adjudicator": "claude", "spot_checked": "n"}
    cl.write_tsv(os.path.join(root, "prs.tsv"), cl.PRS_COLS, prs)
    cl.write_tsv(os.path.join(root, "issues.tsv"), cl.ISSUE_COLS,
                 [base | {"sample_id": PRE, "file": f, "line": str(n), "severity_class": s}
                  for f, n, s in issues])
    cl.write_tsv(os.path.join(root, "dismissed.tsv"), cl.DISMISSED_COLS,
                 [base | {"sample_id": PRE, "file": f, "line": str(n),
                          "severity_class": "minor", "label": "false-positive",
                          "dismissal_reason": "hallucinated"} for f, n in dismissed])


def _write_run(root, config, sid, k, judged, skipped=(), fail_open=False, latency=100.0):
    label = rc.label_for(config, sid, k)
    rec = {"label": label, "judged": judged, "packaging_version": "v03b",
           "fail_open": fail_open, "total_latency_ms": latency, "provider": "jev"}
    os.makedirs(rc.run_dir(root, config), exist_ok=True)
    with open(rc.ledger_path(root, config), "a") as f:
        f.write(json.dumps(rec) + "\n")
    out = rc.out_path(root, config, sid, k)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"skipped": list(skipped)}, open(out, "w"))


@pytest.fixture
def split():
    return cl.split_for("o/r", 1)


@pytest.fixture
def sw():
    return sc.load_sweep()


def test_scores_positive_and_clean(tmp_path, jr, sw, split):
    root = str(tmp_path)
    _write_corpus(root, [("a.py", 10, "major")], dismissed=[("b.py", 5)])
    _write_run(root, "base", PRE, 1, [
        _j("a.py", 10, 6, 14, 2.6, 0.8),          # TP (BLOCKER) -> Changes requested
        _j("b.py", 5, 1, 9, 1.4, 0.7),            # repeats a known FP
        _j("c.py", 3, 1, 7, 1.2, 0.3)])           # below threshold
    _write_run(root, "base", FIN, 1, [_j("a.py", 11, 7, 15, 1.3, 0.6)])  # FP on clean
    res = sc.score(root, "base", split=split, jr=jr, sw=sw)
    agg = res["aggregate"]
    assert agg["golden_total"] == 1 and agg["recall_strict"] == 1.0
    assert agg["recall_cluster"] == 1.0
    assert agg["precision"] == 0.5
    assert agg["fp_per_clean"] == 1.0
    assert agg["findings_per_pr"] == 1.5              # (2 + 1) / 2 samples
    assert agg["known_fp_repeats"] == 1 and agg["dismissed_total"] == 1
    assert agg["verdict_accuracy"] == 1.0              # @pre BLOCKER -> CR; final MINOR -> Approved
    assert res["missing"] == [] and res["by_repo"]["o/r"]["golden_total"] == 1


def test_miss_decomposition(tmp_path, jr, sw, split):
    root = str(tmp_path)
    _write_corpus(root, [("a.py", 12, "major"), ("a.py", 30, "minor"),
                         ("big.py", 50, "major"), ("z.py", 1, "minor"),
                         ("d.py", 8, "minor")])
    _write_run(root, "base", PRE, 1, [
        _j("a.py", 9, 6, 14, 2.2, 0.8),           # reported; covers 12 but |12-9|>1
        _j("a.py", 30, 26, 34, 2.0, 0.3),         # below threshold
        _j("d.py", 8, 4, 12, 0.4, 0.9)],          # real but severity < 1
        skipped=[{"file": "big.py", "reason": "hunk>120 lines",
                  "line_start": 1, "line_end": 200}])
    _write_run(root, "base", FIN, 1, [])
    agg = sc.score(root, "base", split=split, jr=jr, sw=sw)["aggregate"]
    # r13-m1 (Task 4): MISS_BUCKETS gains `truncated`; the :97 fossil above
    # is OLD-LEDGER FIXTURE DATA (intentional, do not update).
    assert agg["misses"] == {"anchor-offset": 1, "judged-below-threshold": 1,
                             "judged-low-severity": 1, "skipped-triage": 1,
                             "truncated": 0, "not-judged": 1}
    assert agg["recall_strict"] == 0.0 and agg["recall_cluster"] == 0.2


def test_span_covered_truncated_miss_lands_in_truncated_bucket(tmp_path, jr,
                                                                sw, split):
    """r13-m1: a ceiling-dropped unit's skipped entry (reason
    'max-hunks>ceiling', span-covered) classifies as `truncated`, NOT
    `skipped-triage` — a ceiling drop is not triage."""
    root = str(tmp_path)
    _write_corpus(root, [("big.py", 10, "major")])
    _write_run(root, "base", PRE, 1, [],
               skipped=[{"file": "big.py", "reason": "max-hunks>ceiling",
                         "line_start": 1, "line_end": 40}])
    _write_run(root, "base", FIN, 1, [])
    agg = sc.score(root, "base", split=split, jr=jr, sw=sw)["aggregate"]
    assert agg["misses"]["truncated"] == 1
    assert agg["misses"]["skipped-triage"] == 0


def test_variance_and_missing_and_fail_open(tmp_path, jr, sw, split):
    root = str(tmp_path)
    _write_corpus(root, [("a.py", 10, "major")])
    _write_run(root, "base", PRE, 1, [_j("a.py", 10, 6, 14, 2.6, 0.8)])
    _write_run(root, "base", PRE, 2, [_j("a.py", 10, 6, 14, 2.6, 0.4)])   # flips verdict
    _write_run(root, "base", FIN, 1, [], fail_open=True)
    res = sc.score(root, "base", split=split, jr=jr, sw=sw, repeats=2)
    v = res["variance"]
    assert v["identical"] is False and v["verdict_flips"] == 1
    assert v["max_is_real_spread"] == pytest.approx(0.4)
    assert res["aggregate"]["fail_open"] == 1
    assert (FIN, 2) in [(m["sample_id"], m["k"]) for m in res["missing"]]


def test_replay_grid_moves_threshold(tmp_path, jr, sw, split):
    root = str(tmp_path)
    _write_corpus(root, [("a.py", 10, "major")])
    _write_run(root, "base", PRE, 1, [_j("a.py", 10, 6, 14, 2.6, 0.42)])
    _write_run(root, "base", FIN, 1, [])
    grid = sc.replay_grid(root, "base", split=split, jr=jr, sw=sw)
    by_t = {g["threshold"]: g["recall_strict"] for g in grid}
    assert by_t[0.4] == 1.0 and by_t[0.45] == 0.0


def test_load_sweep_is_isolated(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["pytest-should-not-be-read"])
    before = set(sys.modules)
    a, b = sc.load_sweep(), sc.load_sweep()
    assert a is not b and a.GRID is not b.GRID
    assert set(sys.modules) == before
    assert capsys.readouterr() == ("", "")


def test_render_markdown_mentions_primary_metrics(tmp_path, jr, sw, split):
    root = str(tmp_path)
    _write_corpus(root, [("a.py", 10, "major")])
    _write_run(root, "base", PRE, 1, [_j("a.py", 10, 6, 14, 2.6, 0.8)])
    _write_run(root, "base", FIN, 1, [])
    md = sc.render_markdown(sc.score(root, "base", split=split, jr=jr, sw=sw))
    for key in ("recall (strict)", "FPs per clean PR", "verdict accuracy", "misses"):
        assert key in md
