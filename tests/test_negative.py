"""tests/test_negative.py — m5: the README change is triaged as SKIPPED
(asserted from the built negative fixture's diff — it is never judged),
and benign source changes must be judged without false positives being
impossible by construction (we only assert packaging/triage here; the FP
census is the live runs' job via eval_negative).
"""

import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)


@pytest.fixture(scope="module")
def neg_fixture(tmp_path_factory):
    root = tmp_path_factory.mktemp("neg-fixture") / "repo"
    env = dict(os.environ, JEV_FIXTURE_ROOT=str(root))
    subprocess.run(["bash", os.path.join(REPO_ROOT,
                   "examples/build-negative-fixture.sh")],
                   check=True, capture_output=True, env=env)
    return str(root)


def test_readme_change_is_triaged_skipped(jr, neg_fixture):
    diff = subprocess.run(
        ["git", "-C", neg_fixture, "diff", "HEAD~1..HEAD"],
        capture_output=True, text=True, check=True).stdout
    hunks = jr.package_hunks(diff)
    kept, skipped = jr.triage(hunks)
    readme_files = {h["file"] for h in hunks if h["file"].endswith("README.md")}
    assert readme_files, "fixture diff must contain the README change"
    assert all(s["file"].endswith("README.md") for s in skipped)
    assert all(not h["file"].endswith("README.md") for h in kept)


def test_benign_src_clusters_are_judged(jr, neg_fixture):
    diff = subprocess.run(
        ["git", "-C", neg_fixture, "diff", "HEAD~1..HEAD"],
        capture_output=True, text=True, check=True).stdout
    hunks = jr.package_hunks(diff)
    kept, skipped = jr.triage(hunks)
    assert kept, "benign src changes are triaged IN (they get judged)"
    assert all(os.path.basename(h["file"]) != "README.md" for h in kept)


def test_negative_fixture_contains_whole_file_deletion(jr, neg_fixture):
    """v0.3b (Kurt review): the #45 failure shape — a benign WHOLE-FILE
    deletion — must be present in the negative diff, judged (not triaged
    out), and classified whole-file-deleted. The live FP census now
    exercises the deletion rubric on every negative run."""
    diff = subprocess.run(
        ["git", "-C", neg_fixture, "diff", "HEAD~1..HEAD"],
        capture_output=True, text=True, check=True).stdout
    hunks = jr.package_hunks(diff)
    dels = [h for h in hunks
            if h["change_type"] == "whole-file-deleted"]
    assert len(dels) == 1, "fixture must contain exactly one whole-file deletion"
    assert dels[0]["file"] == "src/format_extra.py"
    kept, skipped = jr.triage(hunks)
    assert dels[0] in kept, "the deletion must be judged, not skipped"
    state = jr.hunk_state(dels[0])
    assert state["references_remaining"] is False  # benign: nothing references it
