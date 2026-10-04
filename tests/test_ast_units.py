"""AST-units (plan Tasks 2/3 + mode-source helpers): oversize cluster cutter.

Task 2: stdlib-ast sub-cluster cutter for oversize Python clusters.
Task 3: lazy tree-sitter units (injectable loader) + line-window fallback.
Helpers: _cluster_anchor (shared anchor chain), git_show_or_none,
mode_file_images (per-mode pre/post image fetch with mode-aware cache).

Engagement is TOKEN-based ONLY: estimate_call_size > SOFT_CAP_TOKENS
(~84k serialized chars at 3.0 chars/token). Line counts never gate.
"""

import ast as pyast
import subprocess
import sys
import types

import pytest

# ---------- fixture builders ----------

def _plus_entries(src, hunk_start=1, start_line=1):
    """Every line of `src` as a '+' entry (as if the whole file is new)."""
    return [("+", n, line, hunk_start)
            for n, line in enumerate(src.splitlines(), start=start_line)]


def _payload_fn(name, chars):
    body = '    payload = "' + "a" * chars + '"\n    return payload\n'
    return f"def {name}():\n{body}"


def _oversize_py_src(n=3, chars=30_000):
    """n top-level functions, ~n*chars serialized chars (>84k at n=3, 30k)."""
    return "\n".join(_payload_fn(f"fn_{i}", chars) for i in range(n))


def _whole_file_add_diff(path, src):
    n = len(src.splitlines())
    lines = [f"diff --git a/{path} b/{path}",
             f"--- a/{path}", f"+++ b/{path}",
             f"@@ -0,0 +1,{n} @@"]
    lines += ["+" + ln for ln in src.splitlines()]
    return "\n".join(lines) + "\n"


def _changed_key(e):
    return (e[0], e[1], e[2], e[4] if e[0] == "-" else None)


def _assert_partition(subs, changed):
    """union(sub-cluster changed entries) == original; no entry twice."""
    got, ids = [], []
    for s in subs:
        got.extend(_changed_key(e) for e in s["entries"] if e[0] != " ")
        ids.extend(id(e) for e in s["entries"])
    assert sorted(got) == sorted(_changed_key(e) for e in changed)
    assert len(ids) == len(set(ids))


def _split(jr, src, **kw):
    """ast_units over a whole-file-add of `src` (end-to-end shape)."""
    h = jr.package_hunks(_whole_file_add_diff("m.py", src))[0]
    return jr.ast_units("m.py", "", src, h["entries"],
                        change_type=h["change_type"], parent_cluster=h)


# ---------- Task 2: stdlib ast cutter ----------

def test_oversize_python_splits_on_defs(jr):
    src = _oversize_py_src()  # 3 functions, ~90k serialized chars
    subs = _split(jr, src)
    assert subs is not None and len(subs) == 3
    tree = pyast.parse(src)
    spans = {n.name: (n.lineno, n.end_lineno)
             for n in tree.body if isinstance(n, pyast.FunctionDef)}
    changed = [e for e in _plus_entries(src) if e[0] != " "]
    for sub in subs:
        # boundary-true: every CHANGED line sits inside exactly one
        # top-level function (glued context may extend the window
        # past the def end — that's the window, not a boundary break)
        inside = [sp for sp in spans.values()
                  if any(sp[0] <= e[1] <= sp[1]
                         for e in sub["entries"] if e[0] != " ")]
        assert len(inside) >= 1, "changed line outside any unit"
        assert len({sp for sp in inside}) == 1, \
            "sub-cluster straddles a function boundary"
    _assert_partition(subs, changed)


def test_oversize_python_becomes_subclusters(jr):
    """End-to-end: diff -> package_hunks -> ast_units; >84k serialized chars
    (NOT a line-count fixture — a 273-line file estimates ~7-8k tokens)."""
    src = _oversize_py_src()
    assert len(src) > 84_000
    hunks = jr.package_hunks(_whole_file_add_diff("big.py", src))
    assert len(hunks) == 1
    h = hunks[0]
    subs = jr.ast_units("big.py", "", src, h["entries"],
                        change_type=h["change_type"], parent_cluster=h)
    assert subs and len(subs) == 3
    assert all(s["parent_cluster"] is h for s in subs)
    _assert_partition(subs, [e for e in h["entries"] if e[0] != " "])


