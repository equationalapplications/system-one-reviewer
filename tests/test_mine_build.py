"""mine_corpus spotcheck/build: sampling, owner overrides, gate, TSV generation."""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402
import mine_corpus as mc  # noqa: E402

PRE, FIN, BASE = "1" * 40, "2" * 40, "3" * 40


def _cand(n, pr=1, disp="fixed", path="a.py", repo="o/r"):
    return {"id": f"{repo}#{pr}:T{n}", "repo": repo, "pr": pr,
            "pr_url": f"https://github.com/{repo}/pull/{pr}", "thread_url": f"https://x/T{n}",
            "reviewer": "bot", "body": "b", "path": path, "line": 10 + n,
            "start_line": None, "original_commit": PRE, "base_ref_oid": BASE,
            "head_ref_oid": FIN, "is_outdated": False, "disposition": disp,
            "disposition_source": "fix-pr", "disposition_note": None,
            "fix_sha": FIN if disp == "fixed" else None, "error": None}


def _adj(n, label, pr=1, repo="o/r", **kw):
    row = {"candidate_id": f"{repo}#{pr}:T{n}", "label": label, "severity_class": "major",
           "category": "bug-risk", "evidence": "line 3 | divides by zero",
           "file": "a.py", "line": 10 + n, "verify_substring": "x",
           "dismissal_reason": None if label == "real-bug" else "hallucinated",
           "fixed_at_final": True if label == "real-bug" else None}
    row.update(kw)
    return row


def test_is_disagreement():
    assert mc.is_disagreement("fixed", "false-positive")
    assert mc.is_disagreement("not-applied", "real-bug")
    assert mc.is_disagreement("unaddressed", "real-bug")
    assert not mc.is_disagreement("fixed", "real-bug")
    assert not mc.is_disagreement("unknown", "false-positive")


def test_spotcheck_samples_random_plus_all_disagreements():
    cands = {c["id"]: c for c in [_cand(i) for i in range(10)]}
    adj = [_adj(i, "real-bug") for i in range(9)] + [_adj(9, "false-positive")]
    rows = mc.spotcheck_rows(adj, cands, seed=0, frac=0.2)
    kinds = {r["candidate_id"]: r["why"] for r in rows}
    assert kinds["o/r#1:T9"] in ("disagreement", "random+disagreement")
    assert sum("random" in w for w in kinds.values()) == 2
    assert rows == mc.spotcheck_rows(adj, cands, seed=0, frac=0.2)  # deterministic


def test_spotcheck_markdown_roundtrip(tmp_path):
    cands = {c["id"]: c for c in [_cand(i) for i in range(5)]}
    adj = [_adj(i, "real-bug") for i in range(5)]
    path = str(tmp_path / "spot-check.md")
    mc.write_spot_check(path, mc.spotcheck_rows(adj, cands, seed=0, frac=0.4))
    overrides, notes, agreed, agreement = mc.read_spot_check(path)
    assert agreement is None  # unfilled
    text = open(path).read()
    assert "\\|" in text  # the pipe in evidence is escaped
    lines = text.splitlines()
    filled, first = [], True
    for ln in lines:
        if ln.startswith("| o/r#"):
            cells = mc._cells(ln)
            cells[-3] = "agree" if first else "disagree"
            cells[-2] = "" if first else "false-positive"
            first = False
            ln = "| " + " | ".join(cells) + " |"
        filled.append(ln)
    open(path, "w").write("\n".join(filled) + "\n")
    overrides, notes, agreed, agreement = mc.read_spot_check(path)
    assert agreement == 0.5
    assert list(overrides.values()) == ["false-positive"] and len(agreed) == 1


def _fake_verify_ok(repo, sha, pr, file, line, substring):
    return None


def test_build_rows_pairs_pre_and_final():
    cands = {c["id"]: c for c in [_cand(1), _cand(2, disp="not-applied")]}
    adj = [_adj(1, "real-bug"), _adj(2, "false-positive")]
    out, warnings = mc.build_rows(cands, adj, {}, {}, set(), [], _fake_verify_ok)
    prs, issues, dismissed = out["public"]
    kinds = {r["sample_id"]: r["kind"] for r in prs}
    assert kinds == {"o/r#1@pre": "positive", "o/r#1@final": "clean"}
    pre = next(r for r in prs if r["sample_id"] == "o/r#1@pre")
    assert (pre["head_sha"], pre["base_sha"]) == (PRE, BASE)
    assert pre["split"] == cl.split_for("o/r", 1) and pre["source"] == "fix-pr"
    assert [i["file"] for i in issues] == ["a.py"] and issues[0]["line"] == "11"
    assert dismissed[0]["dismissal_reason"] == "hallucinated"
    assert warnings == []


def test_build_rows_no_real_bug_gives_single_clean_pre():
    cands = {c["id"]: c for c in [_cand(2, disp="not-applied")]}
    out, _ = mc.build_rows(cands, [_adj(2, "false-positive")], {}, {}, set(), [], _fake_verify_ok)
    prs, issues, dismissed = out["public"]
    assert [(r["sample_id"], r["kind"]) for r in prs] == [("o/r#1@pre", "clean")]
    assert issues == [] and len(dismissed) == 1


