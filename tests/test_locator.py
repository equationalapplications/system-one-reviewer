"""locate(): where to look, never what is wrong. Independent of enrichment."""

import json

import pytest
from test_enrichment import _add_file_diff

PY = "class A:\n    def m(self):\n        return 1\n\n\ndef top():\n    return 2\n"
TS = ("export class Service {\n  run(job: string): void {\n"
      "    const cb = () => job.length;\n    cb();\n  }\n}\n")


def _unit(path, line, **kw):
    return {"file": path, "line": line, "change_type": "code-change",
            "entries": [("+", line, "x", line)], **kw}


def test_python_symbol(jr):
    assert jr.locate("m.py", None, PY, _unit("m.py", 3)) == {"symbol": "A.m", "line": 3}
    assert jr.locate("m.py", None, PY, _unit("m.py", 7)) == {"symbol": "top", "line": 7}


def test_module_level_is_none(jr):
    assert jr.locate("m.py", None, "x = 1\n", _unit("m.py", 1)) == {"symbol": None, "line": 1}


def test_ts_symbol(jr):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    got = jr.locate("m.ts", None, TS, _unit("m.ts", 3))
    assert got == {"symbol": "Service.run.cb", "line": 3}
    assert jr.locate("m.ts", None, TS, _unit("m.ts", 4))["symbol"] == "Service.run"


def test_deletion_only_uses_the_pre_image(jr):
    pre = "def gone():\n    return 1\n\n\ndef kept():\n    pass\n"
    post = "def kept():\n    pass\n"
    unit = {"file": "m.py", "line": 1, "change_type": "deletion-only",
            "entries": [("-", 2, "    return 1", 2)]}
    assert jr.locate("m.py", pre, post, unit)["symbol"] == "gone"


def test_deletion_only_uses_the_old_line_not_the_anchor(jr):
    pre = "".join(f"# {i}\n" for i in range(1, 10)) + (
        "def beta():\n    a = 1\n    b = 2\n    c = 3\n    return a\n") + (
        "".join(f"# {i}\n" for i in range(15, 21)))
    assert len(pre.splitlines()) == 20
    unit = {"file": "m.py", "line": 18, "change_type": "deletion-only",
            "entries": [("-", 10, "def beta():", 10)]}
    assert jr.locate("m.py", pre, "x = 1\n", unit) == {"symbol": "beta", "line": 18}


def test_whole_file_deleted_gives_none(jr):
    unit = {"file": "m.py", "line": 2, "change_type": "whole-file-deleted",
            "entries": [("-", 2, "    return 1", 2)]}
    assert jr.locate("m.py", PY, PY, unit) == {"symbol": None, "line": 2}


@pytest.mark.parametrize("pre,post", [(None, None), (None, ""), ("", "")])
def test_no_image_gives_none(jr, pre, post):
    assert jr.locate("m.py", pre, post, _unit("m.py", 1)) == {"symbol": None, "line": 1}


def test_syntax_error_and_unknown_language_fail_open(jr):
    assert jr.locate("m.py", None, "def (:\n", _unit("m.py", 1))["symbol"] is None
    assert jr.locate("m.rb", None, "def a\nend\n", _unit("m.rb", 1))["symbol"] is None


def test_never_raises(jr, monkeypatch):
    monkeypatch.setattr(jr, "_enclosing_chain",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert jr.locate("m.py", None, PY, _unit("m.py", 3)) == {"symbol": None, "line": 3}


def test_ts_context_none_gives_none(jr, monkeypatch):
    monkeypatch.setattr(jr, "_ts_ast_context", lambda *a, **k: None)
    assert jr.locate("m.ts", None, TS, _unit("m.ts", 3)) == {"symbol": None, "line": 3}


def test_does_not_read_ast_context(jr):
    unit = _unit("m.py", 7, ast_context={"enclosing": "bogus"})
    assert jr.locate("m.py", None, PY, unit)["symbol"] == "top"
    unit = _unit("m.py", 1, ast_context={"enclosing": "bogus"})
    assert jr.locate("m.py", None, "x = 1\n", unit)["symbol"] is None


def _run(jr, monkeypatch, tmp_path, capsys, extra=(), images=None, as_json=True):
    diff = _add_file_diff("src/m.py", ["def f():", "    return 1"])
    records: list = []
    monkeypatch.setattr(jr, "judge", lambda kept, ask, errors=None, split_unit=None: (
        [{"hunk": h, "severity": 3.0, "is_real": 0.95, "category": "bug-risk",
          "rubric": "code-change", "references_remaining": None,
          "change_type": h.get("change_type", "code-change"), "latency_ms": 1.0}
         for h in kept], [1.0] * len(kept),
        {"added_units": 0, "avg_input_tokens": None}))
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff", lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", images or (
        lambda *a, **k: (None, "def f():\n    return 1\n")))
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "laya_ask_or_die", lambda model=None: (lambda s, q: ({}, 1.0)))
    monkeypatch.setattr(jr.sys, "argv", ["system-one-reviewer", "--repo", str(tmp_path),
                                         "--staged", *extra, *(["--json"] if as_json else [])])
    jr.main()
    out = capsys.readouterr().out
    return (json.loads(out) if as_json else out), records


def test_surfaced_finding_carries_where_regardless_of_enrichment(
        jr, monkeypatch, tmp_path, capsys):
    on, records = _run(jr, monkeypatch, tmp_path, capsys, ("--provider", "jev",))
    off, _ = _run(jr, monkeypatch, tmp_path, capsys, ("--provider", "jev", "--no-enrichment"))
    assert on["findings"][0]["where"] == {"symbol": "f", "line": 1}
    assert off["findings"][0]["where"] == on["findings"][0]["where"]
    ledger = records[0]["findings"][0]
    assert ledger["where"] == {"symbol": "f", "line": 1} and "lines" not in ledger


def test_where_also_for_laya(jr, monkeypatch, tmp_path, capsys):
    out, _ = _run(jr, monkeypatch, tmp_path, capsys, ("--provider", "laya",))
    assert out["findings"][0]["where"] == {"symbol": "f", "line": 1}


def test_image_failure_gives_symbol_none(jr, monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise RuntimeError("no git")
    out, _ = _run(jr, monkeypatch, tmp_path, capsys, ("--provider", "laya",), images=boom)
    assert out["findings"][0]["where"] == {"symbol": None, "line": 1}


def test_report_prints_the_symbol(jr, monkeypatch, tmp_path, capsys):
    text, _ = _run(jr, monkeypatch, tmp_path, capsys, ("--provider", "jev",), as_json=False)
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("[") and "src/m.py:1" in ln)
    assert lines[i + 1] == "  in f"
    assert jr.render([{"hunk": {"file": "a.py", "line": 1, "header": "h", "lines": []},
                       "severity": 3.0, "where": {"symbol": None, "line": 1}}],
                     [], "ok", None, [],
                     {"repo": "r", "mode": "staged", "head": "0" * 40, "n_hunks": 1,
                      "latencies": [1.0], "n_analyzed": 1, "jev_calls": 1,
                      "total_latency_ms": 1.0}).count("  in ") == 0
