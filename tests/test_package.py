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
