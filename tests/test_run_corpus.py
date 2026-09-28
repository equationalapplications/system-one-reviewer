"""run_corpus: run planning, command shape, ledger isolation, resume."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402
import run_corpus as rc  # noqa: E402


def _corpus():
    prs = {}
    for pr in (1, 2):
        for phase, kind in (("pre", "positive"), ("final", "clean")):
            sid = cl.sample_id("o/r", pr, phase)
            prs[sid] = {"sample_id": sid, "repo": "o/r", "base_sha": "a" * 40,
                        "head_sha": ("b" if phase == "pre" else "c") * 40, "kind": kind,
                        "split": cl.split_for("o/r", pr), "source": "fix-pr"}
    return {"prs": prs, "issues": [], "dismissed": []}


def test_plan_runs_filters_split_and_repeats(tmp_path):
    corpus = _corpus()
    specs = rc.plan_runs(corpus, str(tmp_path), "base", "all", 3)
    assert len(specs) == 4 * 3
    s = specs[0]
    assert s["label"] == f"corpus:base:{s['sample_id']}:r1"
    assert s["out"].startswith(str(tmp_path / "work" / "runs" / "base"))
    assert s["out"].endswith("r1.json") and "#" not in s["out"] and "@" not in s["out"]
    train = rc.plan_runs(corpus, str(tmp_path), "base", "train", 1)
    assert all(corpus["prs"][x["sample_id"]]["split"] == "train" for x in train)


def test_build_cmd_uses_three_dot_range_and_label():
    spec = {"base": "a" * 40, "head": "b" * 40, "out": "/o.json", "label": "L"}
    cmd = rc.build_cmd(["py", "sor.py"], "/cache/o/r", spec)
    assert cmd == ["py", "sor.py", "--repo", "/cache/o/r", "--range",
                   f"{'a' * 40}...{'b' * 40}", "--json", "--out", "/o.json", "--label", "L"]


def test_run_all_isolates_ledger_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_REVIEW_METRICS", "/should/not/be/used.jsonl")
    specs = rc.plan_runs(_corpus(), str(tmp_path), "base", "all", 1)
    seen = []

    class Done:
        returncode = 0
        stderr = ""

    def runner(cmd, env, capture_output, text):
        seen.append(env["JEV_REVIEW_METRICS"])
        out = cmd[cmd.index("--out") + 1]
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "w").write("{}")
        return Done()

    failed = rc.run_all(specs, ["py", "sor.py"], str(tmp_path), "base",
                        prepare=lambda s: "/repo", runner=runner)
    assert failed == []
    assert set(seen) == {rc.ledger_path(str(tmp_path), "base")}
    seen.clear()
    rc.run_all(specs, ["py"], str(tmp_path), "base", prepare=lambda s: "/repo", runner=runner)
    assert seen == []  # all outputs exist: resumed, nothing re-run


def test_run_all_reports_failures(tmp_path):
    specs = rc.plan_runs(_corpus(), str(tmp_path), "base", "all", 1)[:1]

    class Bad:
        returncode = 1
        stderr = "boom"
    failed = rc.run_all(specs, ["py"], str(tmp_path), "base", prepare=lambda s: "/repo",
                        runner=lambda *a, **k: Bad())
    assert failed == [(specs[0]["label"], "boom")]
