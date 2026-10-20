# Test-file reflex class and locator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Judge, tag and log test-file units but hold them out of the surfaced findings by default, and add a locator (`where`) to every surfaced finding.

**Architecture:** A deterministic `reflex_class(path)` stamps each judged unit `test` or `code`. `compose()` takes a `hold_classes` argument (default `("test",)`) and leaves held classes out of `reported`; it stays the single place that decides what is surfaced, so the A/B harness, the sweep and the corpus scorer agree with `main()`. After `compose()` and the 5-cap, `main()` computes `where = {symbol, line}` for the at most five surfaced findings from the file image, independent of enrichment.

**Tech Stack:** Python 3.10+ stdlib; tree-sitter (optional, lazy) already used by the TS enrichment; pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-20-test-file-class-and-locator.md` (read it first; it wins on intent).

## Global Constraints

- No extra model calls. Held units are still judged.
- `reflex_class` values are exactly `"test"` and `"code"`. A finding or ledger entry with no `reflex_class` is `"code"` (older ledgers replay unchanged).
- `compose(findings, skipped, pr_level, threshold=REAL_THRESHOLD, deletion_threshold=DELETION_REAL_THRESHOLD, hold_classes=("test",))`. A finding is left out of `reported` when `f.get("reflex_class", "code") in hold_classes`. Jitter accounting is unchanged.
- The 5-finding cap and the ranking in `main()` apply AFTER the hold.
- New flag `--include-test-findings` passes `hold_classes=()`.
- `meta.n_test_held` is the number of findings that would have been surfaced but were held. One report line: `N test-file finding(s) held back; --include-test-findings shows them`.
- `where = {"symbol": <dotted chain or None>, "line": <anchor hunk.line>}` on each surfaced finding, computed from the file image after the cap, never from `ast_context`; deletion-only units use the pre-image; any failure gives `symbol: None`; no source text.
- The ledger record never receives finding source lines (the existing `lines` strip stays); it may carry `where` and `reflex_class`.
- `record_version` and `packaging_version` stay `v09`.
- Test path rule, matched case-insensitively on `/`-normalised paths: a DIRECTORY segment exactly one of `tests`, `test`, `__tests__`, `__mocks__`, `spec`, `specs`, `e2e`; or a filename matching `*.test.*`, `*.spec.*`, `test_*.*`, `*_test.*`, or equal to `conftest.py`. Not matched: `testing`, `test-utils`, `testutils`, `fixtures`.
- Python 3.10 compatible; ruff line length 100; mypy `check_untyped_defs`; match surrounding comment density and idiom.
- Tooling: wheels venv `/private/tmp/claude-502/-Users-equationalapplications-code-src-github-com-equationalapplications-system-one-reviewer/9215851b-ce55-4a67-8bee-31885431a182/scratchpad/venv2/bin/` (ruff, mypy, python -m pytest); no-wheels venv `.../scratchpad/venv/bin/`. Scratch files only under `.../scratchpad/<task>/`.
- Every new test is mutation-checked in a scratch COPY (never the repo).

## File Structure

- `system_one_reviewer.py`: `reflex_class`, `compose` hold, stamping in `main()`, flag, `n_test_held`, render lines (Tasks 1, 2); `locate` and `where` (Task 3).
- `scripts/sweep-thresholds.py`, `scripts/enrichment_ab.py`: carry the stamp through replays (Task 4).
- `tests/test_reflex_class.py`, `tests/test_test_class_hold.py` (new, Tasks 1-2); `tests/test_locator.py` (new, Task 3); `tests/test_sweep.py`, `tests/test_enrichment_scripts.py` (extend, Task 4).
- `docs/founding/ROADMAP.md`, `README.md`, `INTENT.md` (Task 5).

---

### Task 1: `reflex_class`

**Files:**
- Modify: `system_one_reviewer.py` (add `import fnmatch` in the stdlib import block; add the constants and function next to the other path helpers, before `compose`)
- Test: `tests/test_reflex_class.py` (create)

**Interfaces:**
- Produces: `reflex_class(path: str | None) -> str` returning `"test"` or `"code"`; module constants `TEST_DIRS` (frozenset) and `TEST_NAME_PATTERNS` (tuple of fnmatch patterns).

- [ ] **Step 1: Write the failing test** (`tests/test_reflex_class.py`)

```python
"""reflex_class: path-only classification of test files (deterministic)."""

