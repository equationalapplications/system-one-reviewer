"""Field-evals fixes (2026-09-28): F1 deletion-only handling, F5 merge-base
--range, F7 ledger hygiene. Each test pins a finding from
docs/evals/2026-09-28-field-evals-cj-prs.md.
"""

import json
import os
import subprocess

import pytest


# ---------- F1: change_type detection ----------

def _whole_file_deletion_diff():
    return (
        "diff --git a/src/old-thing.ts b/src/old-thing.ts\n"
        "deleted file mode 100644\n"
        "--- a/src/old-thing.ts\n"
        "+++ /dev/null\n"
        "@@ -1,3 +0,0 @@\n"
        "-export const A = 1\n"
        "-export const B = 2\n"
        "-export const C = 3\n"
    )


def _addition_diff():
    return (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,1 +1,2 @@\n"
        " import os\n"
        "+import sys\n"
    )


def test_deletion_only_cluster_flagged(jr):
    hunks = jr.package_hunks(_whole_file_deletion_diff())
    assert len(hunks) == 1
    # v0.3b: +++ /dev/null ⇒ whole-file-deleted (three-valued change_type)
    assert jr.hunk_state(hunks[0])["change_type"] == "whole-file-deleted"


def test_infile_deletion_is_deletion_only_not_whole_file(jr):
    """Three-valued change_type (v0.3b, Kurt review): an in-file removal
    is deletion-only; whole-file-deleted is reserved for +++ /dev/null."""
    diff = (
        "diff --git a/src/nine.py b/src/nine.py\n"
        "--- a/src/nine.py\n"
        "+++ b/src/nine.py\n"
        "@@ -1,3 +1,2 @@\n"
        " line1\n"
        "-dead_middle()\n"
        " line4\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["change_type"] == "deletion-only"


def test_addition_cluster_not_flagged(jr):
    hunks = jr.package_hunks(_addition_diff())
    assert len(hunks) == 1
    assert jr.hunk_state(hunks[0])["change_type"] == "code-change"


def test_mixed_cluster_not_flagged(jr):
    """A cluster with both - and + keeps code semantics: there IS
    surviving code to judge."""
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-import os\n"
        "+import sys\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert jr.hunk_state(hunks[0])["change_type"] == "code-change"


# ---------- F1: deletion-adapted questions reach the model ----------

class _Capture:
    """Fake provider that records (state, questions) and returns a fixed
    valid answer payload."""

    def __init__(self, severity=1.0, is_real=0.2):
        self.calls = []
        self.severity = severity
        self.is_real = is_real

    def __call__(self, state, questions):
        self.calls.append((state, questions))
        payload = {"answers": {
            "severity": {"score": self.severity,
                         "probabilities": None, "confidence": 0.9},
            "is_real_issue": {"noul": self.is_real},
            "category": {"choice": "other", "probabilities": None},
        }}
        return payload, 1.0


def test_deletion_only_cluster_gets_deletion_questions(jr):
    cap = _Capture(severity=2.8, is_real=0.65)
    jr.judge(jr.package_hunks(_whole_file_deletion_diff()), cap)
    state, questions = cap.calls[0]
    assert questions is jr.DELETION_QUESTIONS
    assert state["change_type"] == "whole-file-deleted"
    assert state["code_after_change"] == []
    # v0.3b: the deterministic cross-file signal rides in the state
    assert "references_remaining" in state


def test_code_cluster_gets_generic_questions(jr):
    cap = _Capture()
    jr.judge(jr.package_hunks(_addition_diff()), cap)
    _state, questions = cap.calls[0]
    assert questions is jr.HUNK_QUESTIONS


def test_deletion_question_set_same_shape(jr):
    """The deletion set must satisfy the identical response contract
    (same question keys and types) so judge()/compose() need no
    special-casing."""
    assert set(jr.DELETION_QUESTIONS) == set(jr.HUNK_QUESTIONS)
    for q in ("severity", "is_real_issue", "category"):
        assert (jr.DELETION_QUESTIONS[q]["type"]
                == jr.HUNK_QUESTIONS[q]["type"])


def test_deletion_verdict_requires_corroboration(jr):
    """v0.3b corroboration rule (the F1 proposal, now implemented): the
    #45 failure shape — a lone, uncorroborated deletion BLOCKER — is
    REPORTED but cannot unilaterally flip the verdict."""
    findings = [{"hunk": {"file": "a.ts", "line": 1, "header": "h",
                          "lines": []},
                 "severity": 2.8, "is_real": 0.75, "category": "other",
                 "rubric": "deletion", "references_remaining": False}]
    reported, _jitter, verdict = jr.compose(findings, [], None)
    assert verdict == "Approved"          # no unilateral flip
    assert len(reported) == 1             # but the human still sees it


def test_deletion_verdict_flips_when_corroborated(jr):
    """Corroboration paths: references_remaining=True (deterministic grep
    hit) or a reported CODE-CHANGE finding. Deletion findings do NOT
    corroborate each other (v0.3b M2 fix: #45 had six wrong together)."""
    def _finding(refs, rubric="deletion", file="a.ts"):
        return {"hunk": {"file": file, "line": 1, "header": "h", "lines": []},
                "severity": 2.8, "is_real": 0.75, "category": "other",
                "rubric": rubric, "references_remaining": refs}
    _, _j, v1 = jr.compose([_finding(True)], [], None)
    assert v1 == "Changes requested"      # grep says code still references it
    second = _finding(False, rubric="code-change", file="b.py")
    _, _j, v2 = jr.compose([_finding(False), second], [], None)
    assert v2 == "Changes requested"      # corroborated by a code-change finding


def test_two_uncorroborated_deletions_do_not_flip(jr):
    """v0.3b M2 fix (Opus): the gate covers the 2-MAJOR path too — two
    uncorroborated deletion findings at MAJOR severity must NOT reach
    'Changes requested' via len(majors) >= 2 (#45 had six clusters)."""
    def _major(file):
        return {"hunk": {"file": file, "line": 1, "header": "h", "lines": []},
                "severity": 2.0, "is_real": 0.75, "category": "bug-risk",
                "rubric": "deletion", "references_remaining": False}
    reported, _j, verdict = jr.compose([_major("a.ts"), _major("b.ts")],
                                       [], None)
    assert verdict == "Approved"
    assert len(reported) == 2             # both still visible to the human


def test_deletion_major_verdict_eligible_when_corroborated(jr):
    """m5 (Opus): corroborated deletion findings are verdict-eligible —
    two corroborated deletion MAJORs DO reach 'Changes requested'. The
    gate is about corroboration, not severity. (A lone corroborated
    MAJOR still doesn't flip — the 2-MAJOR majority rule is unchanged.)"""
    def _major(file):
        return {"hunk": {"file": file, "line": 1, "header": "h",
                         "lines": []},
                "severity": 2.0, "is_real": 0.75, "category": "bug-risk",
                "rubric": "deletion", "references_remaining": True}
    _, _j, v_one = jr.compose([_major("a.ts")], [], None)
    assert v_one == "Approved"            # lone MAJOR: majority rule unchanged
    _, _j, v_two = jr.compose([_major("a.ts"), _major("b.ts")], [], None)
    assert v_two == "Changes requested"   # corroborated, majority met


def test_deletion_rubric_uses_own_threshold(jr):
    """Two rubrics, two thresholds (v0.3b): a deletion finding at is_real
    0.6 — above the code-change 0.50 gate — must NOT be reported; the
    deletion gate is 0.70 until its own sweep says otherwise."""
    findings = [{"hunk": {"file": "a.ts", "line": 1, "header": "h",
                          "lines": []},
                 "severity": 2.0, "is_real": 0.60, "category": "bug-risk",
                 "rubric": "deletion", "references_remaining": False}]
    reported, _jitter, _verdict = jr.compose(findings, [], None)
    assert reported == []


# ---------- F5: --range reviews the merge-base diff ----------

def test_triple_dot_rewrites_two_dot(jr):
    assert jr.triple_dot("main..HEAD") == "main...HEAD"


def test_triple_dot_passthrough(jr):
    for spec in ("main...HEAD", "abc123", "", "HEAD~1..HEAD...x"):
        assert jr.triple_dot(spec) == spec


def test_triple_dot_fills_open_sides_with_head(jr):
    """r1 minor 2 (Opus v0.3 review): open-ended two-dot ranges were
    passed through unchanged, keeping the stale-base two-dot semantics
    F5 set out to remove."""
    assert jr.triple_dot("main..") == "main...HEAD"
    assert jr.triple_dot("..feature") == "HEAD...feature"


@pytest.fixture
def git_pair(tmp_path):
    """Repo where main moves AFTER a branch forks — a stale base."""
    def git(*a, cwd=None):
        r = subprocess.run(["git", *a], cwd=cwd or str(tmp_path),
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    for name in ("base.txt",):
        (tmp_path / name).write_text("base\n")
    git("add", "-A"); git("commit", "-qm", "base")
    git("checkout", "-qb", "feature")
    (tmp_path / "feat.txt").write_text("feat\n")
    git("add", "-A"); git("commit", "-qm", "feat")
    git("checkout", "-q", "main")
    (tmp_path / "mainmove.txt").write_text("main moved\n")
    git("add", "-A"); git("commit", "-qm", "main move")
    return tmp_path, git


def test_range_reviews_merge_base(jr, git_pair):
    """On a stale base, A..B shows main's new file as a deletion;
    A...B (merge-base) must not."""
    tmp_path, git = git_pair
    diff = jr.run_git(str(tmp_path), "diff", jr.triple_dot("main..feature"))
    changed = [ln for ln in diff.splitlines()
               if ln.startswith(("+++", "---"))]
    assert any("feat.txt" in ln for ln in changed)
    assert not any("mainmove" in ln for ln in changed), diff


def test_stale_base_two_dot_would_show_false_deletion(git_pair):
    """Documents the bug F5 fixes: the two-dot form DOES contain the
    main-side file as a deletion (this is what misled v0.2's --range)."""
    tmp_path, git = git_pair
    r = subprocess.run(["git", "diff", "main..feature"], cwd=str(tmp_path),
                       capture_output=True, text=True, check=True)
    assert any(ln.startswith("--- ") and "mainmove" in ln
               for ln in r.stdout.splitlines())


def test_resolve_diff_range_uses_merge_base(jr, git_pair, monkeypatch):
    """resolve_diff() --range path passes the merge-base spec to git."""
    tmp_path, _git = git_pair
    seen = {}
    real_run_git = jr.run_git

    def spy(repo, *args):
        if args and args[0] == "diff":
            seen["spec"] = args[1]
        return real_run_git(repo, *args)
    monkeypatch.setattr(jr, "run_git", spy)
    args = type("A", (), {"range": "main..feature", "staged": False,
                          "uncommitted": False, "pr": None})()
    _diff, _head, mode = jr.resolve_diff(str(tmp_path), args)
    assert seen["spec"] == "main...feature"
    assert mode == "range:main...feature"  # mode records the diffed spec


# ---------- F7: ledger hygiene ----------

def test_main_wires_label_repo_and_version(jr, git_pair, monkeypatch):
    """F7 end-to-end: empty --label logs auto:<mode> (v0.3b marker so a
    short sweep prefix can't collide); repo records the target's realpath
    basename through the real main() wiring.
    (Supersedes test_label_defaults_to_mode and the os.path-only
    test_repo_dot_resolves_to_basename — r2 minors 3+4.)"""
    tmp_path, _git = git_pair
    argv = ["--repo", str(tmp_path), "--range", "main..feature", "--json"]
    monkeypatch.setattr("sys.argv", ["system-one-reviewer"] + argv)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")  # load_api_key gate
    monkeypatch.delenv("SOR_PROVIDER", raising=False)  # r2 minor 5: keep
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: _Capture())
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "metrics.jsonl"))
    jr.main()
    rec = json.loads(open(str(tmp_path / "metrics.jsonl")).readline())
    assert rec["label"] == "auto:range:main...feature"
    assert rec["repo"] == tmp_path.name
    assert rec["packaging_version"] == "v03b"


