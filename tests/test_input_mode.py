"""--input: images, resolve_input and the main() wiring end to end (Task 3).

Input mode never shells out: every main() run here has `git` off PATH and
subprocess.run/Popen patched to raise. The equivalence test is the one place
that uses real git (to build the --range oracle), with its own isolated config.
"""

import json
import os
import subprocess

import pytest

HEAD = "c" * 40
PY_BEFORE = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
PY_AFTER = "def f():\n    return 1\n\n\ndef g():\n    x = 3\n    return x\n"


def doc(files, **over):
    d = {"head": HEAD, "repo": "my-repo", "files": files}
    d.update(over)
    return d


def fdoc(path, before, after, old_path=None):
    return {"path": path, "old_path": old_path, "before": before, "after": after}


def base_files():
    return [fdoc("src/m.py", PY_BEFORE, PY_AFTER),
            fdoc("tests/test_m.py", None, "def test_a():\n    assert 1\n"),
            fdoc("src/gone.py", "def h():\n    return 0\n", None),
            fdoc("src/new_name.py", "def k():\n    return 1\n\n\ndef j():\n    return 2\n",
                 "def k():\n    return 1\n\n\ndef j():\n    return 3\n",
                 old_path="src/old_name.py")]


# ---------- harness ----------

def stub_judge(monkeypatch, jr, is_real=0.95, judged=None):
    def fake_judge(kept, ask, errors=None, split_unit=None):
        if judged is not None:
            judged.extend(kept)
        return ([{"hunk": h, "severity": 3.0, "is_real": is_real, "category": "bug",
                  "rubric": "code-change", "references_remaining": None,
                  "change_type": h.get("change_type", "code-change"), "latency_ms": 1.0}
                 for h in kept], [1.0] * len(kept),
                {"added_units": 0, "avg_input_tokens": None})
    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5, "latency_ms": 1.0})
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")


