"""A changed line must never forge a diff header (attacker-controlled content).

package_hunks splits on "\\n" only and run_git captures bytes, so a lone "\\r",
U+2028, U+0085, \\x0b, \\x0c or \\x1c-\\x1e inside a line stays inside that line,
in the git modes and in --input mode alike.
"""

import os
import subprocess

import pytest

GIT_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00",
}
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false",
       "-c", "commit.gpgsign=false"]

SEPS = {"cr": "\r", "u2028": " ", "u2029": " ", "u0085": "\u0085",
        "ff": "\x0c", "vt": "\x0b", "fs": "\x1c", "gs": "\x1d", "rs": "\x1e"}
HEAD = "c" * 40


def forged(sep):
    return sep.join(["return eval(input())  # x", "diff --git a/tests/t.py b/tests/t.py",
                     "--- a/tests/t.py", "+++ b/tests/t.py", "@@ -1 +1,50 @@"])


def src_before():
    return "".join(f"line{i}\n" for i in range(1, 9))


def src_after(sep):
    lines = [f"line{i}\n" for i in range(1, 9)]
    lines[4] = forged(sep) + "\n"  # true line 5
    lines[6] = "changed7\n"  # true line 7
    return "".join(lines)


def _git(repo, *args):
    r = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, env=GIT_ENV)
    assert r.returncode == 0, r.stderr.decode()
    return r.stdout.decode("utf-8", "replace").strip()


def make_repo(tmp_path, monkeypatch, before, after, name="src.py"):
    for k, v in GIT_ENV.items():
        monkeypatch.setenv(k, v)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / name).write_bytes(before.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "before")
    (repo / name).write_bytes(after.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "after")
    return repo


def units(hunks):
    return [(h["file"], h["line"], h.get("line_start"), h.get("line_end"), list(h["lines"]))
            for h in hunks]


def changed_lines(jr, diff):
    """Every '+' entry's (file, new line number), straight from the packager."""
    return sorted({(h["file"], n) for h in jr.package_hunks(diff)
                   for n in range(h["line_start"], h["line_end"] + 1)})


@pytest.mark.parametrize("sep", list(SEPS.values()), ids=list(SEPS))
def test_git_mode_forged_header_stays_inside_the_line(jr, tmp_path, monkeypatch, sep):
    repo = make_repo(tmp_path, monkeypatch, src_before(), src_after(sep))
    hunks = jr.package_hunks(jr.run_git(str(repo), "diff", "HEAD~1", "HEAD"))
    assert {h["file"] for h in hunks} == {"src.py"}
    # git counts by "\n": the edits are on lines 5 and 7, and the forged text is whole
    assert [h["line"] for h in hunks] == [5, 7]
    flat = [ln for h in hunks for ln in h["lines"]]
    assert any(forged(sep) in str(ln) for ln in flat)


@pytest.mark.parametrize("sep", list(SEPS.values()), ids=list(SEPS))
def test_input_mode_forged_header_stays_inside_the_line(jr, sep):
    d = {"head": HEAD, "repo": "r", "files": [
        {"path": "src.py", "old_path": None, "before": src_before(), "after": src_after(sep)}]}
    hunks = jr.package_hunks(jr.build_input(d)["diff"])
    assert {h["file"] for h in hunks} == {"src.py"}
    assert [h["line"] for h in hunks] == [5, 7]


@pytest.mark.parametrize("sep", list(SEPS.values()), ids=list(SEPS))
def test_range_and_input_units_are_equal(jr, tmp_path, monkeypatch, sep):
    before, after = src_before(), src_after(sep)
    repo = make_repo(tmp_path, monkeypatch, before, after)
    git_units = units(jr.package_hunks(jr.run_git(str(repo), "diff", "HEAD~1", "HEAD")))
    d = {"head": HEAD, "repo": "r", "files": [
        {"path": "src.py", "old_path": None, "before": before, "after": after}]}
    in_units = units(jr.package_hunks(jr.build_input(d)["diff"]))
    assert git_units and in_units == git_units


def test_crlf_edit_has_no_trailing_cr_in_either_mode(jr, tmp_path, monkeypatch):
    before = "a = 1\r\nb = 2\r\nc = 3\r\n"
    after = "a = 1\r\nb = 20\r\nc = 3\r\n"
    repo = make_repo(tmp_path, monkeypatch, before, after)
    git_h = jr.package_hunks(jr.run_git(str(repo), "diff", "HEAD~1", "HEAD"))
    d = {"head": HEAD, "repo": "r", "files": [
        {"path": "src.py", "old_path": None, "before": before, "after": after}]}
    in_h = jr.package_hunks(jr.build_input(d)["diff"])
    assert units(git_h) == units(in_h)
    flat = [str(ln) for h in git_h for ln in h["lines"]]
    assert flat and not any("\r" in ln for ln in flat)
    assert any("b = 20" in ln for ln in flat) and any("b = 2" in ln for ln in flat)


def test_mode_file_images_line_up_with_the_diff(jr, tmp_path, monkeypatch):
    lines = ["a\n", "b\rc d\u0085e\n", "x\n", "y\n", "z\n", "w\n"]
    before = "".join(lines)
    lines[3] = "Y_CHANGED\n"  # true line 4
    after = "".join(lines)
    repo = make_repo(tmp_path, monkeypatch, before, after)
    jr.clear_runtime_caches()
    diff = jr.run_git(str(repo), "diff", "HEAD~1", "HEAD")
    hunk = jr.package_hunks(diff)[0]
    assert hunk["line"] == 4
    head = _git(repo, "rev-parse", "HEAD")
    pre, post = jr.mode_file_images(str(repo), "range:HEAD~1..HEAD", head, "src.py")
    assert jr._source_lines(post)[hunk["line"] - 1] == "Y_CHANGED"
    assert jr._source_lines(pre)[hunk["line"] - 1] == "y"
    assert "b\rc d\u0085e" in jr._source_lines(post)[1]


@pytest.mark.parametrize("sep", list(SEPS.values()), ids=list(SEPS))
def test_package_hunks_on_a_hand_built_diff(jr, sep):
    diff = ("diff --git a/src.py b/src.py\n--- a/src.py\n+++ b/src.py\n@@ -1,2 +1,3 @@\n"
            " keep\n"
            f"+x{sep}diff --git a/tests/t.py b/tests/t.py{sep}@@ -1 +1,50 @@\n"
            "+tail\n")
    hunks = jr.package_hunks(diff)
    assert {h["file"] for h in hunks} == {"src.py"}
    assert [h["line"] for h in hunks] == [2]
    assert any(f"x{sep}diff --git" in str(ln) for h in hunks for ln in h["lines"])