def test_infile_deletion_with_context_is_deletion_only(jr):
    """M1 (Opus v0.3 review): change_type must key on the cluster's own
    run, not the after-state — context lines survive in HEAD and must not
    flip an in-file removal into 'code-change'."""
    diff = (
        "diff --git a/src/nine.py b/src/nine.py\n"
        "--- a/src/nine.py\n"
        "+++ b/src/nine.py\n"
        "@@ -1,5 +1,4 @@\n"
        " line1\n"
        " line2\n"
        "-dead_middle()\n"
        " line4\n"
        " line5\n"
    )
    hunks = jr.package_hunks(diff)
    assert len(hunks) == 1
    assert hunks[0]["change_type"] == "deletion-only"
    state = jr.hunk_state(hunks[0])
    assert state["change_type"] == "deletion-only"
    assert state["code_after_change"]     # context survives; state is honest
    assert any("dead_middle" in b for b in state["code_before_change"])
    # v0.3b: 'dead_middle' appears in no surviving line here, but line4/line5
    # don't mention it either — references_remaining must be a real bool
    assert state["references_remaining"] is False


def test_references_remaining_true_when_context_mentions_removed(jr):
    """v0.3b deterministic corroboration: a surviving context line that
    still references the removed symbol flips references_remaining True —
    that is the gate that lets a deletion finding drive the verdict."""
    diff = (
        "diff --git a/src/nine.py b/src/nine.py\n"
        "--- a/src/nine.py\n"
        "+++ b/src/nine.py\n"
        "@@ -1,4 +1,2 @@\n"
        " line1\n"
        "-def dead_middle():\n"
        "-    return 0\n"
        " result = dead_middle()  # survives, still calls it\n"
    )
    hunks = jr.package_hunks(diff)
    state = jr.hunk_state(hunks[0])
    assert state["change_type"] == "deletion-only"
    assert state["references_remaining"] is True