import pytest


@pytest.mark.parametrize("path,expected", [
    # the five field firings (issue #26)
    ("integrations/deepseek/src/index.ts", "code"),
    ("__tests__/drawerTermsGate.test.tsx", "test"),
    ("__tests__/acceptTermsScreen.test.tsx", "test"),
    ("tests/unit/memory-transfer.test.ts", "test"),
    ("packages/ct-wisdom-core/src/spawn.ts", "code"),
    # directory segments
    ("src/tests/helpers.ts", "test"),
    ("src/test/Foo.java", "test"),
    ("pkg/__mocks__/fs.js", "test"),
    ("spec/models/user_spec.rb", "test"),
    ("web/e2e/login.ts", "test"),
    # filename patterns
    ("src/foo.test.ts", "test"),
    ("src/foo.spec.js", "test"),
    ("pkg/test_utils.py", "test"),
    ("pkg/foo_test.go", "test"),
    ("src/foo_test.ts", "test"),
    ("conftest.py", "test"),
    ("pkg/conftest.py", "test"),
    # deliberately NOT test: product or infrastructure code
    ("src/testing/clock.ts", "code"),
    ("packages/test-utils/src/index.ts", "code"),
    ("packages/testutils/index.ts", "code"),
    ("src/fixtures/seed.ts", "code"),
    ("src/contest.py", "code"),
    ("src/latest.ts", "code"),
    # normalisation
    ("SRC\\Tests\\Foo.TS", "test"),
    ("Src/TESTS/foo.ts", "test"),
    # a FILE named like a directory is not a test directory
    ("src/test", "code"),
    ("", "code"),
    (None, "code"),
])
def test_reflex_class(jr, path, expected):
    assert jr.reflex_class(path) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `.../venv2/bin/python -m pytest tests/test_reflex_class.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'reflex_class'`).

- [ ] **Step 3: Implement** (system_one_reviewer.py)

```python
TEST_DIRS = frozenset({"tests", "test", "__tests__", "__mocks__",
                       "spec", "specs", "e2e"})
TEST_NAME_PATTERNS = ("*.test.*", "*.spec.*", "test_*.*", "*_test.*")


def reflex_class(path):
    """"test" for test files, else "code", from the path alone (INTENT
    rule 2: deterministic preparation). A DIRECTORY segment in TEST_DIRS or a
    filename matching TEST_NAME_PATTERNS (or conftest.py) is a test. testing/,
    test-utils/ and fixtures/ are deliberately not matched: they are often
    product or infrastructure code."""
    parts = [s for s in (path or "").replace("\\", "/").lower().split("/") if s]
    if not parts:
        return "code"
    if any(seg in TEST_DIRS for seg in parts[:-1]):
        return "test"
    name = parts[-1]
    if name == "conftest.py" or any(fnmatch.fnmatchcase(name, pat)
                                    for pat in TEST_NAME_PATTERNS):
        return "test"
    return "code"
```

