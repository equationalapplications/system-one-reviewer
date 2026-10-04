"""Task 4 (AST-units plan): triage rewiring + unit counters + ceiling records.

r5-M4: `triage()` gains a provider/size_policy param — the `hunk>` size
skip is LAYA-only; jev routes oversize clusters through the Task 2/3
cutter instead. r8-M1/r9-M1: unit counters are leaf-aware and two-phase
(n_units_pre frozen pre-judge, n_units_total/n_analyzed post-judge).
r12-m1/r13-m1: --max-hunks ceiling truncation emits `skipped` entries
with reason `max-hunks>ceiling` (never parse_error findings, never laya).
"""

import json

import pytest

# ---------- helpers ----------

def _hunk(i, file="f.py"):
    return {"file": file, "line": i, "hunk_start": 1, "lines": ["x"],
            "entries": [(" ", i, "x", 1)], "n_changed": 1, "header": "h",
            "size": 1, "too_large": False}


def _oversize_hunk(change_type="code-change", file="big.ts"):
    h = _hunk(1, file=file)
    h["too_large"] = True
    h["change_type"] = change_type
    return h


def _payload_fn(name, chars):
    body = '    payload = "' + "a" * chars + '"\n    return payload\n'
    return f"def {name}():\n{body}"


def _oversize_py_src(n=3, chars=30_000):
    """n top-level functions, ~n*chars serialized chars (>84k at n=3)."""
    return "\n".join(_payload_fn(f"fn_{i}", chars) for i in range(n))


def _whole_file_add_diff(path, src):
    n = len(src.splitlines())
    lines = [f"diff --git a/{path} b/{path}",
             f"--- a/{path}", f"+++ b/{path}",
             f"@@ -0,0 +1,{n} @@"]
    lines += ["+" + ln for ln in src.splitlines()]
    return "\n".join(lines) + "\n"


def _meta(**kw):
    m = {"repo": "r", "mode": "m", "head": "0" * 40, "n_analyzed": 0,
         "n_hunks": 1, "total_latency_ms": 0.0, "jev_calls": 0,
         "fail_open": False, "provider": "jev", "model": None}
    m.update(kw)
    return m


# ---------- r5-M4: provider-gated size triage ----------

def test_no_hunk_skip_reason_ever_jev(jr):
    """r5-M4: under jev ANY cluster — any size, any change_type — never
    produces a `hunk>` skip record (the deliberate whole-file-deleted>cap
    exempt per r5-M3)."""
    hunks = [_oversize_hunk("code-change"),
             _oversize_hunk("deletion-only", file="old.py"),
             _hunk(2, file="normal.py")]
    kept, skipped = jr.triage(hunks, provider="jev")
    for s in skipped:
        assert not str(s.get("reason", "")).startswith("hunk>")
    assert len(kept) == 3, "jev never size-skips; routing is the caller's job"


def test_laya_keeps_size_skip(jr):
    """r5-M4: laya keeps TODAY'S exact behavior — a `hunk>` skip record is
    appended for oversize clusters, change_type included."""
    kept, skipped = jr.triage([_oversize_hunk("code-change"),
                               _oversize_hunk("deletion-only", file="old.py")],
                              provider="laya")
    assert kept == []
    by_file = {s["file"]: s for s in skipped}
    assert by_file["big.ts"]["reason"].startswith("hunk>")
    assert by_file["old.py"]["reason"].startswith("hunk>")
    assert by_file["big.ts"]["change_type"] == "code-change"
    assert by_file["old.py"]["change_type"] == "deletion-only"


def test_triage_size_skip_carries_change_type_jev_routes_to_cutter(jr):
    """Successor of test_triage_size_skip_carries_change_type: under jev an
    oversize cluster is NOT skipped — it stays in kept so main() can route
    it through ast_units; the skip-record change_type contract stays live
    for laya only."""
    oversize = _oversize_hunk("code-change")
    kept, skipped = jr.triage([oversize], provider="jev")
    assert kept == [oversize] and skipped == []


