"""TS/JS ast_context enrichment (tree-sitter twin of the Python path).

Two layers, like tests/test_ast_units.py: loader-seam tests that run in CI
(no tree-sitter there) and `importorskip` tests that exercise the real
parser against tests/data/ts-enrich/. The fixtures pin the enclosing
chain per line, including the shapes a top-level-only query misses
(non-exported and nested arrows, object-literal methods, class fields,
namespaces) and the ones that must yield no symbol (overload signatures,
anonymous callbacks, decorators on an exported class).
"""

import json
import os

import pytest
from test_enrichment import _add_file_diff, _run_main

DATA = os.path.join(os.path.dirname(__file__), "data", "ts-enrich")


def _read(name):
    with open(os.path.join(DATA, name)) as f:
        return f.read()


def _ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    pytest.importorskip("tree_sitter_javascript")


def _line_of(src, needle):
    for i, ln in enumerate(src.splitlines(), 1):
        if needle in ln:
            return i
    raise AssertionError(needle)


def _enclosing(jr, name, ext, needle):
    src = _read(name)
    ctx = jr._ts_ast_context(src, ext, _line_of(src, needle))
    return None if ctx is None else ctx["enclosing"]


# ---------- loader seam (runs in CI) ----------

def test_missing_tree_sitter_yields_no_context(jr):
    def bad_loader(name):
        raise ImportError(name)

    unit = {"file": "m.ts", "line": 1, "hunk_start": 1,
            "entries": [("+", 1, "const a = 1;", 1)],
            "change_type": "code-change"}
    out = jr.attach_ast_context([unit], lambda p, u: (None, "const a = 1;\n"),
                                loader=bad_loader)
    assert "ast_context" not in out[0]


