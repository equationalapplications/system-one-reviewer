"""package_hunks v0.2: per-cluster isolation with hunk-boundary clamping.

Regression core: tests/data/v01-fixture.diff (the v0.1 live fixture, saved
before rebuild) must keep producing the five known anchors.
"""

import os

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _read(name):
    with open(os.path.join(DATA, name)) as f:
        return f.read()


def test_v01_fixture_anchors(jr):
    hunks = jr.package_hunks(_read("v01-fixture.diff"))
    assert [h["line"] for h in hunks] == [11, 14, 17, 20, 26]
    assert all(h["file"] == "src/app.py" for h in hunks)
    assert sum(h["n_changed"] for h in hunks) == 10


def test_deletion_anchor_uses_head_position(jr):
    """M2 (r2) + m5 (r3)/M3 (r4): deletion-only clusters anchor at the
    position in HEAD where the line was removed. Git semantics: for
    `@@ -5,1 +4,0 @@` the new start 4 with count 0 means "the file's 4
    lines end, deletion after line 4" — so the anchor is 4, the last
    existing HEAD line (verified against real `git diff -U0` output).
    Never the old-file line 5, never top-of-file fallback 1, never
    past-EOF 5."""
    diff = (
        "diff --git a/src/mid.py b/src/mid.py\n"
        "--- a/src/mid.py\n"
        "+++ b/src/mid.py\n"
        "@@ -5,1 +4,0 @@\n"
        "-    dead_call()\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    # git semantics: +4,0 = deletion after HEAD line 4 (the last existing)
    assert hunks[0]["line"] == 4
    assert any("dead_call" in ln for ln in hunks[0]["lines"])


def test_deletion_anchor_after_earlier_insertions(jr):
    """M2 (r2) traced example: hunk `@@ -1,8 +1,9 @@` with an insertion
    BEFORE the deletion. The deleted old line 7 sits between new lines 8
    and 9 in HEAD, so the anchor must be 9 (the '-' entry's new_line), not
    7 (old-file line). The earlier +n1/+n2 run packs as its own cluster;
    the deletion cluster is what pins the anchor contract."""
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,8 +1,9 @@\n"
        " l1\n"
        "+n1\n"
        "+n2\n"
        " l2\n"
        " l3\n"
        " l4\n"
        " l5\n"
        " l6\n"
        "-l7\n"
        " l8\n"
    )
    hunks = jr.package_hunks(diff)
    assert [h["line"] for h in hunks] == [2, 9]


