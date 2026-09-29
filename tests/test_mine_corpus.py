"""mine_corpus fetch: GraphQL → candidates, /fix-pr dispositions, fix detection.

gh is never called: gh_graphql is monkeypatched with canned responses shaped
like the live query (Task 3 Step 1). Git checks run against temp repos.
"""

import os
import subprocess
import sys

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