def test_build_rows_unfixed_bug_drops_final_and_overrides_apply():
    cands = {c["id"]: c for c in [_cand(1), _cand(3)]}
    adj = [_adj(1, "real-bug", fixed_at_final=False), _adj(3, "real-bug")]
    overrides = {"o/r#1:T3": "false-positive"}
    out, _ = mc.build_rows(cands, adj, overrides, {}, {"o/r#1:T1"}, [], _fake_verify_ok)
    prs, issues, dismissed = out["public"]
    assert [r["sample_id"] for r in prs] == ["o/r#1@pre"]
    assert issues[0]["spot_checked"] == "y"
    assert dismissed[0]["adjudicator"] == "human"
    assert dismissed[0]["dismissal_reason"] == "other"  # override without a reason


def test_build_rows_drops_rows_that_fail_verification():
    cands = {c["id"]: c for c in [_cand(1), _cand(4)]}
    adj = [_adj(1, "real-bug"), _adj(4, "real-bug")]

    def verify(repo, sha, pr, file, line, substring):
        return "lacks x" if line == 14 else None
    out, warnings = mc.build_rows(cands, adj, {}, {}, set(), [], verify)
    _, issues, _ = out["public"]
    assert [i["line"] for i in issues] == ["11"]
    assert len(warnings) == 1 and "lacks x" in warnings[0]


def test_build_rows_dedups_same_anchor_prefers_human():
    """Two candidates anchoring the same (file, line): one row, the human's."""
    # T1 and T2 differ only in id; give them the SAME adjudication anchor.
    a1, a2 = _adj(1, "real-bug"), _adj(2, "real-bug")
    a2["file"], a2["line"] = a1["file"], a1["line"]
    cands = {c["id"]: c for c in [_cand(1), _cand(2)]}
    overrides = {"o/r#1:T2": "real-bug"}  # human blessed the T2 copy
    out, warnings = mc.build_rows(cands, [a1, a2], overrides, {}, set(), [],
                                  _fake_verify_ok)
    _, issues, _ = out["public"]
    assert len(issues) == 1
    assert issues[0]["adjudicator"] == "human"
    assert any("duplicate anchor" in w and "T2" in w for w in warnings)


def test_build_rows_dedup_survives_verify_failure_of_preferred_row():
    """The human row fails verify, the claude row at the same anchor passes:
    the anchor must survive via the claude row (dedup runs after verify)."""
    a1, a2 = _adj(1, "real-bug"), _adj(2, "real-bug")
    a2["file"], a2["line"] = a1["file"], a1["line"]
    a1["verify_substring"], a2["verify_substring"] = "x1", "x2"
    cands = {c["id"]: c for c in [_cand(1), _cand(2)]}
    overrides = {"o/r#1:T2": "real-bug"}

    def verify2(repo, sha, pr, file, line, substring):
        return "gone" if substring == "x2" else None  # the HUMAN copy fails

    out, warnings = mc.build_rows(cands, [a1, a2], overrides, {}, set(), [], verify2)
    _, issues, _ = out["public"]
    assert len(issues) == 1
    assert issues[0]["adjudicator"] == "claude"  # the surviving copy
    assert any("dropped" in w for w in warnings)


def test_build_rows_private_repo_goes_local_and_promotions_apply():
    cands = {c["id"]: c for c in [_cand(1, repo="o/p")]}
    adj = [_adj(1, "real-bug", repo="o/p")]
    promo = [{"sample_id": "o/p#1@final", "file": "b.py", "line": 5, "verify_substring": "y",
              "severity_class": "minor", "category": "bug-risk", "evidence": "missed"}]
    out, _ = mc.build_rows(cands, adj, {}, {}, set(), promo, _fake_verify_ok,
                           private={"o/p"})
    assert out["public"] == ([], [], [])
    prs, issues, _ = out["private"]
    fin = next(r for r in prs if r["sample_id"] == "o/p#1@final")
    assert (fin["kind"], fin["source"]) == ("positive", "promoted")
    assert {i["sample_id"] for i in issues} == {"o/p#1@pre", "o/p#1@final"}


def test_build_rows_rejects_bad_adjudication():
    cands = {c["id"]: c for c in [_cand(1)]}
    with pytest.raises(cl.CorpusError, match="dismissal_reason"):
        mc.build_rows(cands, [_adj(1, "false-positive", dismissal_reason=None)], {},
                      {}, set(), [], _fake_verify_ok)
    with pytest.raises(cl.CorpusError, match="unknown candidate"):
        mc.build_rows(cands, [_adj(7, "real-bug")], {}, {}, set(), [], _fake_verify_ok)


def test_build_cli_enforces_spot_check_gate(tmp_path):
    work = tmp_path / "corpus" / "work"
    cl.write_jsonl(str(work / "candidates.jsonl"), [_cand(i) for i in range(4)])
    cl.write_jsonl(str(work / "adjudicated.jsonl"), [_adj(i, "real-bug") for i in range(4)])
    assert mc.main(["build", "--corpus", str(tmp_path / "corpus")]) == 1  # no sheet
    assert mc.main(["spotcheck", "--corpus", str(tmp_path / "corpus")]) == 0
    assert mc.main(["build", "--corpus", str(tmp_path / "corpus")]) == 1  # unfilled