def test_oversize_source_is_not_parsed(jr):
    # _ts_parse fails open on ANY exception, so a loader that raised would
    # be swallowed and this test would pass even without the size guard;
    # record the calls instead
    calls = []

    def loader(name):
        calls.append(name)
        raise ImportError(name)

    src = "const a = 1;\n" * (jr.TS_ENRICHMENT_MAX_CHARS // 10)
    assert jr._ts_ast_context(src, "ts", 1, loader) is None
    assert calls == []
    # control: a small file does reach the loader
    assert jr._ts_ast_context("const a = 1;\n", "ts", 1, loader) is None
    assert calls == ["tree_sitter"]


def test_injected_loaders_bypass_the_parse_cache(jr):
    """A cache keyed on id(loader) could hand one test's fake loader the
    result of another's after the id is reused; injected loaders skip it."""
    src = "const a = () => 1;\n"

    def failing(name):
        raise ImportError(name)

    jr.clear_runtime_caches()
    jr._ts_ast_context(src, "ts", 1, failing)
    assert jr._TS_PARSE_CACHE == {}


def test_stamps(jr):
    assert jr._enrichment_stamp({"file": "a.py", "ast_context": {}}) == "ast"
    assert jr._enrichment_stamp({"file": "a.ts", "ast_context": {}}) == "ts-ast"
    assert jr._enrichment_stamp({"file": "a.tsx", "ast_context": {}}) == "ts-ast"
    assert jr._enrichment_stamp({"file": "a.ts"}) == "none"
    py = {"file": "a.py", "ast_context": {}}
    ts = {"file": "a.ts", "ast_context": {}}
    assert jr._run_enrichment_stamp([py]) == "ast"
    assert jr._run_enrichment_stamp([ts, {"file": "b.ts"}]) == "ts-ast"
    assert jr._run_enrichment_stamp([ts, py]) == "ast+ts-ast"
    assert jr._run_enrichment_stamp([{"file": "b.ts"}]) == "none"


# ---------- real parser: enclosing chains ----------

@pytest.mark.parametrize("name,ext,needle,expected", [
    ("sample.ts", "ts", "return a + 1;", "exported"),
    ("sample.ts", "ts", "return inner();", "notExported"),
    ("sample.ts", "ts", "const inner = () => n * 2;", "notExported.inner"),
    ("sample.ts", "ts", "private cache", "Service"),
    ("sample.ts", "ts", "return this.cache.get(id);", "Service.handler"),
    ("sample.ts", "ts", "return new Service();", "Service.create"),
    ("sample.ts", "ts", "return this.cache.size;", "Service.size"),
    ("sample.ts", "ts", "const cb = () => job.length;", "Service.run.cb"),
    ("sample.ts", "ts", "return [1, 2, 3];", "fetchAll"),
    ("sample.ts", "ts", "parse: (s: string)", "parse"),
    ("sample.ts", "ts", "retries: 3", None),
    ("sample.ts", "ts", "return deeper();", "nested"),
    ("sample.ts", "ts", "return a;", "overload"),
    ("sample.ts", "ts", "function overload(a: string): string;", None),
    ("sample.ts", "ts", "area(): number;", "Shape"),
    ("sample.ts", "ts", "export type Id", "Id"),
    ("sample.ts", "ts", "export function inNs", "Ns.inNs"),
    ("sample.ts", "ts", "console.log(v);", None),
    ("sample.ts", "ts", "@Input() label", "Decorated"),
    ("sample.ts", "ts", "decoratedMethod() {", "Decorated.decoratedMethod"),
    ("sample.ts", "ts", "@Injectable()", None),
    ("component.tsx", "tsx", "return <button", "Button"),
    ("component.tsx", "tsx", "const onClick", "Button.onClick"),
    ("component.tsx", "tsx", "return <div>", "Card"),
    ("default.ts", "ts", "return 2;", "<default>"),
])
def test_enclosing_chain(jr, name, ext, needle, expected):
    _ts()
    assert _enclosing(jr, name, ext, needle) == expected


def test_nested_function_chain(jr):
    _ts()
    src = _read("sample.ts")
    deeper = [i for i, ln in enumerate(src.splitlines(), 1)
              if ln.strip() == "function deeper() {"][0]
    assert jr._ts_ast_context(src, "ts", deeper + 1)["enclosing"] \
        == "nested.deeper"


def test_symbol_table_and_window_caps(jr):
    _ts()
    src = _read("sample.ts")
    ctx = jr._ts_ast_context(src, "ts", _line_of(src, "return a + 1;"))
    assert {"exported", "notExported", "Service", "config", "nested",
            "overload"} <= set(ctx["symbols"])
    assert ctx["symbols"]["exported"] == \
        "export function exported(a: number): number {"
    assert len(ctx["symbols"]) <= jr.ENRICHMENT_MAX_SYMBOLS
    assert ctx["context"][0].startswith("export function exported")
    # innermost symbol, not the class header: a method change shows the
    # method (r20-M1 parity with the Python window)
    ctx = jr._ts_ast_context(src, "ts", _line_of(src, "return new Service"))
    assert ctx["context"][0].strip().startswith("static create")
    long_src = "function big() {\n" + "  const x = 1;\n" * 60 + "}\n"
    ctx = jr._ts_ast_context(long_src, "ts", 30)
    assert len(ctx["context"]) == jr.ENRICHMENT_MAX_CONTEXT_LINES


def test_deterministic(jr):
    _ts()
    src = _read("sample.ts")
    a = [jr._ts_ast_context(src, "ts", i) for i in range(1, 80)]
    jr._TS_PARSE_CACHE.clear()
    b = [jr._ts_ast_context(src, "ts", i) for i in range(1, 80)]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_syntax_error_file_gets_no_context(jr):
    _ts()
    assert jr._ts_ast_context(_read("broken.ts"), "ts", 1) is None


def test_javascript_uses_javascript_grammar(jr):
    _ts()
    src = "const f = (a) => {\n  return a;\n};\nclass K { m() { return 1; } }\n"
    assert jr._ts_ast_context(src, "js", 2)["enclosing"] == "f"
    assert jr._ts_ast_context(src, "js", 4)["enclosing"] == "K.m"


def test_deletion_only_unit_uses_pre_image(jr):
    _ts()
    pre = "export function gone() {\n  return 1;\n}\nexport function kept() {}\n"
    post = "export function kept() {}\n"
    unit = {"file": "m.ts", "line": 1, "hunk_start": 1,
            "change_type": "deletion-only",
            "entries": [("-", 2, "  return 1;", 2)]}
    out = jr.attach_ast_context([unit], lambda p, u: (pre, post))
    assert out[0]["ast_context"]["enclosing"] == "gone"


# ---------- end to end (the vacuous-test guard) ----------

def test_run_main_stamps_ts_ast_and_no_enrichment_turns_it_off(
        jr, monkeypatch, tmp_path, capsys):
    """The Oct 2 enrichment A/B was vacuous because the on-arm never
    engaged. This is the same guard in miniature: with tree-sitter the
    on-arm MUST stamp ts-ast per unit and at run level, and
    --no-enrichment MUST read none."""
    _ts()
    diff = _add_file_diff("m.ts", ["export function f() {", "  return 1;", "}"])
    post = "export function f() {\n  return 1;\n}\n"

    def images(repo_, mode_, head_, path_, old_file=None):
        return None, post

    out, judged, records = _run_main(jr, monkeypatch, tmp_path, capsys, diff,
                                     images)
    assert out["meta"]["enrichment"] == "ts-ast"
    assert records[0]["judged"]
    assert all(e["enrichment"] == "ts-ast" for e in records[0]["judged"])
    assert any(u.get("ast_context", {}).get("enclosing") == "f" for u in judged)

    out, judged, records = _run_main(jr, monkeypatch, tmp_path, capsys, diff,
                                     images, extra_args=("--no-enrichment",))
    assert out["meta"]["enrichment"] == "none"
    assert judged and records[0]["judged"]
    assert all("ast_context" not in u for u in judged)
    assert all(e["enrichment"] == "none" for e in records[0]["judged"])


def test_line_numbers_survive_unicode_line_separators(jr):
    """str.splitlines() splits on U+2028 / form feed; tree-sitter rows and
    diff line numbers count "\\n" only. The text sent to the model must not
    shift."""
    _ts()
    src = 'const s = "a\u2028b";\nfunction b() {\n  return 2;\n}\n'
    ctx = jr._ts_ast_context(src, "ts", 3)
    assert ctx["symbols"]["b"] == "function b() {"
    assert ctx["context"][0] == "function b() {"
    assert ctx["enclosing"] == "b"


def test_js_class_field_arrow_and_destructuring(jr):
    _ts()
    js = "class A {\n  h = () => {\n    return 1;\n  };\n}\n"
    assert jr._ts_ast_context(js, "js", 3)["enclosing"] == "A.h"
    ts = "const { a, b } = obj;\nexport function f() {\n  return a;\n}\n"
    assert set(jr._ts_ast_context(ts, "ts", 3)["symbols"]) == {"f"}


def test_parse_is_cached_per_image(jr):
    _ts()
    src = _read("sample.ts")
    jr.clear_runtime_caches()
    jr._ts_ast_context(src, "ts", 3)
    first = jr._ts_parse(src, "ts")
    jr._ts_ast_context(src, "ts", 8)
    assert jr._ts_parse(src, "ts") is first


# ---------- character budget ----------

def _table_chars(symbols):
    return sum(len(k) + len(v) for k, v in symbols.items())


def test_symbol_table_char_budget_keeps_head_in_order(jr):
    _ts()
    pad = "a" * 90
    names = [f"fn{i:02d}" for i in range(40)]
    src = "".join(f"export function {n}(x: number, {pad}: string): number {{}}\n"
            for n in names)
    assert all(len(ln) > 120 for ln in src.splitlines())
    ctx = jr._ts_ast_context(src, "ts", 1)
    got = list(ctx["symbols"])
    assert 0 < len(got) < 40
    assert _table_chars(ctx["symbols"]) <= jr.ENRICHMENT_MAX_TABLE_CHARS
    assert got == names[:len(got)]
    # the next entry is what would not fit
    nxt = len(names[len(got)]) + len(src.splitlines()[len(got)])
    assert _table_chars(ctx["symbols"]) + nxt > jr.ENRICHMENT_MAX_TABLE_CHARS


def test_very_long_line_is_clipped_in_table_and_window(jr):
    _ts()
    lim = jr.ENRICHMENT_MAX_LINE_CHARS
    src = "export function f(" + "a, " * 1700 + "b) {\n  return 1;\n}\n"
    assert len(src.splitlines()[0]) > 5000
    ctx = jr._ts_ast_context(src, "ts", 2)
    assert len(ctx["symbols"]["f"]) == lim
    assert ctx["symbols"]["f"].endswith("\u2026")
    assert ctx["symbols"]["f"].startswith("export function f(a, a,")
    assert len(ctx["context"][0]) == lim and ctx["context"][0].endswith("\u2026")
    assert ctx["context"][1:] == ["  return 1;", "}"]


def test_short_lines_are_not_clipped(jr):
    _ts()
    line = "export function f(" + "a" * 100 + "): void {"
    assert len(line) < jr.ENRICHMENT_MAX_LINE_CHARS
    ctx = jr._ts_ast_context(line + "\n}\n", "ts", 1)
    assert ctx["symbols"]["f"] == line and ctx["context"][0] == line


# ---------- enclosing-span tie-break ----------

def test_enclosing_span_tie_goes_to_deeper_chain(jr):
    """Identical start and end: the longer chain wins (it encloses less)."""
    spans = [(3, 5, ["A"]), (3, 5, ["A", "m"]), (3, 5, ["B"])]
    assert jr._ts_enclosing_span(spans, 4)[2] == ["A", "m"]
    assert jr._ts_enclosing_span(list(reversed(spans)), 4)[2] == ["A", "m"]
    # narrower span still beats a deeper chain; later start breaks ties first
    assert jr._ts_enclosing_span([(1, 9, ["X", "y", "z"]), (2, 8, ["Q"])],
                                 4)[2] == ["Q"]
    assert jr._ts_enclosing_span([(1, 5, ["P"]), (2, 6, ["Q"])], 3)[2] == ["Q"]


def test_real_parse_same_span_symbols_resolve_to_deeper(jr):
    """One-line class expression and nested namespaces produce two symbol
    nodes with the same span; the inner symbol must win."""
    _ts()
    cls = "const C = class { m() { return 1; } };\n"
    assert jr._ts_ast_context(cls, "ts", 1)["enclosing"] == "C.m"
    ns = "namespace A { namespace B { const x = 1; } }\n"
    assert jr._ts_ast_context(ns, "ts", 1)["enclosing"] == "A.B"