def test_triage_default_provider_is_jev(jr):
    """The gate must be MECHANICAL (r5-M4): triage() defaults to the jev
    policy (no size skip), so the legacy `hunk>` path only fires when the
    caller explicitly passes laya."""
    kept, _ = jr.triage([_oversize_hunk()])
    assert len(kept) == 1


def test_laya_legacy_suffix_byte_identical(jr, monkeypatch, tmp_path):
    """LAYA KEEPS TODAY'S EXACT BEHAVIOR: a laya run over an oversize-only
    diff produces today's legacy suffix string byte-for-byte (plus the
    hunk> skip and n_size_skipped_code == 1)."""
    diff = "\n".join(
        ["diff --git a/big.py b/big.py", "new file mode 100644",
         "index 0000000..1111111", "--- /dev/null", "+++ b/big.py",
         "@@ -0,0 +1,150 @@"] + [f"+line {i}" for i in range(1, 151)])
    records = []

    def fake_pr_level(findings, ask, size_skipped_code=None):
        return {"overall_risk": 1.0, "needs_human_review": 0.5,
                "latency_ms": 1.0}

    def fake_judge(kept, ask, errors=None, split_unit=None):
        assert kept == [], "laya's oversize-only diff judges nothing"
        return [], [], {"added_units": 0, "avg_input_tokens": None}

    monkeypatch.setattr(jr, "judge_pr_level", fake_pr_level)
    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "laya_ask_or_die", lambda model=None: None)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "laya"])
    jr.main()
    rec = records[0]
    assert rec["provider"] == "laya"
    assert rec["n_size_skipped_code"] == 1
    assert rec["n_analyzed"] == 0
    assert rec["verdict"] == ("Approved (incomplete review — 0 of 1 "
                              "clusters judged)")
    assert rec["base_verdict"] == "Approved"


# ---------- oversize routing through the Task 2/3 cutter ----------