- [ ] **Step 4: Run to verify it passes**, then `ruff check .` and `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): drop `parts[:-1]` to `parts`, remove `.lower()`, remove `"*_test.*"`, remove `conftest.py`; each must fail a test case.

---

### Task 2: Hold the `test` class in `compose()`; stamp, flag, counts, report line

**Files:**
- Modify: `system_one_reviewer.py` (`compose` ~line 3566; `main()` around the `compose(` call ~4102, the `judged = [...]` list ~4160, the `result = {...}` dict ~4201, argparse near `--no-enrichment`; `render` ~3816)
- Test: `tests/test_test_class_hold.py` (create)

**Interfaces:**
- Consumes: `reflex_class(path)` from Task 1.
- Produces: `compose(..., hold_classes=("test",))`; findings and ledger `judged` entries carry `reflex_class`; `meta["n_test_held"]: int`; flag `args.include_test_findings`.

- [ ] **Step 1: Write the failing tests** (`tests/test_test_class_hold.py`)

```python
"""compose() holds the test class out of what is surfaced; main() stamps,
counts and reports it. The class is judged and ledgered either way."""

import json

from test_enrichment import _add_file_diff


def _f(file, is_real=0.95, severity=3.0, cls=None, rubric="code-change"):
    f = {"hunk": {"file": file, "line": 1}, "is_real": is_real,
         "severity": severity, "category": "bug-risk", "rubric": rubric,
         "parse_error": None}
    if cls is not None:
        f["reflex_class"] = cls
    return f


def test_compose_holds_test_class_by_default(jr):
    findings = [_f("a.ts", cls="code"), _f("a.test.ts", cls="test")]
    reported, _, _ = jr.compose(findings, [], None, threshold=0.8)
    assert [f["hunk"]["file"] for f in reported] == ["a.ts"]


def test_compose_surfaces_test_class_when_not_held(jr):
    findings = [_f("a.ts", cls="code"), _f("a.test.ts", cls="test")]
    reported, _, _ = jr.compose(findings, [], None, threshold=0.8,
                                hold_classes=())
    assert len(reported) == 2


def test_compose_treats_a_missing_stamp_as_code(jr):
    reported, _, _ = jr.compose([_f("a.test.ts")], [], None, threshold=0.8)
    assert len(reported) == 1   # older ledgers replay unchanged


def test_compose_jitter_is_unchanged_by_the_hold(jr):
    f = _f("a.test.ts", is_real=0.81, cls="test")
    reported, jitter, _ = jr.compose([f], [], None, threshold=0.8)
    assert reported == [] and jitter and jitter[0]["file"] == "a.test.ts"


def _run(jr, monkeypatch, tmp_path, capsys, path, extra=(), is_real=0.95):
    diff = _add_file_diff(path, ["def f():", "    return 1"])
    records: list = []
    monkeypatch.setattr(jr, "judge", lambda kept, ask, errors=None, split_unit=None: (
        [{"hunk": h, "severity": 3.0, "is_real": is_real, "category": "bug-risk",
          "rubric": "code-change", "references_remaining": None,
          "change_type": h.get("change_type", "code-change"), "latency_ms": 1.0}
         for h in kept], [1.0] * len(kept),
        {"added_units": 0, "avg_input_tokens": None}))
    monkeypatch.setattr(jr, "judge_pr_level", lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff", lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", lambda *a, **k: (None, "def f():\n    return 1\n"))
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr.sys, "argv", ["system-one-reviewer", "--repo", str(tmp_path),
                                         "--staged", "--provider", "jev", "--json", *extra])
    jr.main()
    return json.loads(capsys.readouterr().out), records


def test_main_judges_stamps_and_holds_a_test_file_unit(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "tests/test_m.py")
    assert out["findings"] == []
    assert out["meta"]["n_test_held"] == 1
    judged = records[0]["judged"]
    assert len(judged) == 1                       # still judged and logged
    assert judged[0]["reflex_class"] == "test" and judged[0]["reported"] is False


def test_main_surfaces_it_with_include_test_findings(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "tests/test_m.py",
                        extra=("--include-test-findings",))
    assert len(out["findings"]) == 1
    assert out["meta"]["n_test_held"] == 0
    assert records[0]["judged"][0]["reflex_class"] == "test"
    assert records[0]["judged"][0]["reported"] is True


def test_main_code_file_is_unaffected(jr, monkeypatch, tmp_path, capsys):
    out, records = _run(jr, monkeypatch, tmp_path, capsys, "src/m.py")
    assert len(out["findings"]) == 1 and out["meta"]["n_test_held"] == 0
    assert records[0]["judged"][0]["reflex_class"] == "code"


def test_report_says_when_findings_were_held(jr):
    meta = {"repo": "r", "mode": "staged", "head": "0" * 40, "provider": "jev",
            "n_hunks": 1, "n_test_held": 2, "latencies": [1.0]}
    text = jr.render([], [], "OK", None, [], meta)
    assert "2 test-file finding(s) held back" in text
    assert "--include-test-findings" in text
    meta["n_test_held"] = 0
    assert "held back" not in jr.render([], [], "OK", None, [], meta)
