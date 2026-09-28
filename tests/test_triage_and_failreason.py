"""Fail-open reason surfacing + data-file triage (post-v0.3b install test).

The first live install run failed open on an SSL CA error and the report
said only "unavailable after repeated failures" — the cause was invisible.
The same run judged a .jsonl metrics ledger as code and printed whole
records as a finding.
"""

import pytest


def _hunk(i, file="f.py"):
    return {"file": file, "line": i, "hunk_start": 1, "lines": ["x"],
            "entries": [(" ", i, "x", 1)], "n_changed": 1, "header": "h",
            "size": 1, "too_large": False}


# ---------- fail-open reason ----------

def test_judge_records_transport_error_reason(jr):
    def dead(state, questions):
        raise RuntimeError("certificate verify failed")
    errors = []
    findings, _ = jr.judge([_hunk(1), _hunk(2)], dead, errors=errors)
    assert findings is None
    assert errors and "certificate verify failed" in errors[-1]
    assert "RuntimeError" in errors[-1]


def test_judge_records_shape_error_reason(jr):
    def garbage(state, questions):
        return {"answers": {}}, 1.0
    errors = []
    findings, _ = jr.judge([_hunk(1), _hunk(2)], garbage, errors=errors)
    assert findings is None
    assert errors and "severity" in errors[-1]


def test_judge_errors_param_is_optional(jr):
    def dead(state, questions):
        raise RuntimeError("x")
    findings, _ = jr.judge([_hunk(1), _hunk(2)], dead)
    assert findings is None


def test_render_shows_fail_reason(jr):
    meta = {"repo": "r", "mode": "m", "head": "0" * 40, "n_analyzed": 2,
            "total_latency_ms": 0.0, "jev_calls": 0, "fail_open": True,
            "provider": "jev", "model": None,
            "fail_reason": "SSLCertVerificationError('certificate verify failed')"}
    out = jr.render([], [], "Unavailable", None, [], meta)
    assert "last error: SSLCertVerificationError" in out


# ---------- data-file triage ----------

@pytest.mark.parametrize("path", [
    "docs/benchmarks/metrics.jsonl", "events.ndjson", "data/x.csv",
    "examples/golden.tsv", "src/__snapshots__/App.test.tsx.snap",
    "Gemfile.lock", "composer.lock", "Pipfile.lock", "go.sum",
    "flake.lock", "sub/pkg/bun.lock",
])
def test_data_and_lock_files_are_triaged(jr, path):
    kept, skipped = jr.triage([_hunk(1, file=path)])
    assert not kept, f"{path} must be skipped"
    assert skipped[0]["file"] == path


@pytest.mark.parametrize("path", [
    "package.json", "tsconfig.json", "src/config.json", "src/data.py",
    "src/csv_reader.py", "src/lockfile.py",
])
def test_code_and_config_are_still_judged(jr, path):
    kept, _ = jr.triage([_hunk(1, file=path)])
    assert kept, f"{path} must still be judged"


def test_data_skip_reason_is_distinct(jr):
    _, skipped = jr.triage([_hunk(1, file="m.jsonl")])
    assert skipped[0]["reason"] == "data/snapshot"


# ---------- git/argument errors (live install testing) ----------

def _git_repo(tmp_path):
    import subprocess as sp
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"], ["add", "-A"],
                ["commit", "-qm", "head"]):
        sp.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    return repo


