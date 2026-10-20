"""--input: line model and diff synthesis (Task 2).

synthesize_file_diff must produce what real `git diff` produces (modulo `index`
lines and the function context git appends after the second `@@`), and the
packager must parse it identically. git is used here only to build the oracle.
"""

import os
import random
import re
import subprocess
import time

import pytest

GIT_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00",
}
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
       "-c", "core.quotePath=false", "-c", "commit.gpgsign=false"]


def git(repo, *args):
    r = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, env=GIT_ENV)
    assert r.returncode == 0, r.stderr.decode()
    return r.stdout.decode("utf-8")


def normalise(diff):
    out = []
    for ln in diff.split("\n"):
        if ln.startswith(("index ", "similarity index")):
            continue
        m = re.match(r"(@@ [^@]*@@)", ln)
        out.append(m.group(1) if m else ln)
    return "\n".join(out)


def put(repo, path, text):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def real_diff(tmp_path, before, after, path="f.txt", old_path=None):
    """git diff of one file between two commits; None sides mean absent."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    put(repo, "keep.txt", "keep\n")
    if before is not None:
        put(repo, old_path or path, before)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "before")
    if old_path:
        (repo / old_path).unlink()
    elif after is None:
        (repo / path).unlink()
    if after is not None:
        put(repo, path, after)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "after")
    return git(repo, "diff", "-M", "--no-ext-diff", "-U3", "HEAD~1", "HEAD")


def mine(jr, before, after, path="f.txt", old_path=None):
    entry = {"path": path, "old_path": old_path, "before": before, "after": after}
    return jr.synthesize_file_diff(entry)[0]


def lines(n, prefix="line"):
    return "".join(f"{prefix}{i}\n" for i in range(n))


def edit(text, idx, new):
    ls = text.split("\n")
    ls[idx] = new
    return "\n".join(ls)


ten = lines(10)
rep = "".join(f"r{i % 3}\n" for i in range(250))  # many repeated lines
base40 = lines(40)

CASES = {
    "add": (None, "a\nb\n"),
    "delete": ("a\nb\n", None),
    "modify": ("a\nb\nc\n", "a\nB\nc\n"),
    "empty_added": (None, ""),
    "empty_deleted": ("", None),
    "empty_to_content": ("", "a\n"),
    "content_to_empty": ("a\nb\n", ""),
    "no_newline_after": ("a\nb\n", "a\nb"),
    "no_newline_before": ("a\nb", "a\nb\n"),
    "no_newline_both_edit": ("a\nb", "a\nc"),
    "no_newline_context": (ten[:-1], edit(ten[:-1], 1, "CHANGED")),
    "only_adds_final_newline": ("a\nb", "a\nb\n"),
    "only_removes_final_newline": ("a\nb\n", "a\nb"),
    "single_line_no_nl_add_nl": ("x", "x\n"),
    "crlf": ("a\r\nb\r\nc\r\n", "a\r\nB\r\nc\r\n"),
    "crlf_to_lf": ("a\r\nb\r\n", "a\nb\n"),
    "repeated_lines_one_change": (rep, edit(rep, 120, "changed")),
    "change_near_start": (base40, edit(base40, 1, "X")),
    "change_at_first_line": (base40, edit(base40, 0, "X")),
    "change_near_end": (base40, edit(base40, 38, "X")),
    "change_at_last_line": (base40, edit(base40, 39, "X")),
    "gap6_merges": (base40, edit(edit(base40, 10, "A"), 17, "B")),
    "gap7_splits": (base40, edit(edit(base40, 10, "A"), 18, "B")),
    "gap8_splits": (base40, edit(edit(base40, 10, "A"), 19, "B")),
    "pure_insert_middle": (base40, base40.replace("line20\n", "line20\nnew\n")),
    "pure_delete_middle": (base40, base40.replace("line20\n", "")),
    "rewrite": (lines(12), lines(15, "other")),
    "u2028_and_formfeed": ("a b\nc\x0cd\ne\n", "a b\nc\x0cd\nE\n"),
    "unicode": ("café\n中文\n", "café\n中文!\n"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_matches_real_git(jr, tmp_path, name):
    before, after = CASES[name]
    want = normalise(real_diff(tmp_path, before, after))
    assert normalise(mine(jr, before, after)) == want


def test_rename_with_edit_matches_git(jr, tmp_path):
    before = lines(30)
    after = edit(before, 15, "changed")
    want = normalise(real_diff(tmp_path, before, after, path="new/n.txt", old_path="old/o.txt"))
    assert "rename from old/o.txt" in want
    assert normalise(mine(jr, before, after, "new/n.txt", "old/o.txt")) == want


def test_pure_rename_is_headers_only(jr, tmp_path):
    before = lines(30)
    want = normalise(real_diff(tmp_path, before, before, path="n.txt", old_path="o.txt"))
    got = mine(jr, before, before, "n.txt", "o.txt")
    assert normalise(got) == want
    assert "---" not in got and "@@" not in got
    assert jr.package_hunks(got) == []


def test_empty_added_and_deleted_have_no_file_markers(jr):
    for before, after in ((None, ""), ("", None)):
        d = mine(jr, before, after)
        assert not any(ln.startswith(("--- ", "+++ ", "@@")) for ln in d.split("\n"))
        assert jr.package_hunks(d) == []


def test_header_ranges_follow_git(jr):
    # ',1' omitted; an empty side is 0,0; a non-empty side is 1-based
    assert "@@ -0,0 +1 @@" in mine(jr, None, "a\n")
    assert "@@ -1 +0,0 @@" in mine(jr, "a\n", None)
    assert "@@ -1 +1 @@" in mine(jr, "a\n", "b\n")
    assert "@@ -0,0 +1,2 @@" in mine(jr, None, "a\nb\n")
    assert "@@ -1,2 +0,0 @@" in mine(jr, "a\nb\n", None)


def test_context_is_three_lines(jr):
    d = mine(jr, base40, edit(base40, 20, "X"))
    assert " line17" in d and " line16" not in d
    assert " line23" in d and " line24" not in d
    assert "@@ -18,7 +18,7 @@" in d


def test_no_newline_marker_once_per_side(jr):
    d = mine(jr, "a\nb", "a\nc")
    assert d.split("\n").count("\\ No newline at end of file") == 2
    assert "-b\n\\ No newline at end of file\n+c\n\\ No newline at end of file\n" in d


def test_final_newline_only_change_is_a_real_change(jr):
    d = mine(jr, "a\nb", "a\nb\n")
    assert "-b\n\\ No newline at end of file\n+b\n" in d
    d = mine(jr, "a\nb\n", "a\nb")
    assert "-b\n+b\n\\ No newline at end of file\n" in d


# ---------- split_lines ----------

@pytest.mark.parametrize("text,want", [
    ("", []),
    ("a", ["a"]),
    ("a\n", ["a\n"]),
    ("a\n\nb", ["a\n", "\n", "b"]),
    ("\n", ["\n"]),
    ("a\r\nb", ["a\r\n", "b"]),
    ("a b\x0cc\n", ["a b\x0cc\n"]),
])
def test_split_lines(jr, text, want):
    assert jr.split_lines(text) == want
    assert "".join(jr.split_lines(text)) == text


# ---------- packager round trip ----------

def test_packager_round_trip(jr):
    after = edit(edit(base40, 5, "ALPHA"), 30, "BETA")
    hunks = jr.package_hunks(mine(jr, base40, after, "src/m.py"))
    assert [h["file"] for h in hunks] == ["src/m.py", "src/m.py"]
    assert [h["line"] for h in hunks] == [6, 31]


def test_packager_multi_file_with_whole_file_and_no_newline(jr):
    entries = [
        {"path": "a.py", "old_path": None, "before": "x\ny\n", "after": "x\nY\n"},
        {"path": "b.py", "old_path": None, "before": None, "after": "n1\nn2"},
        {"path": "c.py", "old_path": None, "before": "gone\n", "after": None},
        {"path": "d.py", "old_path": None, "before": "p\nq", "after": "p\nq\n"},
        {"path": "e.py", "old_path": "old_e.py", "before": "k\n", "after": "k\n"},
    ]
    diff = "".join(jr.synthesize_file_diff(e)[0] for e in entries)
    got = [(h["file"], h["line"]) for h in jr.package_hunks(diff)]
    assert got == [("a.py", 2), ("b.py", 1), ("c.py", 1), ("d.py", 2)]


def test_packager_dash_dash_content_is_not_a_header(jr):
    # a removed line "-- x" renders as "--- x"; the @@ counts keep it content
    d = mine(jr, "a\n-- x\nb\n", "a\nb\n")
    hunks = jr.package_hunks(d)
    assert len(hunks) == 1 and hunks[0]["file"] == "f.txt"


# ---------- build_input ----------

def mkdoc(*files, head="h", repo="r"):
    return {"head": head, "repo": repo, "files": list(files)}


def f(path, before, after, old_path=None):
    return {"path": path, "old_path": old_path, "before": before, "after": after}


def test_build_input_shape_and_order(jr):
    out = jr.build_input(mkdoc(f("z.py", "a\n", "b\n"), f("a.py", None, "n\n"),
                               head="H", repo="R"))
    assert out["head"] == "H" and out["repo"] == "R"
    assert out["skipped"] == [] and out["n_autojunk"] == 0
    assert out["images"] == {"z.py": ("a\n", "b\n"), "a.py": (None, "n\n")}
    assert out["diff"].index("b/z.py") < out["diff"].index("b/a.py")


def test_binary_is_skipped_with_record(jr):
    out = jr.build_input(mkdoc(f("b.bin", "a\0b", "a\0c"), f("ok.py", "a\n", "b\n"),
                               f("c.bin", None, "x\0")))
    assert out["skipped"] == [
        {"file": "b.bin", "reason": "input-binary", "line_start": 1, "line_end": 1},
        {"file": "c.bin", "reason": "input-binary", "line_start": 1, "line_end": 1}]
    assert list(out["images"]) == ["ok.py"]
    assert "b.bin" not in out["diff"] and "ok.py" in out["diff"]


def test_oversize_chars_either_side(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_FILE_CHARS", 10)
    out = jr.build_input(mkdoc(f("big.py", "x" * 11, "y"), f("big2.py", "y", "x" * 11),
                               f("edge.py", "x" * 10, "y" * 10)))
    assert [s["reason"] for s in out["skipped"]] == ["hunk>input-oversize"] * 2
    assert [s["file"] for s in out["skipped"]] == ["big.py", "big2.py"]
    assert list(out["images"]) == ["edge.py"]


def test_oversize_lines_either_side(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_FILE_LINES", 5)
    out = jr.build_input(mkdoc(f("a.py", "1\n" * 6, "1\n"), f("b.py", "1\n", "1\n2\n" * 3),
                               f("c.py", "1\n" * 5, "2\n" * 5)))
    assert [s["file"] for s in out["skipped"]] == ["a.py", "b.py"]
    assert out["skipped"][0] == {"file": "a.py", "reason": "hunk>input-oversize",
                                 "line_start": 1, "line_end": 1}
    assert list(out["images"]) == ["c.py"]


def test_oversize_counts_a_final_unterminated_line(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_FILE_LINES", 5)
    out = jr.build_input(mkdoc(f("a.py", "1\n" * 5 + "x", "1\n")))
    assert [s["file"] for s in out["skipped"]] == ["a.py"]


def test_binary_wins_over_oversize(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_FILE_CHARS", 3)
    out = jr.build_input(mkdoc(f("a.bin", "abcd\0", "x")))
    assert out["skipped"][0]["reason"] == "input-binary"


def test_empty_files_list(jr):
    out = jr.build_input(mkdoc())
    assert out["diff"] == "" and out["skipped"] == [] and out["images"] == {}


def test_n_autojunk_counts_files_over_the_cap(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MATCH_LINES", 10)
    small = f("s.py", lines(5), lines(5, "other"))
    big1 = f("b1.py", lines(11), lines(11, "other"))
    big2 = f("b2.py", lines(3), lines(11, "other"))  # one core over the cap is enough
    assert jr.build_input(mkdoc(small))["n_autojunk"] == 0
    assert jr.build_input(mkdoc(small, big1, big2))["n_autojunk"] == 2
    assert jr.synthesize_file_diff(small)[1] is False
    assert jr.synthesize_file_diff(big1)[1] is True


def test_cap_applies_to_the_core_not_the_file(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MATCH_LINES", 10)
    big = lines(500)
    _, junk = jr.synthesize_file_diff(f("a.py", big, edit(big, 250, "X")))
    assert junk is False


def test_matcher_autojunk_flag_follows_the_cap(jr, monkeypatch):
    seen = []
    real = jr.difflib.SequenceMatcher

    def spy(*args, **kw):
        seen.append(kw.get("autojunk"))
        return real(*args, **kw)

    monkeypatch.setattr(jr.difflib, "SequenceMatcher", spy)
    monkeypatch.setattr(jr, "INPUT_MATCH_LINES", 10)
    jr.synthesize_file_diff(f("a.py", lines(10), lines(10, "o")))
    jr.synthesize_file_diff(f("a.py", lines(11), lines(11, "o")))
    assert seen == [False, True]


def test_autojunk_fallback_diff_is_still_correct(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MATCH_LINES", 10)
    before = "".join(f"u{i}\n" for i in range(60))
    after = before.replace("u30\n", "CHANGED\n")
    # prefix/suffix are stripped, so a single change has a 1-line core: no fallback
    assert jr.synthesize_file_diff(f("a.py", before, after))[1] is False
    a2 = "".join(f"u{i}\n" for i in range(0, 60, 2)) + "end\n"
    b2 = "start\n" + "".join(f"u{i}\n" for i in range(1, 61, 2)) + "end\n"
    text, junk = jr.synthesize_file_diff(f("a.py", a2, b2))
    assert junk is True
    old, new = [], []
    for ln in text.split("\n"):
        if ln.startswith(("--- ", "+++ ", "@@", "diff ")):
            continue
        if ln[:1] in " -":
            old.append(ln[1:])
        if ln[:1] in " +":
            new.append(ln[1:])
    # hunks together must be a faithful patch: applying them reproduces the sides
    assert [x for x in old if x] == [x for x in a2.split("\n") if x]
    assert [x for x in new if x] == [x for x in b2.split("\n") if x]


# ---------- timing ----------

def test_timing_20000_blank_lines_one_change(jr):
    before = "\n" * 20000
    after = "\n" * 9999 + "x\n" + "\n" * 10000
    t = time.perf_counter()
    text, junk = jr.synthesize_file_diff(f("a.txt", before, after))
    elapsed = time.perf_counter() - t
    assert elapsed < 1.0, elapsed
    assert junk is False
    assert "+x" in text


def test_timing_3000_repetitive_lines_mid_shift(jr):
    # two symbols, pseudo-random: a ~3000-line core with no unique anchors
    rnd = random.Random(1)
    before = "".join(rnd.choice("ab") + "\n" for _ in range(3000))
    after = "z\n" + before[:3000] + "q\n" + before[3000:-2]  # shifts the middle
    t = time.perf_counter()
    text, junk = jr.synthesize_file_diff(f("a.txt", before, after))
    elapsed = time.perf_counter() - t
    assert elapsed < 10.0, elapsed
    assert junk is False  # the core is within INPUT_MATCH_LINES: exact matching
    assert text.startswith("diff --git") and "+z\n" in text
