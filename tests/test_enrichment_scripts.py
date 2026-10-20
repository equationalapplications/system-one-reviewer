"""Offline tests for the enrichment census and A/B harness helpers."""

import importlib.util
import os
import subprocess

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts")


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _load("enrichment_ab")
census = _load("enrichment_census")


# ---------- A/B: vacuity guard + decision rules ----------

def _res(stamp, wheels=True):
    return {"meta": {"enrichment": stamp,
                     "wheels": {"python": {"available": True},
                                "ts": {"available": wheels}}}}


def test_guard_rejects_an_arm_that_never_engaged():
    assert ab.guard(_res("ts-ast"), "on", "ts-ast") is None
    assert "stamped 'none'" in ab.guard(_res("none"), "on", "ts-ast")
    assert "stamped 'ast'" in ab.guard(_res("ast"), "on", "ts-ast")
    assert ab.guard(_res("ast+ts-ast"), "on", "ts-ast") is None
    # python's cutter is always "available"; only the TS wheels count
    assert "wheels" in ab.guard(_res("ts-ast", wheels=False), "on", "ts-ast")
    assert ab.guard(_res("ast", wheels=False), "on", "ast") is None
    assert ab.guard(_res("none"), "off", "ts-ast") is None
    assert "off-arm" in ab.guard(_res("ts-ast"), "off", "ts-ast")


def test_sign_test():
    assert ab.sign_test_p([]) == 1.0
    assert ab.sign_test_p([0, 0]) == 1.0
    assert ab.sign_test_p([-0.1] * 8) < 0.05
    assert ab.sign_test_p([0.1, -0.1, 0.1, -0.1]) == 1.0


def _row(on_rep, off_rep, on_tp, off_tp, deltas=()):
    return {"on_reported": on_rep, "off_reported": off_rep,
            "on_tp": on_tp, "off_tp": off_tp, "deltas": list(deltas)}


def test_decide():
    flat = [0.0] * 4
    # recall signal in every repeat, precision held
    rows = [_row(1, 1, 5, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "SIGNAL"
    # a single repeat short of +2 is not signal
    rows = [_row(1, 1, 5, 3, flat), _row(1, 1, 4, 3, flat)]
    assert ab.decide(rows)["verdict"] == "NO-DETECTABLE-EFFECT"
    # clean sample: any extra surfaced finding is a new false positive
    rows = [_row(2, 1, 0, 0, flat)] * 3
    assert ab.decide(rows, clean=True)["verdict"] == "KILL"
    # golden sample: extra TRUE positives are the point, not a kill
    rows = [_row(5, 3, 5, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "SIGNAL"
    # ...but extra false positives (reported - tp) still are
    rows = [_row(6, 3, 4, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "KILL"
    assert ab.decide([])["verdict"] == "NO-DETECTABLE-EFFECT"
    # systematic softening kills even when precision and recall pass
    rows = [_row(1, 1, 5, 3, [-0.1] * 8)] * 2
    assert ab.decide(rows)["verdict"] == "KILL"


def test_paired_deltas_pair_by_unit():
    on = [{"file": "a.ts", "line": 1, "line_end": 3, "is_real": 0.5},
          {"file": "b.ts", "line": 1, "line_end": 3, "is_real": 0.9}]
    off = [{"file": "a.ts", "line": 1, "line_end": 3, "is_real": 0.7}]
    assert ab.paired_is_real_deltas(on, off) == pytest.approx([-0.2])


# ---------- census ----------

def test_census_on_a_throwaway_repo(tmp_path):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    repo = tmp_path / "r"
    repo.mkdir()
    long_body = "".join(f"  const v{i} = {i};\n" for i in range(40))
    (repo / "a.ts").write_text(
        "export function short() {\n  return 1;\n}\n"
        f"export function long() {{\n{long_body}  return 2;\n}}\n")
    (repo / "b.py").write_text("def f():\n    return 1\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    tool = census.load_tool()
    recs = census.census(tool, str(repo), "HEAD",
                         [("a.ts", 2), ("a.ts", 40), ("b.py", 2), ("gone.ts", 1)])
    by = {(r["file"], r["line"]): r for r in recs}
    assert by[("a.ts", 2)]["covered"] and by[("a.ts", 2)]["enclosing"] == "short"
    # position, not text: a repeated line outside the window is not covered
    assert by[("a.ts", 2)]["window"] == 3
    # a line deep in a long function is outside the 20-line head-first window
    assert by[("a.ts", 40)]["enriched"] and not by[("a.ts", 40)]["covered"]
    assert by[("b.py", 2)]["covered"]
    assert not by[("gone.ts", 1)]["enriched"]
    summ = census.summarize(recs)
    assert summ["rows"] == 4 and summ["enriched"] == 3 and summ["covered"] == 2
    assert summ["missing"] == 1 and by[("gone.ts", 1)]["missing"]
