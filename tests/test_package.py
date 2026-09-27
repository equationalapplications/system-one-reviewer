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
    """M2 (r2): deletion-only clusters anchor at the position in HEAD where
    the line was removed (the '-' entry's tracked new_line), not the old
    file's line number — the two diverge when earlier lines in the hunk
    changed the count. Hunk `@@ -5,1 +4,0 @@`: HEAD lines 1..3 are shared,
    the deleted line sat before new line 4, so the anchor is 4. Must never
    collapse to the top-of-file fallback 1."""
    diff = (
        "diff --git a/src/mid.py b/src/mid.py\n"
        "--- a/src/mid.py\n"
        "+++ b/src/mid.py\n"
        "@@ -5,1 +4,0 @@\n"
        "-    dead_call()\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    # anchor must fall at the deletion site in HEAD, never fallback 1
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