def no_git(monkeypatch, tmp_path):
    """git absent from PATH and any subprocess use a hard failure."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    def boom(*a, **k):
        raise AssertionError("input mode must not spawn a subprocess")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


def run_input(jr, monkeypatch, tmp_path, capsys, d, extra=(), judged=None, is_real=0.95,
              as_json=True):
    """main() over `d` with a stub judge and no git; returns (stdout, records, judged)."""
    records: list = []
    stub_judge(monkeypatch, jr, is_real=is_real, judged=judged)
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    no_git(monkeypatch, tmp_path)
    p = tmp_path / "in.json"
    p.write_text(json.dumps(d))
    argv = ["system-one-reviewer", "--input", str(p), "--provider", "jev", *extra]
    if as_json:
        argv.append("--json")
    monkeypatch.setattr(jr.sys, "argv", argv)
    jr.main()
    out = capsys.readouterr().out
    return (json.loads(out) if as_json else out), records


# ---------- 1. mode_file_images input branch ----------

def test_images_input_branch_returns_map_with_none_sides(jr, monkeypatch):
    jr.set_input_images({"a.py": (None, "new\n"), "b.py": ("old\n", None), "c.py": ("x", "y")})
    assert jr.mode_file_images(None, "input", "h", "a.py") == (None, "new\n")
    assert jr.mode_file_images(None, "input", "h", "b.py") == ("old\n", None)
    assert jr.mode_file_images(None, "input", "h", "c.py") == ("x", "y")
    assert jr.mode_file_images(None, "input", "h", "nope.py") == (None, None)


def test_images_input_branch_never_touches_git_or_cache(jr, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no git in input mode")
    monkeypatch.setattr(jr, "git_show_or_none", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    jr.set_input_images({"a.py": ("o", "n")})
    # repo is None: dereferencing it (os.path.join, git -C) would raise
    assert jr.mode_file_images(None, "input", "h", "a.py", old_file="z.py") == ("o", "n")
    assert jr._IMAGE_CACHE == {}


def test_clear_runtime_caches_empties_input_images(jr):
    jr.set_input_images({"a.py": ("o", "n")})
    jr.clear_runtime_caches()
    assert jr._INPUT_IMAGES == {}
    assert jr.mode_file_images(None, "input", "h", "a.py") == (None, None)


def test_two_documents_do_not_collide(jr):
    jr.set_input_images({"a.py": ("o1", "n1")})
    jr.clear_runtime_caches()
    jr.set_input_images({"b.py": ("o2", "n2")})
    assert jr.mode_file_images(None, "input", "h", "a.py") == (None, None)
    assert jr.mode_file_images(None, "input", "h", "b.py") == ("o2", "n2")
    # replacing without a clear also drops the previous document
    jr.set_input_images({"c.py": ("o3", "n3")})
    assert jr.mode_file_images(None, "input", "h", "b.py") == (None, None)


def test_resolve_input_returns_diff_head_and_input_mode(jr):
    bundle = jr.build_input(jr.validate_input(doc([fdoc("a.py", "x\n", "y\n")])))
    diff, head, mode = jr.resolve_input(bundle)
    assert (diff, head, mode) == (bundle["diff"], HEAD, "input")
    assert jr.mode_file_images(None, mode, head, "a.py") == ("x\n", "y\n")


# ---------- 2. end to end through main() ----------

def test_e2e_report_meta_ledger_and_engagement(jr, monkeypatch, tmp_path, capsys):
    out, records = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()))
    meta = out["meta"]
    assert meta["mode"] == "input" and meta["repo"] == "my-repo"
    assert meta["head"] == HEAD and meta["n_input_autojunk"] == 0
    assert meta["status"] == "ok"
    rec = records[0]
    assert rec["mode"] == "input" and rec["label"] == "auto:input"
    assert rec["repo"] == "my-repo" and rec["head"] == HEAD[:10]
    assert rec["fixture_head"] == HEAD
    files = {j["file"] for j in rec["judged"]}
    assert {"src/m.py", "tests/test_m.py", "src/gone.py", "src/new_name.py"} <= files
    # the test-file hold engages: judged and logged, not surfaced
    t = next(j for j in rec["judged"] if j["file"] == "tests/test_m.py")
    assert t["reflex_class"] == "test" and t["reported"] is False
    assert meta["n_test_held"] == 1
    # the locator (where) and enrichment read the images from the map
    reported = {f["file"]: f for f in out["findings"]}
    assert "tests/test_m.py" not in reported
    assert reported["src/m.py"]["where"]["symbol"] == "g"
    m = next(j for j in rec["judged"] if j["file"] == "src/m.py")
    assert m["enrichment"] != "none"
    assert meta["enrichment"] != "none"


def test_e2e_rename_uses_carried_before_image(jr, monkeypatch, tmp_path, capsys):
    judged: list = []
    run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()), judged=judged)
    ren = [h for h in judged if h["file"] == "src/new_name.py"]
    assert ren and any("j" in str(h.get("ast_context", "")) for h in ren)


def test_e2e_ts_add(jr, monkeypatch, tmp_path, capsys):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    ts = "export function add(a: number, b: number): number {\n  return a + b;\n}\n"
    out, records = run_input(jr, monkeypatch, tmp_path, capsys,
                             doc([fdoc("src/a.ts", None, ts)]))
    assert out["findings"][0]["file"] == "src/a.ts"
    assert out["findings"][0]["where"]["symbol"] == "add"


def test_e2e_text_report_header(jr, monkeypatch, tmp_path, capsys):
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()), as_json=False)
    assert f"repo=my-repo mode=input head={HEAD[:10]}" in out


def test_e2e_repo_defaults_to_input(jr, monkeypatch, tmp_path, capsys):
    d = doc(base_files())
    del d["repo"]
    out, records = run_input(jr, monkeypatch, tmp_path, capsys, d)
    assert out["meta"]["repo"] == "input" and records[0]["repo"] == "input"


def test_e2e_validation_runs_before_load_api_key(jr, monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise AssertionError("load_api_key reached before validation")
    stub_judge(monkeypatch, jr)
    monkeypatch.setattr(jr, "load_api_key", boom)
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(doc([fdoc("a\nb", "x", "y")])))
    monkeypatch.setattr(jr.sys, "argv", ["sor", "--input", str(p)])
    with pytest.raises(SystemExit) as ei:
        jr.main()
    assert ei.value.code == 2


def test_e2e_bundle_built_before_load_api_key(jr, monkeypatch, tmp_path):
    order: list = []
    real_build = jr.build_input
    monkeypatch.setattr(jr, "build_input", lambda d: (order.append("build"), real_build(d))[1])
    stub_judge(monkeypatch, jr)
    monkeypatch.setattr(jr, "load_api_key", lambda: order.append("key") or "k")
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    p = tmp_path / "in.json"
    p.write_text(json.dumps(doc(base_files())))
    monkeypatch.setattr(jr.sys, "argv", ["sor", "--input", str(p), "--json"])
    jr.main()
    assert order[:2] == ["build", "key"]


# ---------- 3. equivalence with --range over real git ----------

GIT_ENV_KEYS = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_DATE": "2020-01-01T00:00:00",
                "GIT_COMMITTER_DATE": "2020-01-01T00:00:00"}
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
       "-c", "commit.gpgsign=false"]


def _git(repo, *args):
    env = {**os.environ, **GIT_ENV_KEYS}
    r = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode()
    return r.stdout.decode().strip()


def _units(judged):
    return [(h["file"], h["line"], h.get("line_start"), h.get("line_end"), list(h["lines"]))
            for h in judged]


def test_equivalence_with_range_over_real_git(jr, monkeypatch, tmp_path, capsys):
    files_before = {
        "src/m.py": PY_BEFORE,
        "src/gone.py": "def h():\n    return 0\n",
        "src/big.py": "".join(f"v{i} = {i}\n" for i in range(60)),
        "notes.txt": "one\ntwo",
    }
    files_after = {
        "src/m.py": PY_AFTER,
        "tests/test_m.py": "def test_a():\n    assert 1\n",
        "src/big.py": "".join(f"v{i} = {i}\n" if i not in (5, 50) else f"v{i} = -1\n"
                              for i in range(60)),
        "notes.txt": "one\ntwo\n",
    }
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, text in files_before.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "before")
    base = _git(repo, "rev-parse", "HEAD")
    for name in files_before:
        if name not in files_after:
            (repo / name).unlink()
    for name, text in files_after.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "after")
    head = _git(repo, "rev-parse", "HEAD")

    env = {**os.environ, **GIT_ENV_KEYS}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    stub_judge(monkeypatch, jr)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)

    def run(argv):
        judged: list = []
        stub_judge(monkeypatch, jr, judged=judged)
        monkeypatch.setattr(jr.sys, "argv", ["system-one-reviewer", *argv, "--provider", "jev"])
        jr.main()
        return _units(judged), capsys.readouterr().out

    git_units, git_report = run(["--repo", str(repo), "--range", f"{base}..{head}"])

    paths = sorted(set(files_before) | set(files_after))
    d = doc([fdoc(p, files_before.get(p), files_after.get(p)) for p in paths], head=head)
    p = tmp_path / "in.json"
    p.write_text(json.dumps(d))
    in_units, in_report = run(["--input", str(p)])

    assert git_units and len(git_units) >= 4
    assert in_units == git_units

    def strip(report):  # the header line carries repo / mode / head
        lines = report.split("\n")
        assert lines[1].startswith("repo=")
        return "\n".join(lines[:1] + lines[2:])
    assert strip(in_report) == strip(git_report)
    assert "mode=input" in in_report and "mode=range:" in git_report


# ---------- 4. per-file triage ----------

def test_skips_binary_and_oversize_code(jr, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(jr, "INPUT_MAX_FILE_CHARS", 50)
    files = [fdoc("img.dat", "a\0b", "a\0c"),
             fdoc("src/huge.py", "x = 1\n", "x = 2\n" + "# pad\n" * 20),
             fdoc("src/ok.py", "y = 1\n", "y = 2\n")]
    out, records = run_input(jr, monkeypatch, tmp_path, capsys, doc(files))
    skipped = {s["file"]: s for s in out["skipped"]}
    assert skipped["img.dat"] == {"file": "img.dat", "reason": "input-binary",
                                  "line_start": 1, "line_end": 1}
    assert skipped["src/huge.py"] == {"file": "src/huge.py", "reason": "hunk>input-oversize",
                                      "line_start": 1, "line_end": 1}
    assert out["meta"]["status"] == "incomplete review"
    assert out["n_size_skipped_code"] == 1
    assert records[0]["n_size_skipped_code"] == 1
    assert "incomplete review" in out["verdict"].lower()
    # banner: the oversize file is in the denominator ("N of M of T clusters")
    assert out["verdict"].endswith("of 2 clusters judged")
    assert [f["file"] for f in out["findings"]] == ["src/ok.py"]


def test_binary_alone_is_deliberate_triage(jr, monkeypatch, tmp_path, capsys):
    files = [fdoc("img.dat", "a\0b", "a\0c"), fdoc("src/ok.py", "y = 1\n", "y = 2\n")]
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc(files))
    assert out["meta"]["status"] == "ok" and out["n_size_skipped_code"] == 0
    assert [s["reason"] for s in out["skipped"]] == ["input-binary"]


def test_all_skipped_doc_reports_empty_and_logs(jr, monkeypatch, tmp_path, capsys):
    text, records = run_input(jr, monkeypatch, tmp_path, capsys,
                              doc([fdoc("img.dat", "a\0b", "a\0c")]), as_json=False)
    assert "Empty diff" in text and "input-binary" in text
    assert len(records) == 1 and records[0]["mode"] == "input"
    assert records[0]["judged"] == []


def test_empty_files_reports_empty_and_logs(jr, monkeypatch, tmp_path, capsys):
    text, records = run_input(jr, monkeypatch, tmp_path, capsys, doc([]), as_json=False)
    assert "Empty diff" in text
    assert len(records) == 1 and records[0]["n_hunks"] == 0


def test_unchanged_only_doc_is_empty(jr, monkeypatch, tmp_path, capsys):
    out, records = run_input(jr, monkeypatch, tmp_path, capsys,
                             doc([fdoc("a.py", "x\n", "x\n")]))
    assert out["meta"]["n_hunks"] == 0 and len(records) == 1


# ---------- 5. flags ----------

def test_flag_golden(jr, monkeypatch, tmp_path, capsys):
    g = tmp_path / "g.tsv"
    g.write_text("src/m.py\t5\tg is wrong\n")
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
                       extra=("--golden", str(g)))
    ev = out["golden_eval"]
    assert ev["golden_issues"] == 1 and ev["reported"] == len(out["findings"]) > 0


def test_flag_negative_golden(jr, monkeypatch, tmp_path, capsys):
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
                       extra=("--negative-golden", "x"))
    assert "negative_eval" in out["golden_eval"]


def test_flag_max_hunks(jr, monkeypatch, tmp_path, capsys):
    out, records = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
                             extra=("--max-hunks", "1"))
    assert out["n_dropped"] == 3 and out["meta"]["status"] == "incomplete review"
    assert records[0]["n_dropped"] == 3


def test_flag_label(jr, monkeypatch, tmp_path, capsys):
    _, records = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
                           extra=("--label", "exp:input-run"))
    assert records[0]["label"] == "exp:input-run"


def test_flag_include_test_findings(jr, monkeypatch, tmp_path, capsys):
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
                       extra=("--include-test-findings",))
    assert "tests/test_m.py" in {f["file"] for f in out["findings"]}
    assert out["meta"]["n_test_held"] == 0


def test_flag_out_and_fixture(jr, monkeypatch, tmp_path, capsys):
    o = tmp_path / "o.json"
    run_input(jr, monkeypatch, tmp_path, capsys, doc(base_files()),
              extra=("--out", str(o), "--fixture", "positive"))
    assert json.loads(o.read_text())["meta"]["mode"] == "input"


def test_git_modes_still_carry_autojunk_key(jr, monkeypatch, tmp_path, capsys):
    from test_enrichment import _add_file_diff
    diff = _add_file_diff("m.py", ["def f():", "    return 1"])
    stub_judge(monkeypatch, jr)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "resolve_diff", lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", lambda *a, **k: (None, None))
    monkeypatch.setattr(jr.sys, "argv", ["sor", "--repo", str(tmp_path), "--staged", "--json"])
    jr.main()
    meta = json.loads(capsys.readouterr().out)["meta"]
    assert meta["n_input_autojunk"] == 0
    assert meta["repo"] == os.path.basename(os.path.realpath(str(tmp_path)))


def test_autojunk_count_reaches_meta(jr, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(jr, "INPUT_MATCH_LINES", 5)
    before = "".join(f"l{i}\n" for i in range(20))
    after = before.replace("l3\n", "L3\n").replace("l15\n", "L15\n")
    out, _ = run_input(jr, monkeypatch, tmp_path, capsys, doc([fdoc("a.py", before, after)]))
    assert out["meta"]["n_input_autojunk"] == 1