def _args(**kw):
    from types import SimpleNamespace
    base = dict(range=None, pr=None, staged=False, uncommitted=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_non_git_repo_is_a_clear_error(jr, tmp_path):
    with pytest.raises(SystemExit, match="not a git repository"):
        jr.resolve_diff(str(tmp_path), _args(range="HEAD~1..HEAD"))


def test_missing_repo_is_a_clear_error(jr, tmp_path):
    with pytest.raises(SystemExit, match="not a git repository"):
        jr.resolve_diff(str(tmp_path / "nope"), _args(staged=True))


def test_pr_without_local_ref_gives_fetch_hint(jr, tmp_path):
    repo = _git_repo(tmp_path)
    with pytest.raises(SystemExit,
                       match=r"git fetch origin pull/7/head:pr/7"):
        jr.resolve_diff(str(repo), _args(pr=7))


# ---------- report readability ----------

def _meta(**kw):
    m = {"repo": "r", "mode": "m", "head": "0" * 40, "n_analyzed": 0,
         "n_hunks": 1, "total_latency_ms": 0.0, "jev_calls": 0,
         "fail_open": False, "provider": "jev", "model": None}
    m.update(kw)
    return m


def _finding(file, line, sev):
    h = _hunk(line, file=file)
    h["header"] = f"@@ {file} around line {line} @@"
    return {"hunk": h, "severity": sev, "is_real": 0.9, "category": "bug-risk"}


def test_render_orders_findings_by_severity(jr):
    reported = [_finding("a.py", 1, 1.2), _finding("b.py", 2, 2.9),
                _finding("c.py", 3, 2.0)]
    out = jr.render(reported, [], "Changes requested", None, [], _meta())
    order = [ln.split("]")[0] for ln in out.splitlines() if ln.startswith("[")]
    assert order == ["[BLOCKER", "[MAJOR", "[MINOR"]


def test_render_collapses_duplicate_skips(jr):
    skipped = [{"file": "package-lock.json", "reason": "docs/generated/lockfile"}] * 2 \
        + [{"file": "big.ts", "reason": "hunk>120 lines"}] * 3
    out = jr.render([], skipped, "Approved", None, [], _meta())
    line = next(ln for ln in out.splitlines() if ln.startswith("Skipped"))
    assert line.count("package-lock.json") == 1
    assert "package-lock.json (docs/generated/lockfile) x2" in line
    assert "big.ts (hunk>120 lines) x3" in line


def test_render_says_when_skips_are_truncated(jr):
    skipped = [{"file": f"f{i}.md", "reason": "docs/generated/lockfile"}
               for i in range(13)]
    out = jr.render([], skipped, "Approved", None, [], _meta())
    assert "(+3 more)" in out


def test_render_flags_empty_diff(jr):
    out = jr.render([], [], "Approved", None, [], _meta(n_hunks=0))
    assert "empty diff" in out.lower()


def test_empty_diff_makes_no_model_calls(jr, tmp_path, capsys, monkeypatch):
    calls = []

    def counting(state, questions):
        calls.append(1)
        return {"answers": {}}, 1.0

    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: counting)
    monkeypatch.setattr(jr, "set_provider_name", lambda name: None)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo_, a: ("", "0" * 40, "range:HEAD...HEAD"))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    monkeypatch.setattr("sys.argv", ["system-one-reviewer", "--repo",
                                     str(tmp_path), "--range", "HEAD..HEAD",
                                     "--label", "empty"])
    jr.main()
    out = capsys.readouterr().out
    assert calls == [], "an empty diff must not spend a model call"
    assert "empty diff" in out.lower()
    assert out.rstrip().splitlines()[-1] == "Approved"


def test_git_probe_timeout_is_a_clear_error(jr, tmp_path, monkeypatch):
    """A stalled git (hung network FS, lock) must not block the CLI
    forever: the up-front probes carry a timeout and report it cleanly."""
    import subprocess as sp
    seen = {}

    def hang(cmd, **kw):
        seen["timeout"] = kw.get("timeout")
        raise sp.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(jr.subprocess, "run", hang)
    with pytest.raises(SystemExit, match="timed out"):
        jr.resolve_diff(str(tmp_path), _args(staged=True))
    assert seen["timeout"], "probe must pass a timeout"


def test_pr_ref_probe_timeout_is_a_clear_error(jr, tmp_path, monkeypatch):
    import subprocess as sp
    repo = _git_repo(tmp_path)
    real_run = sp.run

    def hang_on_verify(cmd, **kw):
        if "--verify" in cmd:
            assert kw.get("timeout"), "pr-ref probe must pass a timeout"
            raise sp.TimeoutExpired(cmd, kw["timeout"])
        return real_run(cmd, **kw)

    monkeypatch.setattr(jr.subprocess, "run", hang_on_verify)
    with pytest.raises(SystemExit, match="timed out"):
        jr.resolve_diff(str(repo), _args(pr=7))