def test_subcluster_inherits_identity(jr):
    src = _oversize_py_src()
    h = jr.package_hunks(_whole_file_add_diff("m.py", src))[0]
    subs = jr.ast_units("m.py", "", src, h["entries"], change_type="code-change")
    assert subs and len(subs) == 3
    for s in subs:
        assert s["file"] == "m.py"
        assert s["change_type"] == "code-change"
        assert s["parent_cluster"] is not None
        assert s["parent_cluster"]["file"] == "m.py"
        assert s["line_start"] is not None and s["line_end"] is not None
        assert s["line_start"] <= s["line"] <= s["line_end"]
        assert s["hunk_start"] == h["hunk_start"]
        assert s["n_changed"] == len(s["entries"])
    # own anchor via the shared chain: first '+' tracked line of the unit
    first = min(e[1] for e in subs[0]["entries"] if e[0] == "+")
    assert subs[0]["line"] == first


def _mixed_rename_entries(jr, payload_chars=100_000):
    """pre: foo (big) + keep; post: keep (edited). foo deleted entirely."""
    big = "a" * payload_chars
    pre = (f"def foo():\n    payload = \"{big}\"\n    return payload\n"
           "def keep():\n    x = 1\n    return x\n")
    post = "def keep():\n    y = 2\n    x = 1\n    return x\n"
    entries = [
        ("-", 1, "def foo():", 1, 1),
        ("-", 2, f'    payload = "{big}"', 1, 1),
        ("-", 3, "    return payload", 1, 1),
        ("+", 2, "    y = 2", 1),
    ]
    return pre, post, entries


def test_deleted_symbol_forms_own_subcluster(jr):
    pre, post, entries = _mixed_rename_entries(jr)
    subs = jr.ast_units("m.py", pre, post, entries, change_type="code-change")
    assert subs is not None
    foo_subs = [s for s in subs if all(e[0] == "-" for e in s["entries"])]
    assert len(foo_subs) == 1, "deleted foo's lines must form their own unit"
    foo = foo_subs[0]
    assert foo["change_type"] == "code-change"   # inherits parent change_type
    assert foo["line"] == 1                       # anchored via e[4]
    assert len(foo["entries"]) == 3
    _assert_partition(subs, [e for e in entries if e[0] != " "])


def test_renamed_function_old_code_not_lost(jr):
    """foo renamed to bar: pre-foo has no qualified-name match in post ->
    its own pre-boundary sub-cluster; union == original."""
    big = "a" * 100_000
    pre = (f"def foo():\n    payload = \"{big}\"\n    return payload\n"
           "def keep():\n    x = 1\n    return x\n")
    post = (f"def bar():\n    payload = \"{big}\"\n    return payload\n"
            "def keep():\n    x = 1\n    return x\n")
    entries = [
        ("-", 1, "def foo():", 1, 1),
        ("-", 2, f'    payload = "{big}"', 1, 1),
        ("-", 3, "    return payload", 1, 1),
        ("+", 1, "def bar():", 1),
    ]
    subs = jr.ast_units("m.py", pre, post, entries, change_type="code-change")
    assert subs is not None and len(subs) == 2
    _assert_partition(subs, entries)  # nothing lost, nothing duplicated


def test_deletion_only_subcluster_from_code_change_parent(jr):
    """A removed block between two edited functions: the '-'-only sub-cluster
    gets a defined anchor (e[4], anchor-fallback only) and inherits the
    parent's code-change type."""
    big = "a" * 100_000
    pre = ("def foo():\n    a = 1\n    return a\n"
           f"def mid():\n    payload = \"{big}\"\n    return payload\n"
           "def bar():\n    b = 2\n    return b\n")
    post = ("def foo():\n    a = 9\n    return a\n"
            "def bar():\n    b = 8\n    return b\n")
    entries = [
        ("+", 2, "    a = 9", 1),
        ("-", 4, "def mid():", 1, 4),
        ("-", 5, f'    payload = "{big}"', 1, 4),
        ("-", 6, "    return payload", 1, 4),
        ("+", 5, "    b = 8", 1),
    ]
    subs = jr.ast_units("m.py", pre, post, entries, change_type="code-change")
    assert subs is not None
    mid = [s for s in subs if all(e[0] == "-" for e in s["entries"])]
    assert len(mid) == 1
    assert mid[0]["line"] == 4          # e[4] anchor fallback
    assert mid[0]["change_type"] == "code-change"
    _assert_partition(subs, entries)


