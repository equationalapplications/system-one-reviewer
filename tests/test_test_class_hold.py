"""compose() holds the test class out of what is surfaced; main() stamps,
counts and reports it. The class is judged and ledgered either way."""

import json

from test_enrichment import _add_file_diff


def _f(file, is_real=0.95, severity=3.0, cls=None, rubric="code-change"):
    f = {"hunk": {"file": file, "line": 1}, "is_real": is_real,
         "severity": severity, "category": "bug-risk", "rubric": rubric,
         "parse_error": None}
    if cls is not None:
        f["reflex_class"] = cls
    return f


def test_compose_holds_test_class_by_default(jr):
    findings = [_f("a.ts", cls="code"), _f("a.test.ts", cls="test")]
    reported, _, _ = jr.compose(findings, [], None, threshold=0.8)
    assert [f["hunk"]["file"] for f in reported] == ["a.ts"]


def test_compose_surfaces_test_class_when_not_held(jr):
    findings = [_f("a.ts", cls="code"), _f("a.test.ts", cls="test")]
    reported, _, _ = jr.compose(findings, [], None, threshold=0.8,
                                hold_classes=())
    assert len(reported) == 2


def test_compose_treats_a_missing_stamp_as_code(jr):
    reported, _, _ = jr.compose([_f("a.test.ts")], [], None, threshold=0.8)
    assert len(reported) == 1   # older ledgers replay unchanged


def test_compose_jitter_is_unchanged_by_the_hold(jr):
    f = _f("a.test.ts", is_real=0.81, cls="test")
    reported, jitter, _ = jr.compose([f], [], None, threshold=0.8)
    assert reported == [] and jitter and jitter[0]["file"] == "a.test.ts"


def _run(jr, monkeypatch, tmp_path, capsys, path, extra=(), is_real=0.95):
    diff = _add_file_diff(path, ["def f():", "    return 1"])
    records: list = []
    monkeypatch.setattr(jr, "judge", lambda kept, ask, errors=None, split_unit=None: (
        [{"hunk": h, "severity": 3.0, "is_real": is_real, "category": "bug-risk",
          "rubric": "code-change", "references_remaining": None,
          "change_type": h.get("change_type", "code-change"), "latency_ms": 1.0}
         for h in kept], [1.0] * len(kept),
        {"added_units": 0, "avg_input_tokens": None}))
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff", lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", lambda *a, **k: (None, "def f():\n    return 1\n"))
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv", ["system-one-reviewer", "--repo", str(tmp_path),
                                         "--staged", "--provider", "jev", "--json", *extra])
    jr.main()
    return json.loads(capsys.readouterr().out), records


def test_main_judges_stamps_and_holds_a_test_file_unit(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "tests/test_m.py")
    assert out["findings"] == []
    assert out["meta"]["n_test_held"] == 1
    judged = records[0]["judged"]
    assert len(judged) == 1                       # still judged and logged
    assert judged[0]["reflex_class"] == "test" and judged[0]["reported"] is False


def test_main_surfaces_it_with_include_test_findings(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "tests/test_m.py",
                        extra=("--include-test-findings",))
    assert len(out["findings"]) == 1
    assert out["meta"]["n_test_held"] == 0
    assert records[0]["judged"][0]["reflex_class"] == "test"
    assert records[0]["judged"][0]["reported"] is True


def test_main_code_file_is_unaffected(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "src/m.py")
    assert len(out["findings"]) == 1 and out["meta"]["n_test_held"] == 0
    assert records[0]["judged"][0]["reflex_class"] == "code"


def test_report_says_when_findings_were_held(jr):
    meta = {"repo": "r", "mode": "staged", "head": "0" * 40, "provider": "jev",
            "n_hunks": 1, "n_test_held": 2, "latencies": [1.0],
            "n_analyzed": 1, "jev_calls": 1, "total_latency_ms": 1.0}
    text = jr.render([], [], "OK", None, [], meta)
    assert "2 test-file finding(s) held back" in text
    assert "--include-test-findings" in text
    meta["n_test_held"] = 0
    assert "held back" not in jr.render([], [], "OK", None, [], meta)


def test_cap_applies_after_the_hold(jr, monkeypatch, tmp_path, capsys):
    """Six code units (sev 2.0) and two higher-severity test units (sev 3.0):
    ranking alone would put the test files first; the hold keeps them out so
    the 5-cap is filled by code only."""
    code = [f"src/m{i}.py" for i in range(6)]
    tests = ["tests/test_a.py", "tests/test_b.py"]
    diff = "".join(_add_file_diff(p, ["def f():", "    return 1"]) for p in code + tests)
    monkeypatch.setattr(jr, "judge", lambda kept, ask, errors=None, split_unit=None: (
        [{"hunk": h, "severity": 3.0 if h["file"].startswith("tests/") else 2.0,
          "is_real": 0.95, "category": "bug-risk", "rubric": "code-change",
          "references_remaining": None,
          "change_type": h.get("change_type", "code-change"), "latency_ms": 1.0}
         for h in kept], [1.0] * len(kept),
        {"added_units": 0, "avg_input_tokens": None}))
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff", lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", lambda *a, **k: (None, "def f():\n    return 1\n"))
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv", ["system-one-reviewer", "--repo", str(tmp_path),
                                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert len(out["findings"]) == 5
    assert all(f["file"].startswith("src/") for f in out["findings"])
    assert out["meta"]["n_test_held"] == 2
