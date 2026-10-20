"""Offline tests for the census cost columns (ctx_chars, added_tokens)."""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


census = _load("enrichment_census")


def _repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "a.ts").write_text("export function short() {\n  return 1;\n}\n")
    (repo / "b.py").write_text("def f():\n    return 1\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    return repo


def test_ctx_chars_and_added_tokens(tmp_path):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    repo = _repo(tmp_path)
    tool = census.load_tool()
    recs = census.census(tool, str(repo), "HEAD",
                         [("a.ts", 2), ("b.py", 2), ("gone.ts", 1)])
    by = {r["file"]: r for r in recs}
    unit = {"file": "a.ts", "line": 2, "change_type": "code-change", "entries": []}
    ctx = tool.build_ast_context("a.ts", None, (repo / "a.ts").read_text(), unit)
    assert by["a.ts"]["ctx_chars"] == len(json.dumps(ctx)) > 0
    assert by["b.py"]["ctx_chars"] > 0
    assert by["gone.ts"]["ctx_chars"] == 0
    summ = census.summarize(recs, tool)
    expected = (by["a.ts"]["ctx_chars"] + by["b.py"]["ctx_chars"]) / tool.CHARS_PER_TOKEN
    assert summ["added_tokens"] == pytest.approx(expected)
    assert summ["rows"] == 3 and summ["enriched"] == 2


def test_summarize_without_enrichment_adds_no_tokens():
    recs = [{"enriched": False, "missing": True, "covered": False, "window": 0,
             "ctx_chars": 0}]
    assert census.summarize(recs)["added_tokens"] == 0


def test_main_exits_3_when_a_wheel_import_raises(tmp_path, monkeypatch, capsys):
    golden = tmp_path / "g.tsv"
    golden.write_text("a.ts\t2\tdesc\n")

    def broken(name, package=None):
        raise ImportError(f"broken wheel {name}")

    monkeypatch.setattr(census.importlib, "import_module", broken)
    rc = census.main(["--repo", str(tmp_path), "--head", "HEAD",
                      "--golden", str(golden)])
    assert rc == 3
    err = capsys.readouterr().err
    assert "tree_sitter" in err and "ImportError" in err