```

(If `render` needs more `meta` keys than the test supplies, read `render` and add exactly the ones it indexes; do not weaken the assertions.)

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement**
  - `compose`: add the `hold_classes=("test",)` parameter and, inside the loop, after the existing `r >= t and severity >= 1` condition holds, `if f.get("reflex_class", "code") in hold_classes: continue` before `reported.append(f)`. Update the docstring (one sentence: held classes are judged and logged but not surfaced).
  - `main()`: after the judge returns `findings` (and before `compose`), stamp every non-`parse_error` finding: `f["reflex_class"] = reflex_class(f["hunk"]["file"])`. Read how `findings` is built and when it is `None` (fail-open) so the stamp loop is safe.
  - Add `ap.add_argument("--include-test-findings", dest="include_test_findings", action="store_true", help="surface test-file findings too (measurement; default holds them back, they are still judged and logged)")`.
  - Call `compose(..., hold_classes=() if args.include_test_findings else ("test",))`. Compute `n_test_held`: call `compose` a second time with `hold_classes=()` and count findings in that result that are not in the first result; set `meta["n_test_held"]` (0 when `--include-test-findings`).
  - `judged` entries: add `"reflex_class": f.get("reflex_class", "code")`.
  - `result["findings"]` entries: add `"reflex_class": f.get("reflex_class", "code")`.
  - `render`: after the findings loop and before the jitter block, `if meta.get("n_test_held"): out.append(f"{meta['n_test_held']} test-file finding(s) held back; --include-test-findings shows them"); out.append("")`.

- [ ] **Step 4: Run** `tests/test_test_class_hold.py`, then the full suite (`python -m pytest -q`, wheels and no-wheels), `ruff check .`, `mypy`. Existing tests that build findings with test-like paths may now hold them: fix such tests only by giving them a non-test path or `hold_classes=()`, and list each one you changed.
- [ ] **Step 5: Mutation-check** (scratch copy): remove the `continue`; default `hold_classes` to `()`; skip the stamp loop; hardcode `n_test_held = 0`; drop the render line; each must fail a test.

---

### Task 3: The locator (`where`)

**Files:**
- Modify: `system_one_reviewer.py` (new `locate`, called in `main()` after the 5-cap; `result["findings"]` entries; `render`)
- Test: `tests/test_locator.py` (create)

**Interfaces:**
- Consumes: `_enclosing_chain(src, lineno)` (Python, existing), `_ts_ast_context(src, ext, lineno, loader=None)` (TS/JS, existing, returns `{"enclosing": ...}` or `None`), `TS_LANGUAGE_BY_EXT`.
- Produces: `locate(path, pre, post, unit) -> {"symbol": str | None, "line": int}`; each surfaced finding gets `f["where"]`; `--json`/`--out` findings carry `"where"`; the report prints `  in <symbol>` under the finding header when a symbol resolves.

- [ ] **Step 1: Write the failing tests** (`tests/test_locator.py`)

```python
"""locate(): where to look, never what is wrong. Independent of enrichment."""

import pytest

PY = "class A:\n    def m(self):\n        return 1\n\n\ndef top():\n    return 2\n"
TS = ("export class Service {\n  run(job: string): void {\n"
      "    const cb = () => job.length;\n    cb();\n  }\n}\n")


def _unit(path, line, **kw):
    return {"file": path, "line": line, "change_type": "code-change",
            "entries": [("+", line, "x", line)], **kw}


def test_python_symbol(jr):
    assert jr.locate("m.py", None, PY, _unit("m.py", 3)) == {"symbol": "A.m", "line": 3}
    assert jr.locate("m.py", None, PY, _unit("m.py", 7)) == {"symbol": "top", "line": 7}


def test_module_level_is_none(jr):
    assert jr.locate("m.py", None, "x = 1\n", _unit("m.py", 1)) == {"symbol": None, "line": 1}


def test_ts_symbol(jr):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    got = jr.locate("m.ts", None, TS, _unit("m.ts", 3))
    assert got == {"symbol": "Service.run.cb", "line": 3}
    assert jr.locate("m.ts", None, TS, _unit("m.ts", 4))["symbol"] == "Service.run"