def test_mode_records_diffed_spec(jr, git_pair):
    """r1 minor 3 (Opus v0.3 review): the mode string must carry the
    merge-base spec actually diffed, not the user's two-dot spelling."""
    tmp_path, _git = git_pair
    args = type("A", (), {"range": "main..feature", "staged": False,
                          "uncommitted": False, "pr": None})()
    _diff, _head, mode = jr.resolve_diff(str(tmp_path), args)
    assert mode == "range:main...feature"


def test_bare_range_spec_rejected_loudly(jr, git_pair):
    """Opus v03b r2 M1: triple_dot passes bare specs through; resolve_diff
    must sys.exit with a clear message, not IndexError."""
    tmp_path, _git = git_pair
    args = type("A", (), {"range": "abc123", "staged": False,
                          "uncommitted": False, "pr": None})()
    with pytest.raises(SystemExit, match="right-hand tip"):
        jr.resolve_diff(str(tmp_path), args)


def test_ledger_fields_reach_sweep_replay(jr, git_pair, monkeypatch):
    """Opus v03b r2 B1 / r3 M2 / r4 M2: judged entries in metrics.jsonl
    must carry rubric/references_remaining AND the deletion rubric must
    actually be exercised — the feature branch DELETES lines from a file
    that exists on main, so the merge-base diff contains a deletion-only
    cluster. Replay goes through the real sweep module."""
    tmp_path, git = git_pair
    # code_mod.py exists on MAIN; feature merges main, then removes lines
    code = tmp_path / "code_mod.py"
    code.write_text("import os\n\nvalue = compute(1)\nflag = True\n")
    git("add", "code_mod.py")
    git("commit", "-qm", "add code_mod on main")
    git("checkout", "-q", "feature")
    git("merge", "-q", "--no-edit", "main")  # feature now has code_mod.py
    code.write_text("import os\n\nvalue = compute(1)\n")
    git("add", "-A")
    git("commit", "-qm", "drop dead flag from code_mod")

    argv = ["--repo", str(tmp_path), "--range", "main..feature", "--json"]
    monkeypatch.setattr("sys.argv", ["system-one-reviewer"] + argv)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.delenv("SOR_PROVIDER", raising=False)
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: _Capture())
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "metrics.jsonl"))
    jr.main()
    rec = json.loads(open(str(tmp_path / "metrics.jsonl")).readline())
    assert rec["judged"], "fixture must produce judged code hunks"
    deletion = [j for j in rec["judged"] if j["rubric"] == "deletion"]
    assert deletion, "the code_mod.py removal must be deletion-rubric"
    assert all(isinstance(j["references_remaining"], bool)
               for j in deletion)
    # replay through the sweep's real module, run-level version passed
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sweep", os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts", "sweep-thresholds.py"))
    assert spec is not None and spec.loader is not None
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    for j in rec["judged"]:
        w = sw.rewrap(j, run_version=rec["packaging_version"])
        assert w["rubric"] == j["rubric"]
        assert w["references_remaining"] == j["references_remaining"]


