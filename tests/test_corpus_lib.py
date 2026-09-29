"""corpus_lib: schema validation, deterministic split, git cache, line checks."""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402

SHA_A, SHA_B = "a" * 40, "b" * 40


def _pr_row(repo, pr, phase, kind, split=None):
    return {"sample_id": cl.sample_id(repo, pr, phase), "repo": repo,
            "base_sha": SHA_A, "head_sha": SHA_B, "kind": kind,
            "split": split or cl.split_for(repo, pr), "source": "fix-pr"}


def _issue(sid, **kw):
    row = {"sample_id": sid, "file": "a.py", "line": "3", "verify_substring": "x",
           "severity_class": "major", "category": "bug-risk", "evidence": "e",
           "fix_sha": SHA_B, "adjudicator": "claude", "spot_checked": "n"}
    row.update(kw)
    return row


def test_sample_id_roundtrip():
    sid = cl.sample_id("o/r", 12, "pre")
    assert sid == "o/r#12@pre"
    assert cl.parse_sample_id(sid) == ("o/r", 12, "pre")
    with pytest.raises(cl.CorpusError):
        cl.parse_sample_id("o/r#12")


def test_split_is_deterministic_and_pr_atomic():
    assert cl.split_for("o/r", 5) == cl.split_for("o/r", 5)
    splits = [cl.split_for("o/r", n) for n in range(1, 401)]
    share = splits.count("holdout") / len(splits)
    assert 0.2 < share < 0.4  # sanity on the hash, not an exact contract


def test_tsv_roundtrip_skips_header_and_comments(tmp_path):
    p = tmp_path / "prs.tsv"
    rows = [_pr_row("o/r", 1, "pre", "positive")]
    cl.write_tsv(str(p), cl.PRS_COLS, rows, comment="generated")
    text = p.read_text()
    assert text.startswith("# generated\n")
    assert cl.read_tsv(str(p), cl.PRS_COLS) == rows


def test_write_tsv_rejects_tabs(tmp_path):
    bad = [_pr_row("o/r", 1, "pre", "positive") | {"source": "a\tb"}]
    with pytest.raises(cl.CorpusError):
        cl.write_tsv(str(tmp_path / "x.tsv"), cl.PRS_COLS, bad)


def _write_corpus(root, prs, issues=(), dismissed=()):
    os.makedirs(root, exist_ok=True)
    cl.write_tsv(os.path.join(root, "prs.tsv"), cl.PRS_COLS, prs)
    cl.write_tsv(os.path.join(root, "issues.tsv"), cl.ISSUE_COLS, list(issues))
    cl.write_tsv(os.path.join(root, "dismissed.tsv"), cl.DISMISSED_COLS, list(dismissed))


def test_load_corpus_merges_local_overlay(tmp_path):
    root = str(tmp_path / "corpus")
    pre = _pr_row("o/r", 1, "pre", "positive")
    _write_corpus(root, [pre], [_issue(pre["sample_id"])])
    priv = _pr_row("o/p", 2, "pre", "clean")
    _write_corpus(os.path.join(root, "local"), [priv])
    c = cl.load_corpus(root)
    assert set(c["prs"]) == {"o/r#1@pre", "o/p#2@pre"}
    assert len(c["issues"]) == 1 and c["dismissed"] == []


def test_load_corpus_empty_dir_is_empty(tmp_path):
    assert cl.load_corpus(str(tmp_path)) == {"prs": {}, "issues": [], "dismissed": []}


@pytest.mark.parametrize("mutate, msg", [
    (lambda prs, iss, dis: prs[0].update(split="holdout" if prs[0]["split"] == "train"
                                         else "train"), "hash split"),
    (lambda prs, iss, dis: prs[0].update(kind="weird"), "kind"),
    (lambda prs, iss, dis: prs[0].update(head_sha="abc"), "40-char"),
    (lambda prs, iss, dis: iss[0].update(sample_id="o/r#9@pre"), "unknown sample"),
    (lambda prs, iss, dis: iss[0].update(line="0"), "bad line"),
    (lambda prs, iss, dis: iss[0].update(severity_class="huge"), "severity_class"),
    (lambda prs, iss, dis: dis[0].update(dismissal_reason="meh"), "dismissal_reason"),
])
def test_validation_errors(tmp_path, mutate, msg):
    pre = _pr_row("o/r", 1, "pre", "positive")
    prs, iss = [pre], [_issue(pre["sample_id"])]
    dis = [_issue(pre["sample_id"], line="7") | {"label": "false-positive",
                                                 "dismissal_reason": "hallucinated"}]
    mutate(prs, iss, dis)
    _write_corpus(str(tmp_path), prs, iss, dis)
    with pytest.raises(cl.CorpusError, match=msg):
        cl.load_corpus(str(tmp_path))


def test_issue_on_clean_sample_rejected(tmp_path):
    fin = _pr_row("o/r", 1, "final", "clean")
    _write_corpus(str(tmp_path), [fin], [_issue(fin["sample_id"])])
    with pytest.raises(cl.CorpusError, match="non-positive"):
        cl.load_corpus(str(tmp_path))


def test_holdout_share_check():
    prs = {}
    for n in range(1, 11):
        r = _pr_row("o/r", n, "pre", "clean")
        prs[r["sample_id"]] = r
    share = sum(r["split"] == "holdout" for r in prs.values()) / 10
    if 0.25 <= share <= 0.35:
        assert cl.check_holdout_share(prs) == share
    else:
        with pytest.raises(cl.CorpusError, match="holdout share"):
            cl.check_holdout_share(prs)
    assert cl.check_holdout_share(dict(list(prs.items())[:3])) is not None  # <10 PRs: no gate


def _git(d, *args):
    subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path):
    d = tmp_path / "origin"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "t")
    (d / "a.py").write_text("one\ntwo\nthree\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "init")
    return d


def test_clone_and_verify_row(tmp_path, origin, monkeypatch):
    monkeypatch.setenv("SOR_CORPUS_CACHE", str(tmp_path / "cache"))
    d = cl.ensure_clone("o/r", url=str(origin))
    assert d == str(tmp_path / "cache" / "o" / "r")
    assert cl.ensure_clone("o/r", url=str(origin)) == d  # idempotent
    sha = cl.git(d, "rev-parse", "HEAD").stdout.strip()
    cl.ensure_commit(d, sha, 1)
    assert cl.verify_row(d, sha, "a.py", 2, "tw") is None
    assert "lacks" in cl.verify_row(d, sha, "a.py", 2, "zzz")
    assert "out of range" in cl.verify_row(d, sha, "a.py", 9, "x")
    assert "missing" in cl.verify_row(d, sha, "nope.py", 1, "x")


def test_ensure_commit_unknown_sha_raises(tmp_path, origin, monkeypatch):
    monkeypatch.setenv("SOR_CORPUS_CACHE", str(tmp_path / "cache"))
    d = cl.ensure_clone("o/r", url=str(origin))
    with pytest.raises(cl.CorpusError, match="not reachable"):
        cl.ensure_commit(d, "c" * 40, 1)