def test_deletion_only_uses_the_pre_image(jr):
    pre = "def gone():\n    return 1\n\n\ndef kept():\n    pass\n"
    post = "def kept():\n    pass\n"
    unit = {"file": "m.py", "line": 1, "change_type": "deletion-only",
            "entries": [("-", 2, "    return 1", 2)]}
    assert jr.locate("m.py", pre, post, unit)["symbol"] == "gone"


@pytest.mark.parametrize("pre,post", [(None, None), (None, ""), ("", "")])
def test_no_image_gives_none(jr, pre, post):
    assert jr.locate("m.py", pre, post, _unit("m.py", 1)) == {"symbol": None, "line": 1}


def test_syntax_error_and_unknown_language_fail_open(jr):
    assert jr.locate("m.py", None, "def (:\n", _unit("m.py", 1))["symbol"] is None
    assert jr.locate("m.rb", None, "def a\nend\n", _unit("m.rb", 1))["symbol"] is None


def test_never_raises(jr, monkeypatch):
    monkeypatch.setattr(jr, "_enclosing_chain",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert jr.locate("m.py", None, PY, _unit("m.py", 3)) == {"symbol": None, "line": 3}
```

Add an end-to-end test (same driver pattern as Task 2's `_run`, serving a Python image through `mode_file_images`) asserting: a surfaced finding in `--json` has `where == {"symbol": ..., "line": ...}`; the stdout/`--out` finding for `--no-enrichment` has the SAME `where`; and the rendered report contains `  in <symbol>`.

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement**

```python
def locate(path, pre, post, unit):
    """Where to look for a surfaced finding: the dotted enclosing symbol at the
    anchor line (None if none resolves) and the anchor line. Deterministic, no
    claim, no source text, and independent of ast_context so --no-enrichment,
    missing wheels or a context dropped at re-expansion do not change it.
    Deletion-only units use the pre-image. Fails open."""
    line = unit["line"]
    src, lineno = post, line
    if unit.get("change_type") == "deletion-only" and pre:
        first = next((e for e in unit.get("entries", []) if e[0] == "-"), None)
        src, lineno = pre, (first[1] if first is not None else line)
    symbol = None
    if src:
        ext = os.path.splitext(path or "")[1].lower().lstrip(".")
        try:
            if ext in TS_LANGUAGE_BY_EXT:
                ctx = _ts_ast_context(src, ext, lineno)
                symbol = ctx["enclosing"] if ctx else None
            elif ext == "py":
                symbol = _enclosing_chain(src, lineno)
        except Exception:
            symbol = None
    return {"symbol": symbol, "line": line}
```

In `main()`, after the `sorted(...)[:5]` cap, for each `f in reported`: `pre, post = mode_file_images(args.repo, mode, head, f["hunk"]["file"], old_file=f["hunk"].get("old_file"))` inside `try/except Exception` (an image failure gives `pre = post = None`), then `f["where"] = locate(f["hunk"]["file"], pre, post, f["hunk"])`. Add `"where": f.get("where")` to the `result["findings"]` entries. In `render`, after the `[sev] file:line (...)` line add `if (f.get("where") or {}).get("symbol"): out.append(f"  in {f['where']['symbol']}")`. Define the images call outside the `if provider == "jev" and kept:` block's lambda so it works for laya too (a plain call to `mode_file_images`, as the lambda does).

- [ ] **Step 4: Run** the new tests, the full suite (both venvs), `ruff`, `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): use `post` for deletion-only; drop the `try/except`; read `ctx["enclosing"]` without the `None` check; derive from `unit["ast_context"]`; drop `where` from the result dict; each must fail a test.

---

### Task 4: Replay paths carry the stamp; the harness gets the flag

**Files:**
- Modify: `scripts/sweep-thresholds.py` (`rewrap`), `scripts/enrichment_ab.py` (`surfaced`, argument, subprocess command)
- Test: `tests/test_sweep.py`, `tests/test_enrichment_scripts.py`

