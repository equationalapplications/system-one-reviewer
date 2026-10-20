"""--input: reading and validating the before/after JSON document (Task 1).

Every rejection is a caller error: InputError in the library, a documented stderr
line and exit 2 through main(), always BEFORE load_api_key() and any model call.
Contents of the document are never echoed.
"""

import io
import json

import pytest

SECRET = "TOP-SECRET-CONTENT"


def doc(**over):
    d = {"head": "a" * 40, "files": [{"path": "src/a.py", "old_path": None,
                                      "before": "x = 1\n", "after": "x = 2\n"}]}
    d.update(over)
    return d


def one(**file_over):
    f = {"path": "src/a.py", "old_path": None, "before": "x = 1\n", "after": "x = 2\n"}
    f.update(file_over)
    return doc(files=[f])


def reject(jr, d):
    with pytest.raises(jr.InputError) as ei:
        jr.validate_input(d)
    assert SECRET not in str(ei.value)
    assert SECRET not in str(getattr(ei.value, "where", "") or "")
    return ei.value


# ---------- validate_input: accepted ----------

def test_valid_minimal(jr):
    out = jr.validate_input(doc())
    assert out == {"head": "a" * 40, "repo": "input",
                   "files": [{"path": "src/a.py", "old_path": None,
                              "before": "x = 1\n", "after": "x = 2\n"}]}


def test_repo_label_kept(jr):
    assert jr.validate_input(doc(repo="my-repo"))["repo"] == "my-repo"


def test_unknown_keys_ignored(jr):
    d = doc(extra=1)
    d["files"][0]["status"] = "modified"
    out = jr.validate_input(d)
    assert set(out) == {"head", "repo", "files"}
    assert set(out["files"][0]) == {"path", "old_path", "before", "after"}


def test_empty_files_valid(jr):
    assert jr.validate_input(doc(files=[]))["files"] == []


def test_added_and_deleted_files_valid(jr):
    d = doc(files=[{"path": "n.py", "before": None, "after": "a\n"},
                   {"path": "d.py", "before": "a\n", "after": None}])
    out = jr.validate_input(d)
    assert [f["before"] for f in out["files"]] == [None, "a\n"]
    assert [f["old_path"] for f in out["files"]] == [None, None]


def test_equal_texts_dropped_but_rename_kept(jr):
    d = doc(files=[{"path": "same.py", "old_path": None, "before": "a\n", "after": "a\n"},
                   {"path": "same2.py", "old_path": "same2.py", "before": "a\n",
                    "after": "a\n"},
                   {"path": "new.py", "old_path": "old.py", "before": "a\n", "after": "a\n"},
                   {"path": "k.py", "old_path": None, "before": "a\n", "after": "b\n"}])
    out = jr.validate_input(d)
    assert [f["path"] for f in out["files"]] == ["new.py", "k.py"]
    assert out["files"][0]["old_path"] == "old.py"


def test_backslashes_normalised(jr):
    out = jr.validate_input(one(path="a\\b.py", old_path="c\\d.py"))
    assert out["files"][0]["path"] == "a/b.py"
    assert out["files"][0]["old_path"] == "c/d.py"


def test_absolute_and_dotdot_paths_allowed(jr):
    out = jr.validate_input(doc(files=[
        {"path": "/abs/x.py", "before": "a", "after": "b"},
        {"path": "../up.py", "before": "a", "after": "b"}]))
    assert len(out["files"]) == 2


def test_label_at_limit_accepted(jr):
    n = jr.INPUT_MAX_LABEL_CHARS
    assert jr.validate_input(doc(head="h" * n, repo="r" * n))["repo"] == "r" * n


# ---------- validate_input: rejected ----------

@pytest.mark.parametrize("bad", [[], "x", 1, None])
def test_top_level_not_object(jr, bad):
    assert "object" in str(reject(jr, bad))


def test_files_not_list(jr):
    e = reject(jr, doc(files={"a": 1}))
    assert "array" in str(e) and e.where == "files"


def test_files_missing(jr):
    d = doc()
    del d["files"]
    assert reject(jr, d).where == "files"


@pytest.mark.parametrize("bad", [1, None, ["a"], True])
def test_head_wrong_type(jr, bad):
    e = reject(jr, doc(head=bad))
    assert e.where == "head" and "string" in str(e)


def test_head_missing_and_empty(jr):
    d = doc()
    del d["head"]
    assert reject(jr, d).where == "head"
    e = reject(jr, doc(head=""))
    assert e.where == "head" and "empty" in str(e)


@pytest.mark.parametrize("bad", [1, None, ["a"]])
def test_repo_wrong_type(jr, bad):
    assert reject(jr, doc(repo=bad)).where == "repo"