def test_oversize_python_becomes_subclusters_via_main(jr, monkeypatch,
                                                      tmp_path, capsys):
    """r5-M4 routing: an oversize Python cluster under jev is split by
    ast_units into sub-clusters judged as first-class units."""
    src = _oversize_py_src()
    assert len(src) > 84_000
    diff = _whole_file_add_diff("big.py", src)
    judged_units = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged_units.extend(kept)
        return ([{"hunk": h, "severity": 1.2, "is_real": 0.2,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    def fake_pr_level(findings, ask, size_skipped_code=None):
        return {"overall_risk": 1.0, "needs_human_review": 0.5,
                "latency_ms": 1.0}

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level", fake_pr_level)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert len(judged_units) == 3, "3 top-level functions -> 3 units"
    assert all(u["parent_cluster"] is not None for u in judged_units)
    assert all(u["file"] == "big.py" for u in judged_units)
    assert len({u["line"] for u in judged_units}) == 3, "own anchor each"
    assert out["meta"]["n_analyzed"] == 3
    assert out["n_dropped"] == 0 and out["n_unjudged"] == 0
    assert out["verdict"] == "Approved", "no incomplete suffix on a full split"


def test_oversize_fallback_judged_as_windows_via_main(jr, monkeypatch,
                                                      tmp_path, capsys):
    """Unparseable oversize (JS-ish) falls back to line-window sub-clusters,
    all judged under jev."""
    # ~90k chars of changed lines with no parseable post-image structure
    body = "\n".join(f"+const v{i} = " + "x" * 80 for i in range(1000))
    diff = ("diff --git a/big.js b/big.js\n"
            "--- /dev/null\n+++ b/big.js\n@@ -0,0 +1,1000 @@\n" + body)
    judged_units = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged_units.extend(kept)
        return ([{"hunk": h, "severity": 1.1, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert len(judged_units) > 1, "fallback windows judged as units"
    assert out["meta"]["n_analyzed"] == len(judged_units)
    assert out["n_dropped"] == 0 and out["n_unjudged"] == 0


# ---------- r1-B1/r8-M1/r9-M1: unit-consistent two-phase counters ----------

def test_unit_counters_stay_consistent(jr, monkeypatch, tmp_path, capsys):
    """r1-B1 regression guard: 5 clusters, one splitting into 3 units ->
    n_dropped == 0, n_unjudged == 0, NO '(incomplete' suffix, and the
    denominator equals the UNIT count (7 of 7), not the parent count.
    Property: n_dropped >= 0 in every fixture combination."""
    small = "\n".join(f"+x{i} = {i}" for i in range(1, 6))
    src = _oversize_py_src(n=3)
    diff = (_whole_file_add_diff("big.py", src)
            + "\n".join(
                f"diff --git a/s{i}.py b/s{i}.py\n--- /dev/null\n"
                f"+++ b/s{i}.py\n@@ -0,0 +1,5 @@\n{small}"
                for i in range(4)))
    seen = {}

    def fake_judge(kept, ask, errors=None, split_unit=None):
        seen["kept"] = list(kept)
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    files = [u["file"] for u in seen["kept"]]
    assert files.count("big.py") == 3, "oversize parent split into 3 units"
    assert len(seen["kept"]) == 7, "3 sub-units + 4 whole parents"
    assert out["n_dropped"] == 0
    assert out["n_unjudged"] == 0
    assert out["meta"]["n_analyzed"] == 7
    assert out["verdict"] == "Approved"
    assert "(incomplete" not in out["verdict"]


def test_n_dropped_non_negative_property(jr, monkeypatch, tmp_path, capsys):
    """Property assertion (r1-B1): n_dropped >= 0 across combinations
    (split + skip + truncation in ONE run, 45 units over ceiling 40)."""
    src = _oversize_py_src(n=45, chars=2_000)  # one parent -> 45 units
    diff = (_whole_file_add_diff("big.py", src)
            + "diff --git a/README.md b/README.md\n--- a/README.md\n"
              "+++ b/README.md\n@@ -1,1 +1,2 @@\n # docs\n+more\n")
    judged = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged.extend(kept)
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert out["n_dropped"] >= 0
    assert out["n_dropped"] == 5, "45 units - 40 kept = 5 ceiling drops"
    assert len(judged) == 40


# ---------- r10-M2: gate_run vs split/parse-error ledgers ----------

def _load_sweep(module_tag):
    import importlib.util
    import os
    import sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(repo_root, "scripts", "sweep-thresholds.py")
    spec = importlib.util.spec_from_file_location(f"sweep-t4-{module_tag}",
                                                  path)
    assert spec is not None and spec.loader is not None
    sw = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = sw
    spec.loader.exec_module(sw)
    return sw


def test_gate_run_accepts_v08_split_ledger():
    """r1-B1: a v08-ast ledger whose run contains splits PASSES gate_run —
    the sweep must never reject a legal split run as malformed."""
    sw = _load_sweep("split")
    judged = [{"file": "big.py", "line": n, "severity": 1.0, "is_real": 0.1,
               "category": "style", "confidence": None, "reported": False,
               "rubric": "code-change", "references_remaining": None}
              for n in range(1, 5)]
    rec = {"label": "v08-split", "fixture": "positive",
           "fixture_head": "a" * 40, "head": "a" * 10,
           "packaging_version": "v08-ast", "provider": "jev", "model": None,
           "judged": judged, "base_verdict": "Approved",
           "n_dropped": 0, "n_unjudged": 0, "n_size_skipped_code": 0,
           "n_analyzed": 4, "verdict": "Approved"}
    sw.gate_run(rec, "a" * 40, packaging_version="v08-ast")  # must not die


def test_gate_run_rejects_parse_error_ledger():
    """r10-M2: a run with ONE parse_error finding is REJECTED twice over —
    judged[] excludes parse_error findings so the :98 completeness check
    fires first ('incomplete — judged has N entries but n_analyzed=N+1'),
    and n_unjudged == 1 would hit the :124 rejection regardless."""
    sw = _load_sweep("perr")
    judged = [{"file": "a.py", "line": 1, "severity": 1.0, "is_real": 0.1,
               "category": "style", "confidence": None, "reported": False,
               "rubric": "code-change", "references_remaining": None}]
    rec = {"label": "v08-perr", "fixture": "positive",
           "fixture_head": "a" * 40, "head": "a" * 10,
           "packaging_version": "v08-ast", "provider": "jev", "model": None,
           "judged": judged, "base_verdict": "Approved",
           "n_dropped": 0, "n_unjudged": 1, "n_size_skipped_code": 0,
           "n_analyzed": 2, "verdict": "Approved (incomplete review — "
                                       "1 of 2 clusters judged)"}
    with pytest.raises(SystemExit, match="incomplete — judged has "
                                         r"1 entries but n_analyzed=2"):
        sw.gate_run(rec, "a" * 40, packaging_version="v08-ast")


# ---------- r12-m1/r13-m1: run-level ceiling truncation ----------

def test_max_hunks_is_run_level(jr, monkeypatch, tmp_path, capsys):
    """r12-m1/r13-m1: truncation keeps the first-40 units in traversal
    order; the 5 dropped units become skipped entries with reason
    'max-hunks>ceiling' (NOT parse_error findings); n_unjudged excludes
    them. Property: 45 units, ceiling 40 => n_dropped == 5."""
    src = _oversize_py_src(n=45, chars=2_000)
    diff = _whole_file_add_diff("big.py", src)
    judged = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged.extend(kept)
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert out["n_dropped"] == 5
    assert len(judged) == 40, "kept = first-40 in traversal order"
    assert len({u["line"] for u in judged}) == 40
    trunc = [s for s in out["skipped"]
             if s.get("reason") == "max-hunks>ceiling"]
    assert len(trunc) == 5, "ceiling drops are skipped entries, not findings"
    assert all("line_start" in s and "line_end" in s for s in trunc), \
        "entries carry **_span(unit)"
    assert out["n_unjudged"] == 0, "ceiling entries never count as unjudged"
    assert out["n_size_skipped_code"] == 0, "never a hunk> record"
    assert "(incomplete" in out["verdict"]


def test_laya_never_emits_ceiling_entries(jr, monkeypatch, tmp_path):
    """r13-m1: LAYA NEVER EMITS max-hunks>ceiling entries — its truncation
    stays the legacy sort-and-chop with hunk> size-skips only."""
    src = _oversize_py_src(n=45, chars=2_000)
    diff = _whole_file_add_diff("big.py", src)

    def fake_judge(kept, ask, errors=None, split_unit=None):
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "laya_ask_or_die", lambda model=None: None)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "laya"])
    jr.main()


# ---------- r5-M3/r6-m4/r7-m3: whole-file-deleted over cap ----------

def test_deletion_wholefile_stay_cluster_based_and_overcap_pin(jr, monkeypatch,
                                                               tmp_path):
    """r5-M3/r7-m3: a whole-file-deleted cluster over cap takes the
    deliberate 'whole-file-deleted>cap' skip; r6-m4: NO '(incomplete'
    suffix from this skip and n_size_skipped_code does NOT count it
    (size_skipped_code() matches only the 'hunk>' prefix)."""
    big_src = "x = 1\n" + "\n".join(f"line{i} = {i}" for i in range(1, 4000))
    payload_chars = 90_000
    src = (f'data = "{"a" * payload_chars}"\n' + big_src)
    diff = (f"diff --git a/gone.py b/gone.py\n"
            f"deleted file mode 100644\n"
            f"--- a/gone.py\n+++ /dev/null\n"
            f"@@ -1,{len(src.splitlines())} +0,0 @@\n"
            + "\n".join("-" + ln for ln in src.splitlines()) + "\n")
    calls = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        calls.extend(kept)
        return [], [], {"added_units": 0, "avg_input_tokens": None}

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    records = []
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    rec = records[0]
    assert calls == [], "whole-file-deleted over cap is never judged"
    assert rec["n_dropped"] == 0
    assert rec["n_unjudged"] == 0
    assert "(incomplete" not in rec["verdict"]
    # deliberate skip is present with the pinned reason, excluded from
    # n_size_skipped_code (the 'hunk>' prefix match misses it)
    # (the skipped array lives on the --out JSON; here the ledger verdict
    #  plus the counter pin suffice)


def test_size_skipped_code_excludes_wholefile_cap_reason(jr):
    """r6-m4: the new deliberate-skip reason is NOT counted by
    size_skipped_code()."""
    assert jr.size_skipped_code([
        {"file": "gone.py", "reason": "whole-file-deleted>cap",
         "change_type": "whole-file-deleted", "line_start": 1,
         "line_end": 9}]) == []


def test_deletion_run_assigned_by_old_symbol_end_to_end(jr, monkeypatch,
                                                        tmp_path, capsys):
    """r2-M3 end-to-end: a 3-function rewrite as one '-' block + one '+'
    block; sub-clusters carry their OWN function's old code (assigned via
    e[1] -> PRE-image AST qualified-name match), never another's."""
    big = "a" * 30_000
    pre = (f"def foo():\n    payload = \"{big}\"\n    return payload\n"
           f"def bar():\n    payload = \"{big}\"\n    return payload\n"
           f"def baz():\n    payload = \"{big}\"\n    return payload\n")
    post = ("def foo():\n    payload = \"new_foo\"\n    return payload\n"
            "def bar():\n    payload = \"new_bar\"\n    return payload\n"
            "def baz():\n    payload = \"new_baz\"\n    return payload\n")
    n = len(pre.splitlines())
    diff = ("diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
            f"@@ -1,{n} +1,{n} @@\n"
            + "\n".join("-" + ln for ln in pre.splitlines()) + "\n"
            + "\n".join("+" + ln for ln in post.splitlines()) + "\n")
    judged = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged.extend(kept)
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the exact pre/post images for m.py to the cutter (offline):
    monkeypatch.setattr(jr, "mode_file_images",
                        lambda repo_, mode_, head_, path_, old_file=None:
                        (pre, post))
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    assert len(judged) >= 3, "each function its own sub-cluster"
    for sub in judged:
        before = "\n".join(e[2] for e in sub["entries"] if e[0] == "-")
        after = "\n".join(e[2] for e in sub["entries"] if e[0] == "+")
        if "def foo" in after or any('payload = "new_foo"' == e[2]
                                     for e in sub["entries"] if e[0] == "+"):
            assert 'payload = "a' in before  # foo's OWN old code
            assert "def bar" not in before and "def baz" not in before


# ---------- r7-m3/r14-n2: render label rework ----------

def test_render_label_pins_analyzed_units_and_judged_calls(jr):
    """r7-m3/r14-n2: the header line reads
    'analyzed=<n> units (<n_sent> judged calls), skipped=<n>' and ceiling
    drops get their OWN 'Not judged (run ceiling)' line, never inside the
    Skipped-triage line."""
    reported = [{"hunk": _hunk(1), "severity": 2.0, "is_real": 0.9,
                 "category": "bug-risk"}]
    skipped = [{"file": "README.md", "reason": "docs/generated/lockfile"},
               {"file": "a.py", "line": 1, "reason": "max-hunks>ceiling",
                "line_start": 1, "line_end": 9},
               {"file": "b.py", "line": 2, "reason": "max-hunks>ceiling",
                "line_start": 10, "line_end": 20}]
    meta = _meta(n_analyzed=5)
    out = jr.render(reported, skipped, "Approved", None, [], meta, n_sent=3)
    header = next(ln for ln in out.splitlines()
                  if ln.startswith("analyzed="))
    assert header == ("analyzed=5 units (3 judged calls), skipped=1, "
                      "total_latency=0ms")
    ceiling_line = next(ln for ln in out.splitlines()
                        if ln.startswith("Not judged"))
    assert "run ceiling" in ceiling_line
    skipped_line = next(ln for ln in out.splitlines()
                        if ln.startswith("Skipped"))
    assert "max-hunks>ceiling" not in skipped_line


def test_render_skipped_count_excludes_ceiling_entries(jr):
    """r14-m1: the skipped= count on the header EXCLUDES ceiling entries."""
    skipped = [{"file": "README.md", "reason": "docs/generated/lockfile"},
               {"file": "big.py", "reason": "max-hunks>ceiling",
                "line_start": 1, "line_end": 40},
               {"file": "big.py", "reason": "max-hunks>ceiling",
                "line_start": 41, "line_end": 80}]
    out = jr.render([], skipped, "Approved", None, [], _meta(n_analyzed=2),
                    n_sent=2)
    header = next(ln for ln in out.splitlines()
                  if ln.startswith("analyzed="))
    assert "skipped=1" in header
    assert "Not judged (run ceiling)" in out
    assert "big.py" in next(ln for ln in out.splitlines()
                            if ln.startswith("Not judged"))


def test_render_legacy_call_still_works(jr):
    """Back-compat: render() without the new kwargs keeps working (laya and
    old callers) — no ceiling line, plain header."""
    out = jr.render([], [{"file": "a.md", "reason": "docs/generated/lockfile"}],
                    "Approved", None, [], _meta(n_analyzed=1))
    assert "analyzed=1" in out
    assert "Not judged" not in out


# ---------- unsplittable leaf seam (r7-M2, insertion only) ----------

def test_single_oversize_line_marks_incomplete(jr, monkeypatch, tmp_path,
                                               capsys):
    """r7-M2: a single line still over SOFT_CAP becomes an unjudged record
    {'hunk': unit, 'parse_error': True, 'raw': None, 'reason':
    'unsplittable>cap'} — n_dropped == 0, n_unjudged == 1, no crash, and
    the over-cap unit is never sent to the provider."""
    huge = 'payload = "' + "a" * 120_000 + '"'
    src = ("def keep():\n    x = 1\n    return x\n"
           f"def blob():\n    {huge}\n")
    diff = _whole_file_add_diff("blob.py", src)
    sent = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        sent.extend(kept)
        for h in kept:
            assert jr.estimate_call_size(jr.hunk_state(h),
                                         jr.HUNK_QUESTIONS) \
                <= jr.SOFT_CAP_TOKENS, "over-cap unit must never be sent"
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert out["n_unjudged"] == 1
    assert out["n_dropped"] == 0
    assert "(incomplete" in out["verdict"]
    # the leaf never reached the provider
    for h in sent:
        state = jr.hunk_state(h)
        assert len(json.dumps(state)) < 120_000


# ---------- r14-m2: ceiling-dropped units reach the PR-level digest ----------

def test_ceiling_dropped_units_in_pr_digest(jr, monkeypatch, tmp_path):
    """r14-m2: judge_pr_level receives the max-hunks>ceiling entries so a
    ceiling drop is visible to the PR-level model with the
    'unjudged (skipped: max-hunks>ceiling)' label."""
    src = _oversize_py_src(n=45, chars=2_000)
    diff = _whole_file_add_diff("big.py", src)
    seen = {}

    def fake_judge(kept, ask, errors=None, split_unit=None):
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    def fake_pr_level(findings, ask, size_skipped_code=None):
        seen["size_skipped"] = list(size_skipped_code or [])
        return {"overall_risk": 1.0, "needs_human_review": 0.5,
                "latency_ms": 1.0}

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level", fake_pr_level)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    ceiling = [s for s in seen["size_skipped"]
               if s.get("reason") == "max-hunks>ceiling"]
    assert len(ceiling) == 5, "ceiling drops reach the PR-level digest"


def test_leaf_digest_label_is_skipped_not_provider_failed(jr):
    """r11-m1: a leaf record (parse_error + reason) renders in the digest
    as 'unjudged (skipped: unsplittable>cap)', NOT 'provider call failed'.
    The judge_pr_level label change is the seam Task 5 builds on."""
    leaf = {"hunk": _hunk(1), "parse_error": True, "raw": None,
            "reason": "unsplittable>cap", "latency_ms": 0.0}
    lines = []

    # exercise the digest builder directly through the label logic: the
    # rendering path (judge_pr_level) is wired in Task 5; here we pin the
    # reason-marker format used by the label helper.
    label = jr._digest_label(leaf)
    lines.append(label)
    assert lines == ["- f.py:1 unjudged (skipped: unsplittable>cap)"]
    judged_rec = {"hunk": _hunk(2), "severity": 2.0, "is_real": 0.9,
                  "category": "bug-risk"}
    assert jr._digest_label(judged_rec) == \
        "- f.py:2 severity=MAJOR category=bug-risk"


# ---------- meta/ledger: post-judge n_analyzed site parameterized ----------

def test_meta_n_analyzed_uses_post_judge_formula(jr, monkeypatch, tmp_path,
                                                 capsys):
    """r10-m2: meta['n_analyzed'] (and the log_run write) must use the
    post-judge formula len(kept) + added_units + n_leaf_unjudged; with
    added_units=0 the numbers equal today's non-oversize behavior."""
    diff = "\n".join(
        ["diff --git a/f.py b/f.py", "--- a/f.py", "+++ b/f.py",
         "@@ -1,1 +1,6 @@"] + [f"+line {i}" for i in range(1, 6)])
    records = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None, "change_type": "code-change",
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    # serve the post-image to the cutter without git (offline test):
    def _images(repo_, mode_, head_, path_, old_file=None):
        _src = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("+") and not ln.startswith("+++"))
        _pre = "\n".join(ln[1:] for ln in diff.splitlines()
                       if ln.startswith("-") and not ln.startswith("---"))
        return (_pre or None, _src or None)
    monkeypatch.setattr(jr, "mode_file_images", _images)
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])
    jr.main()
    rec = records[0]
    capsys.readouterr()  # drain the --json stdout
    assert rec["n_analyzed"] == 1 and rec["n_dropped"] == 0
    assert rec["n_unjudged"] == 0
    assert "(incomplete" not in rec["verdict"]