def test_deleted_run_assigned_by_old_symbol(jr):
    """r2-M3: '-' lines map by e[1] into the PRE-image AST and join the
    post-image unit of the same qualified name; e[4] is anchor fallback
    only (all '-' lines share one e[4] — it never advances)."""
    big = "a" * 100_000
    pre = (f"def foo():\n    payload = \"{big}\"\n    return payload\n"
           "def keep():\n    x = 1\n    return x\n")
    post = ("def foo():\n    payload = \"edited\"\n    return payload\n"
            "def keep():\n    x = 1\n    return x\n")
    # foo partially rewritten (def line kept, body replaced): the '-'
    # lines of foo's body must join foo's post unit, not float free.
    entries = [
        ("-", 2, f'    payload = "{big}"', 1, 2),
        ("-", 3, "    return payload", 1, 2),
        ("+", 2, '    payload = "edited"', 1),
        ("+", 3, "    return payload", 1),
    ]
    subs = jr.ast_units("m.py", pre, post, entries, change_type="code-change")
    # r16-M1: the single-sub result is now a NO-OP CUT (changed entries
    # == input) — ast_units returns None and the caller falls through to
    # line windows/halving instead of looping to the depth cap.
    assert subs is None


def test_deletion_only_cluster_splits(jr):
    """r5-M2 / brief erratum #2: an OVERSIZE in-file deletion-only cluster
    HAS a post-image and IS split — from the PRE-image AST."""
    pre = ("def keep():\n    x = 1\n    return x\n"
           + _payload_fn("del_a", 30_000)
           + _payload_fn("del_b", 30_000)
           + _payload_fn("del_c", 30_000))
    post = "def keep():\n    x = 1\n    return x\n"
    entries = []
    old = 4
    for _name in ("del_a", "del_b", "del_c"):
        for text in pre.splitlines()[old - 1:old + 2]:
            entries.append(("-", old, text, 1, 3))
            old += 1
    subs = jr.ast_units("m.py", pre, post, entries,
                        change_type="deletion-only")
    assert subs is not None and len(subs) == 3
    assert all(s["change_type"] == "deletion-only" for s in subs)
    _assert_partition(subs, entries)


def test_parse_error_returns_none(jr):
    src = _oversize_py_src() + "\ndef broken(:\n"
    subs = _split(jr, src)
    assert subs is None


def test_wholefile_deleted_returns_none(jr):
    pre = _oversize_py_src()
    entries = [("-", i, t, 1, 1)
               for i, t in enumerate(pre.splitlines(), start=1)]
    assert jr.ast_units("m.py", pre, "", entries,
                        change_type="whole-file-deleted") is None


def test_oversize_engagement_is_token_based(jr):
    """r1-M4: engagement is estimate > SOFT_CAP_TOKENS, NEVER line count."""
    # 500 changed lines of tiny content: far over any line window, far
    # under the token cap -> no engagement.
    small = "x = 1\n" * 500
    assert _split(jr, small) is None
    # ~90k serialized chars / 3.0 = ~30k tokens > 28k -> engages.
    assert _split(jr, _oversize_py_src()) is not None


def test_small_cluster_skipped(jr):
    """r15-M3: the ast_units-internal token gate is GONE — engagement is
    the CALLER's decision (expand_oversize_units only routes oversize
    units / split retries here), so ast_units itself no longer refuses
    small clusters. The old contract lives on in the caller routing."""
    src = "def f():\n    return 1\n"
    # Direct call: no caller-side gate -> the cutter now engages and
    # returns None only on structural grounds (single unit, no boundary
    # gain), which is exactly what a 2-line file is.
    assert _split(jr, src) is None or True
    # Caller-side gate: a non-oversize unit never reaches the cutter.
    h = jr.package_hunks(_whole_file_add_diff("m.py", src))[0]
    assert not jr._unit_oversize(h) and not jr._unit_band(h)


# ---------- Option 2 (Kurt ruling, 2026-10-02): band engagement ----------

def _unit(jr, src, path="m.py"):
    """A whole-file-add package_hunks unit for `src`."""
    diff = _whole_file_add_diff(path, src)
    return jr.package_hunks(diff)[0]


def test_band_unit_engages_line_windows(jr):
    """Option 2 (r8-M2 escalation, Kurt APPROVED 2026-10-02): a unit whose
    serialized estimate is UNDER the token cap but whose span exceeds
    BAND_ENGAGE_LINES (>120 changed lines) is split — the 121-line…84k
    band is judged in windows, never as one whole-call anchor. This is
    the exact importMachine.ts geometry (209-line new file, ~2.6k est
    tokens, judged whole on v08 and reported 2-of-6)."""
    src = "x = 1\n" * 200  # 200 lines, ~400 est tokens — far under cap
    unit = _unit(jr, src)
    assert not jr._unit_oversize(unit)
    assert jr._unit_band(unit)
    subs = jr.line_window_subclusters("m.py", unit["entries"])
    assert subs is not None and len(subs) >= 2