**Interfaces:**
- Consumes: `compose(..., hold_classes=...)` and the `reflex_class` key (Task 2).
- Produces: `rewrap(j, ...)` output includes `"reflex_class": j.get("reflex_class", "code")` (so `scripts/score_corpus.py`, which calls `sw.rewrap`, follows automatically); `enrichment_ab.surfaced(judged, include_test=False)`; harness flag `--include-test-findings` forwarded to the reviewer command of both arms and to `surfaced`.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_sweep.py`: a `rewrap` of an entry with `reflex_class: "test"` carries it; one without the key rewraps to `"code"`; `replay()` of a run whose only gate-crosser is a `test` entry returns no findings, and returns it for an old-style entry with no key (historical replay unchanged).
  - `tests/test_enrichment_scripts.py`: `surfaced()` omits a gate-crossing `test` entry by default and includes it with `include_test=True`; `main` with `--include-test-findings` forwards the flag in the subprocess command of both arms (inspect `cmd` in the fake subprocess) and counts the test entry; without the flag it does not.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** the pass-through in `rewrap`; in `surfaced` add `"reflex_class": j.get("reflex_class", "code")` to each finding dict and `hold_classes=() if include_test else ("test",)` to the `compose` call; add `ap.add_argument("--include-test-findings", dest="include_test_findings", action="store_true")` to the harness, append it to `cmd` in `run_one` when set, and pass `include_test=args.include_test_findings` wherever `surfaced` is called. Update the module docstring (one sentence).
- [ ] **Step 4: Run** the two test files and the whole suite; `ruff`, `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): drop the rewrap key; drop the `surfaced` stamp; do not forward the flag; each must fail a test.

---

### Task 4b: `--include-test-findings` for the sweep and the corpus scorer (added after review)

Measurement baselines need golden replays that can still score a test-file row
(Stage A: `custody-stack.test.ts:200`). `scripts/sweep-thresholds.py`
(`replay`, `negative_fp`, `sweep`, `field_fp`, `sweep_field`, `main`) and
`scripts/score_corpus.py` (`replay_indices`, `score_sample`, `score`,
`replay_grid`, `main`) take `--include-test-findings` / `include_test`,
passing `hold_classes=()` to `compose`; default output is unchanged and the
setting is printed only when on. Tests and mutation checks live in
`tests/test_sweep.py` and `tests/test_score_corpus.py`.

### Task 5: Docs

**Files:**
- Modify: `docs/founding/ROADMAP.md` (S3), `README.md`, `INTENT.md` (rule 4 status), `docs/superpowers/specs/2026-10-20-test-file-class-and-locator.md` (resolve the two open questions)

- [ ] **Step 1: ROADMAP S3** records the first shipped class: the test-file rule (the exact path rule from Global Constraints), that it is judged-and-held, `--include-test-findings`, and that the other S3 classes (docs-only, lockfile, generated, rename-only, whitespace-only) remain planned. The class list lives here, not in INTENT.
- [ ] **Step 2: README** documents `--include-test-findings`, the `where` field, `meta.n_test_held`, and the report line, in the existing flag/output sections.
- [ ] **Step 3: INTENT rule 4 status** gets one sentence: test-file findings are judged and logged but held back by default, with the evidence (issue #26 field data) and a pointer to the spec. Do not restate the path list.
- [ ] **Step 4: Spec open questions** become decisions: no `held` list in `--json` (a count in `meta` only; hosts read the ledger); the class list lives in ROADMAP S3.
- [ ] **Step 5:** `grep -rn "held back\|include-test-findings"` across docs and README to confirm consistent wording; no code changes in this task.

---

### Task 6: Gates and PR (controller)

- [ ] Full suite with and without wheels, `ruff check .`, `mypy`.
- [ ] Review the combined diff once; run one Sonnet review at high depth; fix findings.
- [ ] Commit per task with conventional messages; the PR title is `feat: hold test-file findings by default and add a locator to surfaced findings` (squash-merge cuts a minor release).
- [ ] The PR body states what is unmeasured and links issue #26.

## Self-Review

- **Spec coverage:** classification (T1), hold and flag and counts and report line (T2), locator (T3), replay paths (T4), ROADMAP/README/INTENT and open questions (T5), validation list items 1-6 map to the tests in T1-T4. Post-release evaluation is out of the plan, as in the spec.
- **Placeholders:** none; the one conditional ("add the `meta` keys `render` needs") is bounded by an instruction not to weaken assertions.
- **Type consistency:** `reflex_class` (str), `hold_classes` (tuple of str), `where` (dict with `symbol`, `line`), `n_test_held` (int) are used with the same names in every task.