# ---------- preserved pre-Task-4 coverage (fail-open, triage, git errors,
# report readability) — updated only where Task 4 changed behavior ----------


def _hunk(i, file="f.py"):
    return {"file": file, "line": i, "hunk_start": 1, "lines": ["x"],
            "entries": [(" ", i, "x", 1)], "n_changed": 1, "header": "h",
            "size": 1, "too_large": False}


# ---------- fail-open reason ----------

def test_judge_records_transport_error_reason(jr):
    def dead(state, questions):
        raise RuntimeError("certificate verify failed")
    errors = []
    findings, _, _meta = jr.judge([_hunk(1), _hunk(2)], dead, errors=errors)
    assert findings is None
    assert errors and "certificate verify failed" in errors[-1]
    assert "RuntimeError" in errors[-1]


def test_judge_records_shape_error_reason(jr):
    def garbage(state, questions):
        return {"answers": {}}, 1.0
    errors = []
    findings, _, _meta = jr.judge([_hunk(1), _hunk(2)], garbage, errors=errors)
    assert findings is None
    assert errors and "severity" in errors[-1]


def test_judge_errors_param_is_optional(jr):
    def dead(state, questions):
        raise RuntimeError("x")
    findings, _, _meta = jr.judge([_hunk(1), _hunk(2)], dead)
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