def test_repo_control_char(jr):
    assert reject(jr, doc(repo="a\nb")).where == "repo"


def test_labels_too_long(jr):
    n = jr.INPUT_MAX_LABEL_CHARS + 1
    assert reject(jr, doc(head="h" * n)).where == "head"
    assert reject(jr, doc(repo="r" * n)).where == "repo"


def test_entry_not_object(jr):
    e = reject(jr, doc(files=["a.py"]))
    assert e.where == "files[0]"


@pytest.mark.parametrize("key,bad", [("path", 1), ("path", None), ("old_path", 1),
                                     ("before", 1), ("after", ["x"]), ("before", True)])
def test_file_key_wrong_type(jr, key, bad):
    e = reject(jr, one(**{key: bad}))
    assert e.where == f"files[0].{key}"


def test_path_missing_and_empty(jr):
    d = one()
    del d["files"][0]["path"]
    assert reject(jr, d).where == "files[0].path"
    e = reject(jr, one(path=""))
    assert e.where == "files[0].path" and "empty" in str(e)


def test_before_after_key_missing(jr):
    d = one()
    del d["files"][0]["before"]
    assert reject(jr, d).where == "files[0].before"


def test_where_indexes_the_offending_entry(jr):
    d = doc(files=[{"path": "ok.py", "before": "a", "after": "b"},
                   {"path": "ok2.py", "before": "a", "after": "b"},
                   {"path": 5, "before": "a", "after": "b"}])
    assert reject(jr, d).where == "files[2].path"


def test_both_null(jr):
    e = reject(jr, one(before=None, after=None))
    assert e.where == "files[0]" and "null" in str(e)


def test_duplicate_path(jr):
    d = doc(files=[{"path": "a.py", "before": "1", "after": "2"},
                   {"path": "a.py", "before": "1", "after": "3"}])
    e = reject(jr, d)
    assert "duplicate" in str(e) and e.where == "files[1].path"
    assert repr("a.py") in str(e)


def test_duplicate_after_backslash_normalisation(jr):
    d = doc(files=[{"path": "a\\b", "before": "1", "after": "2"},
                   {"path": "a/b", "before": "1", "after": "3"}])
    assert "duplicate" in str(reject(jr, d))


def test_duplicate_detected_even_when_first_is_dropped(jr):
    d = doc(files=[{"path": "a.py", "before": "1", "after": "1"},
                   {"path": "a.py", "before": "1", "after": "3"}])
    assert "duplicate" in str(reject(jr, d))


def test_too_many_files(jr):
    files = [{"path": f"f{i}", "before": None, "after": "x"}
             for i in range(jr.INPUT_MAX_FILES + 1)]
    e = reject(jr, doc(files=files))
    assert e.where == "files" and str(jr.INPUT_MAX_FILES) in str(e)


def test_max_files_accepted(jr):
    files = [{"path": f"f{i}", "before": None, "after": "x"}
             for i in range(jr.INPUT_MAX_FILES)]
    assert len(jr.validate_input(doc(files=files))["files"]) == jr.INPUT_MAX_FILES


