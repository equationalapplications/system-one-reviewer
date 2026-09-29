"""mine_corpus fetch: GraphQL → candidates, /fix-pr dispositions, fix detection.

gh is never called: gh_graphql is monkeypatched with canned responses shaped
like the live query (Task 3 Step 1). Git checks run against temp repos.
"""

import collections
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402
import mine_corpus as mc  # noqa: E402

FIXPR = (
    "## /fix-pr follow-up\n\n"
    "**Commit:** `25b830d`\n\n"
    "### Review resolution\n"
    "- **Draft-release recovery (`@semantic-release/github`)** — **Fixed.** "
    "Added recover_release.py (files: `.github/workflows/ci.yml`)\n"
    "- **`scripts/build_release.py:45` \"file opened in a try block\"** — "
    "**Not applied.** False positive; `with` closes on every path.\n"
    "- **Round 1 topic** — **Fixed in 25b830d.** (Already covered.)\n"
)


def _thread(tid, path, line, commit="c" * 40, side="RIGHT", author="coderabbitai",
            body="bug here", start=None):
    return {"id": tid, "isOutdated": False, "path": path, "line": None,
            "originalLine": line, "startLine": None, "originalStartLine": start,
            "diffSide": side,
            "comments": {"nodes": [{"author": {"login": author}, "body": body,
                                    "url": f"https://x/{tid}",
                                    "originalCommit": {"oid": commit}}]}}


def _pr(number, threads, comments=()):
    return {"number": number, "url": f"https://github.com/o/r/pull/{number}",
            "baseRefOid": "b" * 40, "headRefOid": "d" * 40,
            "comments": {"nodes": [{"author": {"login": "me"}, "body": c}
                                   for c in comments]},
            "reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": threads}}


def test_parse_fixpr_bullets():
    b = mc.parse_fixpr_bullets(FIXPR)
    assert [s for s, _ in b] == ["fixed", "not-applied", "fixed"]
    assert "build_release.py" in b[1][1]
    assert mc.parse_fixpr_bullets("just a comment") == []


def test_match_bullet_unique_basename_only():
    b = mc.parse_fixpr_bullets(FIXPR)
    assert mc.match_bullet("scripts/build_release.py", b)[0] == "not-applied"
    assert mc.match_bullet(".github/workflows/ci.yml", b)[0] == "fixed"
    assert mc.match_bullet("src/other.py", b) is None
    dup = b + [("fixed", "- **also build_release.py** — **Fixed.**")]
    assert mc.match_bullet("scripts/build_release.py", dup) is None  # ambiguous


def test_candidates_use_original_line_and_skip_unanchorable():
    pr = _pr(7, [
        _thread("T1", "scripts/build_release.py", 45, start=44),
        _thread("T2", "a.py", 3, side="LEFT"),          # comment on removed line
        _thread("T3", "b.py", None),                     # file-level comment
    ], comments=[FIXPR])
    cands, stats = mc.candidates_from_pr("o/r", pr)
    assert [c["id"] for c in cands] == ["o/r#7:T1"]
    c = cands[0]
    assert (c["line"], c["start_line"], c["original_commit"]) == (45, 44, "c" * 40)
    assert (c["disposition"], c["disposition_source"]) == ("not-applied", "fix-pr")
    assert stats == {"left_side": 1, "no_line": 1, "no_commit": 0, "threads_truncated": 0}


def test_candidate_without_fixpr_match_is_unknown():
    cands, _ = mc.candidates_from_pr("o/r", _pr(8, [_thread("T9", "z.py", 2)]))
    assert cands[0]["disposition"] == "unknown" and cands[0]["disposition_source"] is None


def test_old_side_touches():
    diff = "@@ -10,2 +10,3 @@\n-a\n+b\n@@ -40,0 +41,1 @@\n+c\n"
    assert mc.old_side_touches(diff, 11)
    assert mc.old_side_touches(diff, 13)           # within slack 2 of 10..11
    assert not mc.old_side_touches(diff, 20)
    assert mc.old_side_touches(diff, 41)           # pure insertion after 40, slack
    assert not mc.old_side_touches(diff, 44)