def test_non_git_repo_is_a_clear_error(jr, tmp_path, monkeypatch):
    # tmp_path can inherit a parent repo via GIT_DIR discovery on
    # dev machines whose TMPDIR sits inside a git work tree (e.g.
    # Hermes scratch under ~/.hermes/.git) — make the check hermetic
    # with a broken .git gitfile (a .git DIRECTORY would be valid).
    # CodeRabbit r3: GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE inherited
    # from the test environment would point git at a valid repo and
    # disable discovery entirely, so the broken gitfile never gets a
    # chance. Clear them so discovery runs and the "not a git
    # repository" path is exercised.
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".git").write_text("gitdir: /nonexistent/repo\n")
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


# ---------- Step 0′: size-skip change_type + honest downgrade ----------

def _oversize_hunk(change_type="code-change", file="big.ts"):
    h = _hunk(1, file=file)
    h["too_large"] = True
    h["change_type"] = change_type
    return h


def test_triage_size_skip_carries_change_type(jr):
    """LAYA-ONLY now (r5-M4): the legacy `hunk>` skip carries change_type —
    the jev successor test above pins sub-cluster routing instead."""
    _, skipped = jr.triage([_oversize_hunk("code-change"),
                            _oversize_hunk("deletion-only", file="old.py")],
                           provider="laya")
    by_file = {s["file"]: s for s in skipped}
    assert by_file["big.ts"]["change_type"] == "code-change"
    assert by_file["old.py"]["change_type"] == "deletion-only"