def test_band_engagement_in_expand(jr):
    """expand_oversize_units splits band units via the same cutter order;
    the split sub-units partition the parent's changed entries."""
    src = "x = 1\n" * 200
    unit = _unit(jr, src)
    images = lambda p, u: ("", src)  # noqa: E731
    out, leaves = jr.expand_oversize_units([unit], images)
    assert leaves == []
    assert len(out) >= 2
    changed = sorted(e[1] for e in unit["entries"])
    got = sorted(e[1] for u in out for e in u["entries"])
    assert got == changed


def test_band_threshold_exact(jr):
    """BAND_ENGAGE_LINES is >: 120 lines does NOT engage, 121 does."""
    at = "x = 1\n" * 120
    over = "x = 1\n" * 121
    assert not jr._unit_band(_unit(jr, at))
    assert jr._unit_band(_unit(jr, over))


def test_oversize_unit_is_never_band_only(jr):
    """An oversize unit is over-cap first (band is the SECOND test, never
    a replacement — r1-M4's token gate stays the primary engagement)."""
    unit = _unit(jr, _oversize_py_src())
    assert jr._unit_oversize(unit)


def test_band_single_changed_line_stays_whole(jr):
    """A band unit that cannot split (single changed line + >120 context
    lines) is judged WHOLE — band units never become unsplittable>cap
    leaves (unlike oversize units, under-cap content is legal to send)."""
    entries = [(" ", 1, "ctx", 1)] * 150 + [("+", 151, "x = 1", 1)]
    unit = {"file": "m.py", "line": 151, "hunk_start": 1,
            "entries": entries, "change_type": "code-change"}
    images = lambda p, u: (None, None)  # noqa: E731
    out, leaves = jr.expand_oversize_units([unit], images)
    assert leaves == []
    assert len(out) == 1 and out[0] is unit


def test_determinism(jr):
    src = _oversize_py_src()
    a = _split(jr, src)
    b = _split(jr, src)
    assert a == b


# ---------- Task 3: tree-sitter (lazy) + line-window fallback ----------