def _git(d, *args):
    return subprocess.run(["git", "-C", str(d), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_first_fix_commit(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "t")
    (d / "a.py").write_text("".join(f"line{i}\n" for i in range(1, 31)))
    _git(d, "add", "-A"); _git(d, "commit", "-q", "-m", "c0")  # noqa: E702
    c0 = _git(d, "rev-parse", "HEAD")
    (d / "other.py").write_text("x\n")
    _git(d, "add", "-A"); _git(d, "commit", "-q", "-m", "unrelated")  # noqa: E702
    text = (d / "a.py").read_text().replace("line20\n", "fixed20\n")
    (d / "a.py").write_text(text)
    _git(d, "add", "-A"); _git(d, "commit", "-q", "-m", "fix")  # noqa: E702
    fix = _git(d, "rev-parse", "HEAD")
    assert mc.first_fix_commit(str(d), c0, fix, "a.py", 20) == fix
    assert mc.first_fix_commit(str(d), c0, fix, "a.py", 5) is None


def test_fetch_writes_candidates(tmp_path, monkeypatch):
    pages = iter([
        {"data": {"repository": {"pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [_pr(7, [_thread("T1", "a.py", 3)])]}}}},
    ])
    monkeypatch.setattr(mc, "gh_graphql", lambda query, **v: next(pages))
    monkeypatch.setattr(cl, "ensure_clone", lambda repo, url=None: str(tmp_path))
    monkeypatch.setattr(cl, "ensure_commit", lambda path, sha, pr: None)
    monkeypatch.setattr(mc, "first_fix_commit", lambda *a: "e" * 40)
    corpus = tmp_path / "corpus"
    assert mc.main(["fetch", "--repo", "o/r", "--corpus", str(corpus)]) == 0
    (c,) = cl.read_jsonl(str(corpus / "work" / "candidates.jsonl"))
    assert (c["disposition"], c["disposition_source"], c["fix_sha"]) == \
        ("fixed", "thread-fix", "e" * 40)


def test_fetch_resumes_cached_repos(tmp_path, monkeypatch):
    """A repo mined earlier is not re-queried; a failing later repo keeps the first."""
    calls = []

    def fake_mine(repo, limit):
        calls.append(repo)
        if repo == "o/boom":
            raise cl.CorpusError("gh api graphql failed: HTTP 504")
        cands, _ = mc.candidates_from_pr(repo, _pr(7, [_thread("T1", "a.py", 3)]))
        return cands, {"prs": 1}

    monkeypatch.setattr(mc, "mine_repo", fake_mine)
    corpus = tmp_path / "corpus"
    argv = ["fetch", "--repo", "o/ok", "--repo", "o/boom", "--corpus", str(corpus)]
    assert mc.main(argv) == 1
    assert calls == ["o/ok", "o/boom"]
    # The successful repo survives the failure in its per-repo cache.
    assert len(cl.read_jsonl(str(corpus / "work" / "candidates" / "o__ok.jsonl"))) == 1
    assert not os.path.exists(str(corpus / "work" / "candidates.jsonl"))

    # Re-running skips the cached repo and retries only the failed one.
    calls.clear()
    assert mc.main(argv) == 1
    assert calls == ["o/boom"]


def test_fetch_force_remines(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(mc, "mine_repo", lambda repo, limit: (
        calls.append(repo), ([], {"prs": 0}))[1])
    corpus = tmp_path / "corpus"
    argv = ["fetch", "--repo", "o/r", "--corpus", str(corpus)]
    mc.main(argv)
    mc.main(argv)
    assert calls == ["o/r"]
    mc.main(argv + ["--force"])
    assert calls == ["o/r", "o/r"]


def test_fetch_retries_errored_cache_but_stops(tmp_path, monkeypatch):
    """Errored caches re-mine ERROR_RETRY_LIMIT times, then stay cached.

    Run 1: initial mine (error) -> attempts 0. Run 2: error retry 1 ->
    attempts 1. Run 3: error retry 2 -> attempts 2 (limit). Run 4: limit
    reached — cache reused with a warning, no re-mine.
    """
    calls = []

    def fake_mine(repo, limit):
        calls.append(1)
        c, _ = mc.candidates_from_pr(repo, _pr(7, [_thread("T1", "a.py", 3)]))
        c[0]["error"] = "permanent: commit gone"
        return c, {"prs": 1}

    monkeypatch.setattr(mc, "mine_repo", fake_mine)
    corpus = tmp_path / "corpus"
    argv = ["fetch", "--repo", "o/r", "--corpus", str(corpus)]
    mc.main(argv)  # initial mine
    mc.main(argv)  # error retry 1
    assert len(calls) == 2
    mc.main(argv)  # error retry 2 — limit now reached
    assert len(calls) == 3
    mc.main(argv)  # cached, warning printed
    assert len(calls) == 3


def test_graphql_retries_transient_then_succeeds(monkeypatch):
    outs = [subprocess.CompletedProcess([], 1, "", "gh: HTTP 504"),
            subprocess.CompletedProcess([], 0, '{"data": {"ok": 1}}', "")]
    slept = []
    monkeypatch.setattr(mc.subprocess, "run", lambda *a, **k: outs.pop(0))
    assert mc.gh_graphql("Q", owner="o", _sleep=slept.append) == {"data": {"ok": 1}}
    assert slept == [2]


def test_graphql_does_not_retry_permanent_error(monkeypatch):
    outs = [subprocess.CompletedProcess([], 1, "", "gh: could not resolve to a Repository")]
    slept = []
    monkeypatch.setattr(mc.subprocess, "run", lambda *a, **k: outs.pop(0))
    with pytest.raises(cl.CorpusError, match="could not resolve"):
        mc.gh_graphql("Q", owner="o", _sleep=slept.append)
    assert slept == []


def test_graphql_gives_up_after_retries(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mc.subprocess, "run",
        lambda *a, **k: (calls.append(1),
                          subprocess.CompletedProcess([], 1, "", "HTTP 504"))[1])
    with pytest.raises(cl.CorpusError, match="504"):
        mc.gh_graphql("Q", owner="o", _sleep=lambda d: None)
    assert len(calls) == len(mc.RETRY_DELAYS) + 1


# ---------- sample ----------


def _cand(repo, pr, tid, **kw):
    c = {"id": f"{repo}#{pr}:{tid}", "repo": repo, "pr": pr, "path": "a.py",
         "line": 3, "disposition": "fixed", "error": None}
    c.update(kw)
    return c


def _pool(n_prs, per_pr, repo="o/a"):
    return [_cand(repo, p, f"T{i}") for p in range(n_prs) for i in range(per_pr)]


def test_sample_is_pr_atomic():
    """Every drawn PR is included whole: no PR is partially labeled."""
    picked = mc.sample_candidates(_pool(10, 5), target=20)
    by_pr = collections.defaultdict(list)
    for c in picked:
        by_pr[c["pr"]].append(c)
    assert picked
    assert all(len(v) == 5 for v in by_pr.values())


def test_sample_is_deterministic_and_seed_sensitive():
    pool = _pool(20, 3)
    assert mc.sample_candidates(pool, 20, seed=0) == mc.sample_candidates(pool, 20, seed=0)
    assert mc.sample_candidates(pool, 20, seed=0) != mc.sample_candidates(pool, 20, seed=1)


def test_sample_gives_every_repo_a_quota():
    """A big repo cannot swallow the draw and starve the small ones."""
    pool = _pool(50, 20, "o/big") + _pool(4, 2, "o/small")
    picked = mc.sample_candidates(pool, target=30)
    per_repo = collections.Counter(c["repo"] for c in picked)
    assert set(per_repo) == {"o/big", "o/small"}
    assert per_repo["o/small"] == 8  # all 8 findings: the quota floor is one PR
    assert per_repo["o/big"] <= 30


def test_sample_quotas_split_remainder():
    assert mc.repo_quotas(["a", "b", "c"], 10) == {"a": 4, "b": 3, "c": 3}
    assert mc.repo_quotas(["a", "b"], 3) == {"a": 2, "b": 1}


def test_sample_skips_errored_candidates():
    pool = _pool(3, 2) + [_cand("o/a", 99, "TX", error="boom")]
    picked = mc.sample_candidates(pool, target=100)
    assert all(c["id"] != "o/a#99:TX" for c in picked)


def test_sample_excludes_whole_pr_with_any_error():
    """PR-atomic rule holds for partially-errored PRs: no half-sampled PRs."""
    pool = _pool(3, 2) + [_cand("o/a", 99, "TX", error="boom"),
                          _cand("o/a", 99, "TY")]
    picked = mc.sample_candidates(pool, target=100)
    assert all(c["pr"] != 99 for c in picked)


def test_sample_redistributes_unused_quota():
    """Small repos that run dry hand their quota back; target is approximated."""
    # 1 finding-PR vs 50 finding-PRs: the small repo exhausts its quota
    # immediately, so its unused share must flow to the big one.
    pool = _pool(50, 1, "o/big") + _pool(1, 1, "o/small")
    picked = mc.sample_candidates(pool, target=20)
    by_repo = collections.Counter(c["repo"] for c in picked)
    assert by_repo["o/small"] == 1
    assert by_repo["o/big"] == 19
    assert sum(by_repo.values()) == 20


def test_sample_pass2_fills_gap_pass1_cannot():
    """Pass 2 is load-bearing: without it the draw falls short of target.

    a: 4 PRs x 1 finding, b: 1 PR x 1 finding, target 5.
    Quotas: a=3 (remainder), b=2. Pass 1: a draws 3 PRs (n=3 >= quota;
    one undrawn PR remains), b draws its only PR and runs dry at 1 < 2.
    used = 4 < 5, so unused = 1: only a pass-2 draw of a's last PR
    (1 finding <= 1) reaches the target. Deleting pass 2 fails this test.
    """
    pool = _pool(4, 1, "o/a") + _pool(1, 1, "o/b")
    picked = mc.sample_candidates(pool, target=5)
    by_repo = collections.Counter(c["repo"] for c in picked)
    by_pair = collections.Counter((c["repo"], c["pr"]) for c in picked)
    assert len(picked) == 5                     # target reached
    assert by_repo["o/a"] == 4 and by_repo["o/b"] == 1
    assert all(v == 1 for v in by_pair.values())  # whole PRs, no duplicates


def test_sample_pass2_never_exceeds_target():
    """The greedy fill skips PRs that would overshoot the remaining budget."""
    # a: 2 PRs x 5 findings; b: 2 PRs x 1 finding; target 6.
    # Pass 1: a=3, b=3 -> a draws PR#0 (5 >= 3), b draws both (2 < 3, dry).
    # used = 7 >= 6 -> pass 2 skipped; overshoot is pass-1 granularity.
    # Now target 8: quotas a=4, b=4: same draws, used = 7 < 8, unused = 1;
    # every undrawn PR (a's PR#1, 5 findings) is bigger than 1 -> skipped.
    pool = _pool(2, 5, "o/a") + _pool(2, 1, "o/b")
    picked = mc.sample_candidates(pool, target=8)
    by_pair = collections.Counter((c["repo"], c["pr"]) for c in picked)
    assert sum(len(by_pr_map) for by_pr_map in [by_pair]) == len(by_pair)
    assert len(picked) == 7  # 5 + 1 + 1: unused=1 unfillable, not overshot


def test_sample_writes_file_and_reports(tmp_path, capsys):
    corpus = tmp_path / "corpus"
    cl.write_jsonl(str(corpus / "work" / "candidates.jsonl"),
                   _pool(6, 2, "o/a") + _pool(3, 2, "o/b"))
    assert mc.main(["sample", "--target", "8", "--corpus", str(corpus)]) == 0
    picked = cl.read_jsonl(str(corpus / "work" / "sample.jsonl"))
    assert picked == sorted(picked, key=lambda c: c["id"])
    out = capsys.readouterr().out
    assert "findings from" in out and "o/a:" in out and "o/b:" in out


def test_sample_without_candidates_errors(tmp_path):
    assert mc.main(["sample", "--corpus", str(tmp_path / "corpus")]) == 1