def test_windows_never_cross_hunk_boundary(jr):
    diff = (
        "diff --git a/src/two.py b/src/two.py\n"
        "--- a/src/two.py\n"
        "+++ b/src/two.py\n"
        "@@ -1,1 +1,2 @@\n"
        " original_one\n"
        "+added_in_hunk_one\n"
        "@@ -6,2 +7,2 @@\n"
        " context_before\n"
        "-old_line_two\n"
        "+new_line_two\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 2
    second = hunks[1]
    # isolation: no context from hunk one bleeds into the hunk-two cluster
    assert all("hunk_one" not in ln for ln in second["lines"])
    assert second["line"] == 8  # the added line of hunk two, not hunk one's 2
    # clamping metadata: cluster carries its hunk window
    assert second["hunk_start"] == 7


def test_cluster_window_excludes_neighbouring_clusters_changed_lines(jr):
    """E2 / M1: a cluster's ±4 window is trimmed at the neighbouring
    clusters' changed indices, so no neighbour's +/- entry can enter it
    (only shared context lines may appear). On v01-fixture.diff cluster 2
    (anchor 14, the divide plant) must contain no non-space entries of
    cluster 1 (the find_user plant) or cluster 3 (duplicate import)."""
    hunks = jr.package_hunks(_read("v01-fixture.diff"))
    by_line = {h["line"]: h for h in hunks}
    c2 = by_line[14]
    for neighbour_text in ("PLANT 1", "PLANT 3"):
        assert not any(neighbour_text in ln for ln in c2["lines"]), (
            f"cluster 14's window contains neighbour [{neighbour_text}]: "
            f"{c2['lines']}")
    assert c2["n_changed"] == 2
    # general form: every cluster's window holds only its own changed entries
    for h in hunks:
        own = sum(1 for e in h["entries"] if e[0] != " ")
        assert own == h["n_changed"], (
            f"cluster {h['line']}: window has {own} changed entries, "
            f"cluster owns {h['n_changed']}")


def test_package_is_deterministic(jr):
    diff = _read("v01-fixture.diff")
    assert jr.package_hunks(diff) == jr.package_hunks(diff)


def test_trailing_deletion_anchors_inside_file(jr):
    # m5 (r3)/M3 (r4): a deletion at end of file must not anchor past
    # EOF. HEAD has 2 lines; the hunk deletes old lines 3-4 entirely
    # and git emits `@@ -3,2 +2,0 @@` (new start 2, count 0 = "file
    # ends at line 2, deletion after it") — verified against real
    # `git diff -U0` output. Anchor = 2, the last existing line.
    diff = (
        "diff --git a/src/tail.py b/src/tail.py\n"
        "--- a/src/tail.py\n"
        "+++ b/src/tail.py\n"
        "@@ -3,2 +2,0 @@\n"
        "-    dead_one()\n"
        "-    dead_two()\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["line"] == 2  # last existing HEAD line, not 3


def test_multifile_headers_never_leak_into_windows(jr):
    """M3 (r4): git header lines of the SECOND file (index/new file mode/
    deleted file mode/rename...) must not leak into the first file's last
    cluster window as context."""
    diff = (
        "diff --git a/src/one.py b/src/one.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/src/one.py\n"
        "+++ b/src/one.py\n"
        "@@ -1,3 +1,4 @@\n"
        " keep_a\n"
        "+added_a\n"
        " keep_a2\n"
        " keep_a3\n"
        "diff --git a/src/two.py b/src/two.py\n"
        "index 3333333..4444444 100644\n"
        "--- a/src/two.py\n"
        "+++ b/src/two.py\n"
        "@@ -1,2 +1,3 @@\n"
        " keep_b\n"
        "+added_b\n"
        " keep_b2\n"
    )
    hunks = jr.package_hunks(diff)
    one = [h for h in hunks if h["file"] == "src/one.py"]
    two = [h for h in hunks if h["file"] == "src/two.py"]
    assert len(one) == 1 and len(two) == 1
    window_text = " ".join(one[0]["lines"])
    assert "index" not in window_text and "diff --git" not in window_text
    assert all("keep_b" not in ln and "added_b" not in ln
               for ln in one[0]["lines"])


def test_whole_file_deletion_attributed_and_anchored(jr):
    """M3 (r4): a deleted file's hunks must belong to the deleted file
    (+++ /dev/null must not keep the previous file), and anchors must be
    sane (>= 1), never 0 or negative from a +0,0 hunk."""
    diff = (
        "diff --git a/src/gone.py b/src/gone.py\n"
        "deleted file mode 100644\n"
        "index abcdef0..0000000\n"
        "--- a/src/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,3 +0,0 @@\n"
        "-import os\n"
        "-x = 1\n"
        "-y = 2\n"
        "diff --git a/src/stays.py b/src/stays.py\n"
        "index abcdef1..abcdef2 100644\n"
        "--- a/src/stays.py\n"
        "+++ b/src/stays.py\n"
        "@@ -1,1 +1,2 @@\n"
        " keep\n"
        "+added\n"
    )
    hunks = jr.package_hunks(diff)
    gone = [h for h in hunks if h["file"] == "src/gone.py"]
    stays = [h for h in hunks if h["file"] == "src/stays.py"]
    assert len(gone) == 1, "deleted file's cluster is missing or misfiled"
    assert gone[0]["line"] >= 1, "anchor must never be 0/negative"
    assert all("import os" in ln or "x = 1" in ln or "y = 2" in ln
               for ln in gone[0]["lines"] if ln.strip().startswith(("-", "0", "1", "2", "3")))
    assert len(stays) == 1
    assert all("gone" not in ln for ln in stays[0]["lines"])


def test_content_looking_like_headers_inside_hunk_is_judged(jr):
    """M2 (r5): inside a hunk, a removed line whose text starts with `-- `
    renders as `--- ...` and an added line starting with `++ ` renders as
    `+++ ...`. These are CONTENT (SQL/Lua comments, diff-like text), not
    file headers — the parser must judge them, not swallow them."""
    diff = (
        "diff --git a/src/query.sql b/src/query.sql\n"
        "--- a/src/query.sql\n"
        "+++ b/src/query.sql\n"
        "@@ -1,4 +1,4 @@\n"
        " SELECT 1;\n"
        "--- drop the audit guard\n"
        "+++ counter\n"
        " SELECT 2;\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1, "header-lookalike content must still form a cluster"
    h = hunks[0]
    assert h["n_changed"] == 2
    assert any("drop the audit guard" in ln for ln in h["lines"])
    assert any("+ counter" in ln or "counter" in ln for ln in h["lines"])
    # line accounting survived: the context line after both must be line 2
    assert h["line"] == 2  # first '+' content line, new-file line 2


def test_renamed_file_reported_under_new_path(jr):
    """M1 (r6): a renamed+edited file must be reported under its NEW path —
    line numbers are HEAD-side, and golden matching compares paths."""
    diff = (
        "diff --git a/src/old.py b/src/new.py\n"
        "similarity index 90%\n"
        "rename from src/old.py\n"
        "rename to src/new.py\n"
        "--- a/src/old.py\n"
        "+++ b/src/new.py\n"
        "@@ -1,2 +1,3 @@\n"
        " keep\n"
        "+added\n"
        " keep2\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["file"] == "src/new.py"


def test_plain_unified_diff_without_git_header_still_parses(jr):
    """m2 (r6): hand-built unified diffs with no `diff --git` line must
    still parse (v0.1 behavior)."""
    diff = (
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,1 +1,2 @@\n"
        " keep\n"
        "+added\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["file"] == "a/x.py" or hunks[0]["file"] == "x.py"


def test_run_git_diff_flags_produce_parseable_output(jr, tmp_path):
    """B1 (r7): run_git's pinned diff invocation must actually run — flags
    after the subcommand — and its output must parse with real anchors.
    Runs against a real throwaway git repo (the r7 blocker was invisible
    to string-diff tests because nothing executed run_git)."""
    import subprocess as sp
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a, cwd=None):
        return sp.run(["git", "-C", str(cwd or repo), *a], capture_output=True,
                      text=True, check=True).stdout
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (repo / "app.py").write_text("one\ntwo\nthree\n")
    g("add", "-A"); g("commit", "-qm", "base")
    (repo / "app.py").write_text("one\nTWO!\nthree\nfour\n")
    g("add", "-A"); g("commit", "-qm", "head")
    diff = jr.run_git(str(repo), "diff", "HEAD~1..HEAD")
    hunks = jr.package_hunks(diff)
    # two separate change runs: the edit at line 2 and the addition at line 4
    assert [h["line"] for h in hunks] == [2, 4]
    assert all(h["file"] == "app.py" for h in hunks)  # a/ b/ prefixes stripped
    assert any("TWO!" in ln for h in hunks for ln in h["lines"])
    assert any("four" in ln for h in hunks for ln in h["lines"])


def test_plain_multifile_unified_diff_parses_both_files(jr):
    """m1 (r7): a plain multi-file unified diff (no `diff --git` lines)
    must attribute each file's hunks correctly — content-lookalike
    headers INSIDE a hunk's declared counts stay content (r5 case)."""
    diff = (
        "--- a/x.sql\n"
        "+++ b/x.sql\n"
        "@@ -1,3 +1,3 @@\n"
        " SELECT 1;\n"
        "--- drop the audit guard\n"
        "+++ counter\n"
        " SELECT 2;\n"
        "--- a/y.py\n"
        "+++ b/y.py\n"
        "@@ -1,1 +1,2 @@\n"
        " keep\n"
        "+added\n"
    )
    hunks = jr.package_hunks(diff)
    xsql = [h for h in hunks if h["file"] == "x.sql"]
    ysql = [h for h in hunks if h["file"] == "y.py"]
    # the r5 content case must remain content of x.sql...
    assert xsql and any("audit guard" in ln for h in xsql for ln in h["lines"])
    # ...and the second file must be its own cluster
    assert len(ysql) == 1 and ysql[0]["line"] == 2
    assert any("added" in ln for ln in ysql[0]["lines"])


def test_shape_errors_reach_fail_open(jr):
    """M1 (r8): parse/shape failures must count toward the fail-open
    limit even when the transport call itself succeeds — an API that
    returns HTTP 200 with a wrong body must end in fail-open (None),
    never a silent 'Approved'. Needs 2+ hunks: the limit is 2 consecutive
    failures."""
    def mk_hunk(i):
        return {"file": "f.py", "line": i, "hunk_start": 1, "lines": ["x"],
                "entries": [(" ", i, "x", 1)], "n_changed": 1, "header": "h",
                "size": 1, "too_large": False}
    hunks = [mk_hunk(1), mk_hunk(2)]
    calls = []

    def bad_ask(state, questions):
        calls.append(1)
        return {"answers": {}}, 1.0  # transport OK, answers shape wrong

    findings, _lat = jr.judge(hunks, bad_ask)
    assert findings is None, "consecutive shape errors must trigger fail-open"
    assert len(calls) == jr.CALL_FAIL_LIMIT


def test_diff_ruN_separator_never_becomes_context(jr):
    """m1 (r8): after a hunk's counts are exhausted, a `diff -ruN ...`
    separator line must be ignored, not appended as fake context."""
    diff = (
        "--- a/x.txt\n"
        "+++ b/x.txt\n"
        "@@ -1,1 +1,2 @@\n"
        " keep\n"
        "+added\n"
        "diff -ruN a/y.txt b/y.txt\n"
        "--- a/y.txt\n"
        "+++ b/y.txt\n"
        "@@ -1,1 +1,2 @@\n"
        " keep2\n"
        "+added2\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 2
    assert all(h["file"] in ("x.txt", "y.txt") for h in hunks)
    for h in hunks:
        assert not any("diff -ruN" in ln for ln in h["lines"]), \
            "separator line leaked into a window"


def test_gnu_diff_timestamp_headers_do_not_pollute_filenames(jr):
    """m3 (r9): GNU diff -u headers carry a tab + timestamp after the path;
    the path must be split at the first tab, not just right-trimmed."""
    diff = (
        "--- a/x.py\t2026-09-27 12:00:00 +0000\n"
        "+++ b/x.py\t2026-09-27 12:00:00 +0000\n"
        "@@ -1,1 +1,2 @@\n"
        " keep\n"
        "+added\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["file"] == "x.py", "timestamp must not ride on the name"


def test_fail_open_run_verdicts_unavailable_end_to_end(jr, tmp_path, capsys,
                                                       monkeypatch):
    """M1 (r9): end to end through main(), a run whose provider never
    answers must carry verdict 'Unavailable...', never 'Approved' — in
    the JSON, the report, and the metrics last line."""
    import json as _json
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"], ["add", "-A"],
                ["commit", "-qm", "head"]):
        import subprocess as sp
        sp.run(["git", "-C", str(repo), *cmd], check=True,
               capture_output=True)

    def dead_transport(state, questions):
        raise RuntimeError("provider down")

    # M2 (r10): main() calls make_provider(), which OVERWRITES the module
    # transport — the fake must be injected there, or the test would hit
    # the real API (it passed for the wrong reason via DNS/401 failure).
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: dead_transport)
    monkeypatch.setattr(jr, "set_provider_name", lambda name: None)

    from types import SimpleNamespace
    args = SimpleNamespace(
        repo=str(repo), range="HEAD", pr=None, staged=False,
        uncommitted=False, out=None, max_hunks=40, golden=None,
        negative_golden=None, fixture=None, label="unavail-test",
        provider="jev", model=None, json=True)

    diff_text = (
        "diff --git a/f.py b/f.py\n"
        "--- a/f.py\n"
        "+++ b/f.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x = 1\n"
        "+x = 2\n"
    )
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo_, a: (diff_text, "0" * 40, "test"))
    monkeypatch.setattr(jr, "load_api_key", lambda: "test-key")
    (tmp_path / "m").mkdir()
    # METRICS_PATH is captured at import time; patch the constant itself.
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "m" / "metrics.jsonl"))
    monkeypatch.setattr("sys.argv", [
        "system-one-reviewer", "--repo", str(repo), "--range", "HEAD",
        "--label", "unavail-test", "--json", "--provider", "jev"])
    rc = jr.main()
    out = capsys.readouterr().out
    assert rc is None  # main() returns None on success
    assert "Unavailable" in out
    # M2 (r10): also assert the metrics record, per the docstring promise.
    import json as _json
    rec = _json.loads(open(str(tmp_path / "m" / "metrics.jsonl")).readlines()[-1])
    assert rec["fail_open"] is True
    assert "Unavailable" in rec["verdict"]


def _ok_payload(state, questions):
    """A healthy provider response for any hunk (ask(state, questions))."""
    return ({"answers": {
        "severity": {"score": 2, "probabilities": None, "confidence": "high"},
        "is_real_issue": {"noul": True},
        "category": {"choice": "correctness", "probabilities": None}}}, 1.0)


def test_triage_skips_do_not_trigger_incomplete_downgrade(jr, tmp_path,
                                                          capsys,
                                                          monkeypatch):
    """M1 (r10): a deliberate triage skip (docs/lockfile) is NOT a dropped
    cluster — a run that judged every kept cluster stays a clean
    'Approved', with no 'incomplete review' downgrade."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"], ["add", "-A"],
                ["commit", "-qm", "head"]):
        import subprocess as sp
        sp.run(["git", "-C", str(repo), *cmd], check=True,
               capture_output=True)

    diff_text = (
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1,1 +1,2 @@\n"
        " # docs\n"
        "+more docs\n"
        "diff --git a/f.py b/f.py\n"
        "--- a/f.py\n"
        "+++ b/f.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x = 1\n"
        "+x = 2\n"
    )
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo_, a: (diff_text, "0" * 40, "test"))
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: _ok_payload)
    monkeypatch.setattr(jr, "load_api_key", lambda: "test-key")
    (tmp_path / "m").mkdir()
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "m" / "metrics.jsonl"))
    monkeypatch.setattr("sys.argv", [
        "system-one-reviewer", "--repo", str(repo), "--range", "HEAD",
        "--label", "triage-clean-test", "--json", "--provider", "jev"])
    jr.main()
    out = capsys.readouterr().out
    assert '"verdict": "Approved"' in out, out
    assert "incomplete" not in out


def test_jev_ask_4xx_costs_exactly_one_request(jr, monkeypatch):
    """M1 (r11): a 401/403 must NOT be retried. r10's fix raised inside
    the try whose except swallowed it — the request went out twice. A
    fake connection counts request() calls; 5xx DOES retry (2 total)."""
    class FakeResp:
        def __init__(self, status):
            self.status = status
        def read(self):
            return b'{"error": "nope"}'

    class FakeConn:
        def __init__(self, status):
            self.status = status
            self.calls = 0
        def request(self, *a, **k):
            self.calls += 1
        def getresponse(self):
            return FakeResp(self.status)

    for status, expected_calls in ((401, 1), (403, 1), (500, 2)):
        conn = FakeConn(status)
        monkeypatch.setattr(jr, "_get_conn", lambda c=conn: c)
        try:
            jr.jev_ask({"s": 1}, [], "test-key")
            raise AssertionError(f"HTTP {status} should raise")
        except Exception:
            pass
        assert conn.calls == expected_calls, (
            f"HTTP {status}: expected {expected_calls} request(s), "
            f"got {conn.calls}")


def test_render_last_line_is_closed_set(jr):
    """M2 (r11): the grep last line must be exactly one of the four
    status values for EVERY verdict, including 'Changes requested
    (incomplete ...)'."""
    f = {"hunk": {"file": "a.py", "line": 1, "header": "@@ -1 +1,2 @@",
                  "lines": ["+x = 2"]},
         "severity": 3.0, "is_real": True, "category": "correctness"}
    meta = {"repo": "r", "mode": "range", "head": "0" * 40, "provider": "jev",
            "model": None, "n_analyzed": 1,
            "total_latency_ms": 0.0, "jev_calls": 1, "fail_open": False}
    allowed = {"Approved", "Changes requested", "Unavailable", "Incomplete"}
    for verdict in ("Approved", "Changes requested",
                    "Approved (incomplete review — 0 of 1 clusters judged)",
                    "Changes requested (incomplete review — 0 of 2 clusters judged)",
                    "Unavailable — provider failed (fail-open)"):
        text = jr.render([f] if verdict.startswith(("Approved", "Changes"))
                         else [], [], verdict, None, [], meta)
        last = text.splitlines()[-1]
        assert last in allowed, f"{verdict!r} -> last line {last!r}"


def test_render_and_meta_carry_provider(jr, tmp_path, capsys, monkeypatch):
    """M3 (r11): meta must carry provider/model, and render() must name
    the right stack (laya runs were labelled jev). Uses the jev transport
    stub so no laya package is needed; the provider fields are what's
    under test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "f.py").write_text("x = 1\n")
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"], ["add", "-A"],
                ["commit", "-qm", "head"]):
        import subprocess as sp
        sp.run(["git", "-C", str(repo), *cmd], check=True,
               capture_output=True)
    diff_text = (
        "diff --git a/f.py b/f.py\n"
        "--- a/f.py\n"
        "+++ b/f.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x = 1\n"
        "+x = 2\n"
    )
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo_, a: (diff_text, "0" * 40, "test"))
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: _ok_payload)
    monkeypatch.setattr(jr, "load_api_key", lambda: "test-key")
    (tmp_path / "m").mkdir()
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "m" / "metrics.jsonl"))
    monkeypatch.setattr("sys.argv", [
        "system-one-reviewer", "--repo", str(repo), "--range", "HEAD",
        "--label", "meta-test", "--json", "--provider", "jev"])
    # render() with a laya meta must name the stack, not fall back to jev
    text = jr.render([], [], "Approved", None, [],
                     {"repo": "r", "mode": "range", "head": "0" * 40,
                      "provider": "laya", "model": "m1", "n_analyzed": 0,
                      "total_latency_ms": 0.0, "jev_calls": 0,
                      "fail_open": False})
    assert "provider: laya/m1" in text
    jr.main()
    out = capsys.readouterr().out
    assert '"provider": "jev"' in out
    assert '"model": null' in out  # JSON null, not Python None