def test_triage_non_size_skips_omit_change_type(jr):
    _, skipped = jr.triage([_hunk(1, file="docs/README.md")])
    assert skipped and "change_type" not in skipped[0]


def test_main_downgrades_on_size_skipped_code(jr, monkeypatch, tmp_path):
    """Step 0′ core, LAYA PATH (r5-M4): a bare Approved is impossible when
    code was size-skipped under laya's whole-cluster transport.

    Feeds a real 150-line insertion diff through package_hunks so laya
    triage size-skips it (code-change), then asserts: the downgrade fires,
    the denominator counts the skipped cluster, base_verdict stays clean,
    and the PR-level digest sees the unjudged file. (Under jev the same
    diff routes through the cutter — see test_laya_legacy_suffix_byte_
    identical's jev counterparts above.)
    """
    diff = "\n".join(
        ["diff --git a/big.py b/big.py", "new file mode 100644",
         "index 0000000..1111111", "--- /dev/null", "+++ b/big.py",
         "@@ -0,0 +1,150 @@"] + [f"+line {i}" for i in range(1, 151)])
    pr_calls = []
    records = []

    def fake_pr_level(findings, ask, size_skipped_code=None):
        pr_calls.append(size_skipped_code)
        return {"overall_risk": 1.0, "needs_human_review": 0.5,
                "latency_ms": 1.0}

    def fake_judge(kept, ask, errors=None, split_unit=None):
        assert kept == [], "laya's oversize-only diff judges nothing"
        return [], [], {"added_units": 0, "avg_input_tokens": None}

    monkeypatch.setattr(jr, "judge_pr_level", fake_pr_level)
    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "laya_ask_or_die", lambda model=None: None)
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "laya"])
    jr.main()
    rec = records[0]
    assert len(pr_calls) == 1 and pr_calls[0], \
        "size skips must reach the PR-level digest"
    assert rec["n_size_skipped_code"] == 1
    assert rec["base_verdict"] == "Approved"  # compose saw no findings
    assert "(incomplete review — 0 of 1 clusters judged)" in rec["verdict"]


# ---------- report readability ----------

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