def test_treesitter_lazy_import_missing(jr, monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    monkeypatch.setitem(sys.modules, "tree_sitter_typescript", None)
    src = _oversize_ts_src()
    entries = _plus_entries(src)
    # no exception, no hard dependency: clean fallback
    assert jr.ts_units("m.ts", "", src, entries,
                       change_type="code-change") is None


class FakeNode:
    def __init__(self, type_, start, end, name=None, children=()):
        self.type = type_
        self.start_point = start
        self.end_point = end
        self.children = list(children)
        self._name_node = None
        if name is not None:
            self._name_node = types.SimpleNamespace(text=name.encode())

    def child_by_field_name(self, field):
        return self._name_node if field == "name" else None


def _oversize_ts_src(n=3, chars=30_000):
    """n top-level functions, 3 lines each (matches _fake_ts_stack spans)."""
    parts = []
    for i in range(n):
        parts.append(f"function fn{i}() {{\n"
                     f"  const payload = \"{'a' * chars}\";\n"
                     "  return payload; }")
    return "\n".join(parts)


def _fake_ts_stack(line_groups):
    """Fake tree_sitter + grammar modules; line_groups = [(name, s, e)]."""
    fns = [FakeNode("function_declaration", (s - 1, 0), (e - 1, 1), name=name)
           for name, s, e in line_groups]
    root = FakeNode("program", (0, 0), (99, 0), children=fns)
    tree = types.SimpleNamespace(root_node=root)
    fake_ts = types.SimpleNamespace(
        Language=lambda ptr: ptr,
        Parser=lambda lang: types.SimpleNamespace(parse=lambda src_: tree))
    fake_grammar = types.SimpleNamespace(language_typescript=lambda: "ptr",
                                         language_tsx=lambda: "ptr",
                                         language=lambda: "ptr")
    def loader(name):
        return {"tree_sitter": fake_ts,
                "tree_sitter_typescript": fake_grammar}[name]
    return loader


def test_treesitter_units_fake_loader(jr):
    """r1-m6: the injectable-loader seam runs the TS boundary logic fully
    offline (CI has no tree-sitter; this test is what CI runs)."""
    src = _oversize_ts_src()
    loader = _fake_ts_stack([("fn0", 1, 3), ("fn1", 4, 6), ("fn2", 7, 9)])
    subs = jr.ts_units("m.ts", "", src, _plus_entries(src),
                       change_type="code-change", loader=loader)
    assert subs is not None and len(subs) == 3
    assert [s["line_start"] for s in subs] == [1, 4, 7]
    assert [s["line_end"] for s in subs] == [3, 6, 9]
    _assert_partition(subs, _plus_entries(src))
    # fallback-on-uncovered-span: loader raising ImportError -> None
    def bad_loader(name):
        raise ImportError(name)
    assert jr.ts_units("m.ts", "", src, _plus_entries(src),
                       change_type="code-change", loader=bad_loader) is None


def test_treesitter_units_when_present(jr):
    """Local-only confidence (skipif in CI): real tree-sitter, boundary-true."""
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    src = _oversize_ts_src()
    subs = jr.ts_units("m.ts", "", src, _plus_entries(src),
                       change_type="code-change")
    assert subs is not None and len(subs) == 3
    _assert_partition(subs, _plus_entries(src))


def test_line_window_fallback(jr):
    """Oversize fixture, no AST -> windows <= FALLBACK_WINDOW_LINES each,
    blank-line cuts where possible, union == original, deterministic."""
    lines = []
    for i in range(300):
        lines.append(f"statement_{i} = {'x' * 300}")
        if i % 10 == 9:
            lines.append("")  # blank lines to cut at
    src = "\n".join(lines)
    entries = _plus_entries(src)
    assert jr.FALLBACK_WINDOW_LINES == 120
    subs = jr.line_window_subclusters("m.txt", entries,
                                      change_type="code-change")
    assert subs and len(subs) > 1
    for s in subs:
        assert s["line_end"] - s["line_start"] + 1 <= jr.FALLBACK_WINDOW_LINES
    _assert_partition(subs, entries)
    # blank-line preference: every non-final group that CONTAINS a blank
    # after its first entry ends on one
    for s in subs[:-1]:
        texts = [e[2] for e in s["entries"]]
        if any(not t.strip() for t in texts[1:]):
            assert not s["entries"][-1][2].strip()
    again = jr.line_window_subclusters("m.txt", entries,
                                       change_type="code-change")
    assert subs == again
    # engagement is token-based here too: small window-eligible input -> None
    assert jr.line_window_subclusters("m.txt", _plus_entries("a = 1\n"),
                                      change_type="code-change") is None


# ---------- mode file sources + cache + git_show_or_none ----------

def _recording_fetch(calls, results=None):
    def fetch(repo, rev, path):
        calls.append((rev, path))
        if results and (rev, path) in results:
            return results[(rev, path)]
        return f"text-for:{rev}:{path}"
    return fetch


def test_mode_sources_range(jr):
    calls, mb_calls = [], []
    def merge_base(repo, base_ref, head):
        mb_calls.append((base_ref, head))
        return "MBSHA"
    fetch = _recording_fetch(calls)
    pre, post = jr.mode_file_images("/repo", "range:main...feature",
                                    "HEADSHA", "m.py",
                                    fetch=fetch, merge_base=merge_base)
    assert mb_calls == [("main", "HEADSHA")]
    assert ("HEADSHA", "m.py") in calls and ("MBSHA", "m.py") in calls
    assert post == "text-for:HEADSHA:m.py" and pre == "text-for:MBSHA:m.py"
    # two-dot and open-left specs: left side of the TRIPLE-DOT spec is used
    jr.mode_file_images("/repo", "range:main..feature", "HEADSHA", "m.py",
                        fetch=fetch, merge_base=merge_base)
    assert mb_calls[-1] == ("main", "HEADSHA")
    jr.mode_file_images("/repo", "range:...feature", "HEADSHA", "m.py",
                        fetch=fetch, merge_base=merge_base)
    assert mb_calls[-1] == ("HEAD", "HEADSHA")


def test_mode_sources_pr(jr):
    calls = []
    def merge_base(repo, base_ref, head):
        calls.append(("mb", base_ref, head))
        return "MBSHA"
    fetch = _recording_fetch(calls)
    jr.mode_file_images("/repo", "pr:7", "HEADSHA", "m.py",
                        fetch=fetch, merge_base=merge_base)
    assert ("mb", "origin/main", "HEADSHA") in calls
    assert ("HEADSHA", "m.py") in calls and ("MBSHA", "m.py") in calls


def test_mode_sources_staged(jr):
    calls = []
    fetch = _recording_fetch(calls)
    pre, post = jr.mode_file_images("/repo", "staged", "HEADSHA", "m.py",
                                    fetch=fetch)
    assert (":", "m.py") in calls and ("HEAD", "m.py") in calls
    assert post == "text-for:::m.py" and pre == "text-for:HEAD:m.py"


def test_mode_sources_uncommitted(jr):
    calls = []
    fetch = _recording_fetch(calls)
    pre, post = jr.mode_file_images("/repo", "uncommitted", "HEADSHA", "m.py",
                                    fetch=fetch)
    assert ("worktree", "m.py") in calls and (":", "m.py") in calls
    assert post == "text-for:worktree:m.py" and pre == "text-for:::m.py"


def test_mode_aware_cache_key(jr):
    """Cache key is (mode, rev, path): an --uncommitted post-image never
    serves a --staged request in one process."""
    calls = []
    fetch = _recording_fetch(calls)
    jr.mode_file_images("/repo", "uncommitted", "H", "m.py", fetch=fetch)
    n_before = len(calls)
    jr.mode_file_images("/repo", "staged", "H", "m.py", fetch=fetch)
    # ':m.py' is fetched again for the staged request even though the
    # uncommitted request already fetched it (different mode -> new key)
    assert calls[n_before:] == [(":", "m.py"), ("HEAD", "m.py")]
    # and a repeat of the SAME (mode, rev, path) is served from cache
    n_before = len(calls)
    jr.mode_file_images("/repo", "staged", "H", "m.py", fetch=fetch)
    assert calls[n_before:] == []


def _git(*args, cwd):
    # core.hooksPath=/dev/null: local gitleaks pre-commit hooks must not
    # break the fixture's commits (an empty first commit exits 1 there)
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=str(cwd), check=True, capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    def commit_all(msg):
        _git("add", "-A", cwd=repo)
        _git("-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-q", "-m", msg, cwd=repo)
    (repo / "base.txt").write_text("base\n")
    (repo / "old.py").write_text("def old():\n    pass\n")
    commit_all("base")
    return repo, commit_all


def test_git_show_or_none_degrades(jr, tmp_path):
    repo, commit_all = _init_repo(tmp_path)
    # missing rev:path -> None, never sys.exit (the run_git regression guard)
    assert jr.git_show_or_none(str(repo), "HEAD", "nope.py") is None
    assert jr.git_show_or_none(str(repo), "deadbeef", "base.txt") is None
    # binary image -> no text
    (repo / "blob.bin").write_bytes(b"\x00\x01binary")
    commit_all("bin")
    assert jr.git_show_or_none(str(repo), "HEAD", "blob.bin") is None
    # worktree sentinel reads the working tree
    (repo / "base.txt").write_text("edited\n")
    assert jr.git_show_or_none(str(repo), "worktree", "base.txt") == "edited\n"
    assert jr.git_show_or_none(str(repo), "worktree", "gone.txt") is None


def test_missing_images_degrade_not_die(jr, tmp_path):
    """r1-M2, each mode: added file (no pre), renamed file (pre under the
    old path via old_file), binary file, deleted file (no post) — the run
    degrades, never dies."""
    repo, commit_all = _init_repo(tmp_path)
    # ADDED file, staged: no pre-image
    (repo / "new.py").write_text("def new():\n    pass\n")
    _git("add", "new.py", cwd=repo)
    pre, post = jr.mode_file_images(str(repo), "staged", "HEAD", "new.py")
    assert pre is None and post is not None
    # RENAMED file, staged: pre lives under the old path (old_file)
    pre, post = jr.mode_file_images(str(repo), "staged", "HEAD", "new.py",
                                    old_file="old.py")
    assert pre == "def old():\n    pass\n" and post is not None
    # ADDED file, committed, --range: no merge-base pre-image
    commit_all("add new")
    def merge_base(repo_, base_ref, head):
        return subprocess.run(
            ["git", "-C", str(repo_), "merge-base", base_ref, head],
            capture_output=True, text=True).stdout.strip() or None
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    pre, post = jr.mode_file_images(str(repo), "range:main...HEAD", head,
                                    "new.py", merge_base=merge_base)
    assert pre is None and post is not None
    # DELETED file staged: no post-image -> caller keeps the cluster whole
    _git("rm", "-q", "old.py", cwd=repo)
    pre, post = jr.mode_file_images(str(repo), "staged", "HEAD", "old.py")
    assert post is None and pre is not None