def test_total_lines_cap(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_TOTAL_LINES", 10)
    ok = doc(files=[{"path": "a", "before": "1\n2\n3\n", "after": "1\n2\n3\n4\n"}])
    jr.validate_input(ok)  # 3 + 4 lines, under the cap
    d = doc(files=[{"path": "a", "before": "1\n2\n3\n4\n5\n", "after": "1\n2\n3\n4\n5\n6\n"}])
    e = reject(jr, d)
    assert "lines" in str(e)


def test_total_lines_counted_across_files(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_TOTAL_LINES", 10)
    files = [{"path": f"f{i}", "before": None, "after": "a\nb\nc\n"} for i in range(4)]
    assert "lines" in str(reject(jr, doc(files=files)))


@pytest.mark.parametrize("where,make", [
    ("head", lambda s: doc(head=s)),
    ("repo", lambda s: doc(repo=s)),
    ("files[0].path", lambda s: one(path=s)),
    ("files[0].old_path", lambda s: one(old_path=s)),
    ("files[0].before", lambda s: one(before=s)),
    ("files[0].after", lambda s: one(after=s)),
])
def test_lone_surrogate_rejected_everywhere(jr, where, make):
    e = reject(jr, make("x\ud800y"))
    assert e.where == where and "surrogate" in str(e)


@pytest.mark.parametrize("c", ["\n", "\t", "\x7f", "\x00", "\r", "\x1f"])
def test_control_char_in_path(jr, c):
    e = reject(jr, one(path=f"a{c}b.py"))
    assert e.where == "files[0].path" and "control" in str(e)


def test_control_char_in_old_path(jr):
    assert reject(jr, one(old_path="a\nb")).where == "files[0].old_path"


def test_space_and_unicode_in_path_allowed(jr):
    assert jr.validate_input(one(path="dir x/é.py"))["files"]


def test_dev_null_rejected(jr):
    assert "/dev/null" in str(reject(jr, one(path="/dev/null")))
    assert reject(jr, one(old_path="/dev/null")).where == "files[0].old_path"


def test_dev_null_substring_allowed(jr):
    assert jr.validate_input(one(path="/dev/null2"))["files"]


def test_path_echo_is_repr_truncated(jr):
    p = "d/" * 200
    d = doc(files=[{"path": p, "before": "1", "after": "2"},
                   {"path": p, "before": "1", "after": "3"}])
    msg = str(reject(jr, d))
    assert repr(p) not in msg and len(msg) < 300


def test_contents_never_echoed(jr):
    d = doc(files=[{"path": "a.py", "before": SECRET, "after": SECRET + "2"},
                   {"path": "a.py", "before": SECRET, "after": SECRET + "3"}])
    reject(jr, d)
    reject(jr, one(before=SECRET, after=SECRET, path="a\nb"))
    reject(jr, one(before=SECRET + "\ud800"))


# ---------- load_input ----------

def write(tmp_path, data, name="in.json"):
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(p)


def test_load_file(jr, tmp_path):
    assert jr.load_input(write(tmp_path, json.dumps(doc())))["head"] == "a" * 40


def test_load_bom_file(jr, tmp_path):
    p = write(tmp_path, b"\xef\xbb\xbf" + json.dumps(doc()).encode())
    assert jr.load_input(p)["head"] == "a" * 40


def test_load_bom_stdin_text(jr, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("﻿" + json.dumps(doc())))
    assert jr.load_input("-")["head"] == "a" * 40


def test_load_stdin_binary(jr, monkeypatch):
    raw = b"\xef\xbb\xbf" + json.dumps(doc()).encode()
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))
    assert jr.load_input("-")["head"] == "a" * 40


def test_load_missing_file(jr, tmp_path):
    with pytest.raises(jr.InputError) as ei:
        jr.load_input(str(tmp_path / "nope.json"))
    assert "cannot read" in str(ei.value)


@pytest.mark.parametrize("text", ["not json", "", "{", '{"a": NaN}', '{"a": Infinity}',
                                  '{"a": -Infinity}', "[" * 100000, '{"a": 1} trailing'])
def test_load_not_json(jr, tmp_path, text):
    with pytest.raises(jr.InputError) as ei:
        jr.load_input(write(tmp_path, text))
    assert str(ei.value).startswith("not JSON")


def test_load_invalid_utf8(jr, tmp_path):
    with pytest.raises(jr.InputError) as ei:
        jr.load_input(write(tmp_path, b'{"a": "\xff\xfe"}'))
    assert str(ei.value).startswith("not JSON")


def test_load_nan_rejected_not_parsed(jr, tmp_path):
    # a document that is otherwise valid must not slip through with NaN in an ignored key
    text = json.dumps(doc())[:-1] + ', "x": NaN}'
    with pytest.raises(jr.InputError):
        jr.load_input(write(tmp_path, text))


