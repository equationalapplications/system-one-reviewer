"""Cluster line span (corpus spec §1): additive line_start/line_end fields.

Cluster matching and miss decomposition need the cluster's window span, not
only its anchor line. Model input is unchanged, so no packaging bump.
"""


def _modify_diff():
    body = "".join(f" l{i}\n" for i in range(1, 6)) + "-old6\n+new6\n" + \
        "".join(f" l{i}\n" for i in range(7, 11))
    return ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
            "@@ -1,10 +1,10 @@\n" + body)


def test_hunk_span_covers_context_window(jr):
    (h,) = jr.package_hunks(_modify_diff())
    assert h["line"] == 6
    # CTX=4 context lines each side: new lines 2..10
    assert (h["line_start"], h["line_end"]) == (2, 10)


def test_deletion_only_span_uses_tracked_new_line(jr):
    diff = ("diff --git a/src/mid.py b/src/mid.py\n--- a/src/mid.py\n"
            "+++ b/src/mid.py\n@@ -5,1 +4,0 @@\n-    dead_call()\n")
    (h,) = jr.package_hunks(diff)
    assert (h["line_start"], h["line_end"]) == (4, 4)


def test_skipped_entries_carry_span(jr):
    hunks = jr.package_hunks(_modify_diff().replace("a.py", "README.md"))
    _, skipped = jr.triage(hunks)
    assert skipped[0]["line_start"] == 2 and skipped[0]["line_end"] == 10


def test_judged_and_findings_carry_span(jr, tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: None)
    monkeypatch.setattr(jr, "set_provider_name", lambda name: None)
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "resolve_diff", lambda r, a: (_modify_diff(), "0" * 40, "m"))

    def fake_judge(kept, ask, errors=None):
        return [{"hunk": h, "severity": 2.6, "is_real": 0.9, "category": "bug-risk",
                 "confidence": 0.8, "rubric": "code-change"} for h in kept], [10.0]
    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None: None)
    out = tmp_path / "out.json"
    monkeypatch.setattr("sys.argv", ["sor", "--repo", str(tmp_path), "--range", "A..B",
                                     "--json", "--out", str(out)])
    jr.main()
    rec = json.loads(open(jr.METRICS_PATH).read().splitlines()[-1])
    assert (rec["judged"][0]["line_start"], rec["judged"][0]["line_end"]) == (2, 10)
    res = json.loads(out.read_text())
    assert (res["findings"][0]["line_start"], res["findings"][0]["line_end"]) == (2, 10)