def test_rewrap_dies_on_broken_v03b_record():
    """Opus v03b r4 M1: the v03b rubric gate is RUN-level — a v03b run
    whose judged entries lack `rubric` must die loudly in rewrap."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sweep", os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "scripts", "sweep-thresholds.py"))
    assert spec is not None and spec.loader is not None
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    bad = {"file": "gone.ts", "line": 1, "severity": 2.8, "is_real": 0.75}
    with pytest.raises(SystemExit, match="no rubric"):
        sw.rewrap(bad, run_version="v03b")
    # pre-v03b record without rubric: replays as code-change, no error
    w = sw.rewrap(dict(bad), run_version="v02")
    assert w["rubric"] == "code-change"


def test_sweep_rewrap_passes_rubric_fields(jr):
    """Opus v03b r2 B1 (unit level): rewrap() in scripts/sweep-thresholds
    forwards rubric/references_remaining so replay matches live compose.
    (Uses the jr fixture's isolated import for compose — Opus r3 m4.)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sweep", os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))),
            "scripts", "sweep-thresholds.py"))
    assert spec is not None and spec.loader is not None
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    rec = {"file": "gone.ts", "line": 1, "severity": 2.8, "is_real": 0.75,
           "category": "other", "rubric": "deletion",
           "references_remaining": False}
    w = sw.rewrap(rec, run_version="v03b")
    assert w["rubric"] == "deletion"
    assert w["references_remaining"] is False
    # and compose() applies the deletion gate: 0.75 >= 0.70 → reported,
    # but uncorroborated → verdict NOT flipped
    reported, _, verdict = jr.compose([w], [], None)
    assert len(reported) == 1 and verdict == "Approved"


def test_references_remaining_relative_imports(jr):
    """Opus v03b r4 M3 / r3 M1 regression: relative imports must NOT
    produce empty or root-less names that make \\b\\b match everything."""
    def _diff(removed):
        return (
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1,4 +1,3 @@\n"
            " import os\n"
            f"-{removed}\n"
            " value = compute(1)\n"
        )
    for removed in ("from .utils import helper",
                    "from . import helper",
                    "from ..pkg import helper"):
        hunks = jr.package_hunks(_diff(removed))
        state = jr.hunk_state(hunks[0])
        # surviving context mentions none of the removed module names
        assert state["references_remaining"] is False, removed