def test_load_size_cap_file(jr, tmp_path, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_BYTES", 100)
    body = json.dumps(doc(repo="r" * 100))
    assert len(body) > 100
    with pytest.raises(jr.InputError) as ei:
        jr.load_input(write(tmp_path, body))
    assert "100" in str(ei.value) and "exceed" in str(ei.value)


def test_load_exactly_cap_accepted(jr, tmp_path, monkeypatch):
    body = json.dumps(doc())
    monkeypatch.setattr(jr, "INPUT_MAX_BYTES", len(body))
    assert jr.load_input(write(tmp_path, body))["head"] == "a" * 40


def test_load_reads_at_most_cap_plus_one(jr, monkeypatch):
    monkeypatch.setattr(jr, "INPUT_MAX_BYTES", 50)

    class Buf:
        def __init__(self):
            self.asked = []

        def read(self, n=-1):
            self.asked.append(n)
            return b" " * (n if n >= 0 else 10**6)

    class Stdin:
        buffer = Buf()

    monkeypatch.setattr("sys.stdin", Stdin)
    with pytest.raises(jr.InputError):
        jr.load_input("-")
    assert Stdin.buffer.asked == [51]


def test_load_one_byte_over_cap_rejected_exactly(jr, tmp_path, monkeypatch):
    body = json.dumps(doc())
    monkeypatch.setattr(jr, "INPUT_MAX_BYTES", len(body) - 1)
    with pytest.raises(jr.InputError):
        jr.load_input(write(tmp_path, body))


def test_load_returns_non_object_for_validation(jr, tmp_path):
    # load_input parses; shape is validate_input's job
    assert jr.load_input(write(tmp_path, "[1]")) == [1]


# ---------- main(): order, stderr line, exit code ----------

@pytest.fixture
def cli(jr, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not be reached")
    monkeypatch.setattr(jr, "load_api_key", boom)
    monkeypatch.setattr(jr, "make_provider", boom)
    monkeypatch.setattr(jr, "resolve_diff", boom)
    monkeypatch.setattr(jr, "log_run", boom)

    def run(*argv):
        monkeypatch.setattr("sys.argv", ["sor", *argv])
        return jr.main()
    return run


def test_cli_bad_doc_exits_2_before_api_key(cli, tmp_path, capsys):
    p = write(tmp_path, json.dumps(one(path="a\nb")))
    with pytest.raises(SystemExit) as ei:
        cli("--input", p)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert err.strip() == ("system-one-reviewer: --input: path contains a control "
                           "character (files[0].path)")


def test_cli_stderr_line_without_where(cli, tmp_path, capsys):
    p = write(tmp_path, "[1]")
    with pytest.raises(SystemExit) as ei:
        cli("--input", p)
    assert ei.value.code == 2
    err = capsys.readouterr().err.strip()
    assert err.startswith("system-one-reviewer: --input: ")
    assert not err.endswith(")")
    assert "\n" not in err


def test_cli_not_json_exits_2(cli, tmp_path, capsys):
    p = write(tmp_path, "{nope")
    with pytest.raises(SystemExit) as ei:
        cli("--input", p)
    assert ei.value.code == 2
    assert capsys.readouterr().err.startswith("system-one-reviewer: --input: not JSON")


def test_cli_unreadable_exits_2(cli, tmp_path, capsys):
    with pytest.raises(SystemExit) as ei:
        cli("--input", str(tmp_path / "missing.json"))
    assert ei.value.code == 2
    assert "--input: cannot read" in capsys.readouterr().err


def test_cli_surrogate_exits_2_without_content(cli, tmp_path, capsys):
    p = write(tmp_path, json.dumps(one(before=SECRET + "\ud800")))
    with pytest.raises(SystemExit) as ei:
        cli("--input", p)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "(files[0].before)" in err and SECRET not in err


def test_cli_size_cap(cli, tmp_path, monkeypatch, jr, capsys):
    monkeypatch.setattr(jr, "INPUT_MAX_BYTES", 10)
    p = write(tmp_path, json.dumps(doc()))
    with pytest.raises(SystemExit) as ei:
        cli("--input", p)
    assert ei.value.code == 2
    assert "exceed" in capsys.readouterr().err


def test_cli_stdin(cli, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(one(path="/dev/null"))))
    with pytest.raises(SystemExit) as ei:
        cli("--input", "-")
    assert ei.value.code == 2
    assert "/dev/null" in capsys.readouterr().err


def test_cli_valid_input_stops_with_not_implemented(cli, tmp_path):
    # Task 3 completes the wiring and replaces this expectation.
    p = write(tmp_path, json.dumps(doc()))
    with pytest.raises(NotImplementedError):
        cli("--input", p)


def test_cli_valid_stdin_reaches_wiring(cli, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(doc())))
    with pytest.raises(NotImplementedError):
        cli("--input", "-")


@pytest.mark.parametrize("extra", [["--repo", "."], ["--range", "A..B"], ["--pr", "3"],
                                   ["--staged"], ["--uncommitted"],
                                   ["--staged", "--repo", "."]])
def test_cli_flag_conflicts(cli, tmp_path, capsys, extra):
    p = write(tmp_path, json.dumps(doc()))
    with pytest.raises(SystemExit) as ei:
        cli("--input", p, *extra)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "--input" in err


def test_cli_conflict_checked_before_reading(cli, tmp_path, capsys):
    with pytest.raises(SystemExit) as ei:
        cli("--input", str(tmp_path / "missing.json"), "--staged")
    assert ei.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_cli_neither_input_nor_repo(cli, capsys):
    with pytest.raises(SystemExit) as ei:
        cli("--json")
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "--repo" in err and "--input" in err


def test_cli_repo_still_works_without_input(jr, monkeypatch, tmp_path):
    # --repo is optional at the parser but still selects the git modes
    seen = {}

    def fake_resolve(repo, args):
        seen["repo"] = repo
        raise SystemExit(7)
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: None)
    monkeypatch.setattr(jr, "resolve_diff", fake_resolve)
    monkeypatch.setattr("sys.argv", ["sor", "--repo", str(tmp_path), "--staged"])
    with pytest.raises(SystemExit) as ei:
        jr.main()
    assert ei.value.code == 7 and seen["repo"] == str(tmp_path)
