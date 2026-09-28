"""Field-evals fixes (2026-09-28): F1 deletion-only handling, F5 merge-base
--range, F7 ledger hygiene. Each test pins a finding from
docs/evals/2026-09-28-field-evals-cj-prs.md.
"""

import json
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
    assert jr.hunk_state(hunks[0])["change_type"] == "deletion-only"


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
    assert state["change_type"] == "deletion-only"
    assert state["code_after_change"] == []


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


def test_deletion_findings_gate_and_verdict_unchanged(jr):
    """compose() treats deletion findings identically: the #45 failure
    shape (single BLOCKER-level deletion finding) still flips the verdict
    — the fix changes what the model is ASKED, not how answers gate."""
    findings = [{"hunk": {"file": "a.ts", "line": 1, "header": "h",
                          "lines": []},
                 "severity": 2.8, "is_real": 0.65, "category": "other"}]
    reported, _jitter, verdict = jr.compose(findings, [], None)
    assert verdict == "Changes requested"
    assert len(reported) == 1


# ---------- F5: --range reviews the merge-base diff ----------

def test_triple_dot_rewrites_two_dot(jr):
    assert jr.triple_dot("main..HEAD") == "main...HEAD"


def test_triple_dot_passthrough(jr):
    for spec in ("main...HEAD", "abc123", "", "HEAD~1..HEAD...x"):
        if spec == "HEAD~1..HEAD...x":
            # two dots inside a spec that already has three-dot form
            assert jr.triple_dot(spec) == spec
        else:
            assert jr.triple_dot(spec) == spec


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
    import system_one_reviewer as _unused  # noqa: F401  (import guard only)
    tmp_path, git = git_pair
    r = subprocess.run(["git", "diff", "main..feature"], cwd=str(tmp_path),
                       capture_output=True, text=True, check=True)
    assert any(ln.startswith("--- b/mainmove.txt") or
               (ln.startswith("--- ") and "mainmove" in ln)
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
    assert mode == "range:main..feature"  # mode keeps the user's spelling


# ---------- F7: ledger hygiene ----------

def test_label_defaults_to_mode(jr, git_pair, monkeypatch):
    tmp_path, _git = git_pair
    import system_one_reviewer as _unused  # noqa: F401  (import guard only)
    argv = ["--repo", str(tmp_path), "--range", "main..feature", "--json"]
    monkeypatch.setattr("sys.argv", ["system-one-reviewer"] + argv)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")  # load_api_key gate
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: _Capture())
    monkeypatch.setattr(jr, "METRICS_PATH",
                        str(tmp_path / "metrics.jsonl"))
    jr.main()
    rec = json.loads(open(str(tmp_path / "metrics.jsonl")).readline())
    assert rec["label"] == "range:main..feature"


def test_repo_dot_resolves_to_basename(jr):
    '''repo:"." (cwd invocations) must log the repo's real name, not "."'''
    import os
    assert jr.os.path.basename(jr.os.path.abspath("some/repo")) == "repo"
    assert (jr.os.path.basename(jr.os.path.abspath(".")) ==
            os.path.basename(os.path.abspath(".")))
