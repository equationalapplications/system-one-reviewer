# `--input` mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `system-one-reviewer --input FILE|-` reviews before/after file texts supplied as JSON, with no git and no subprocess.

**Architecture:** Validate the JSON up front; synthesize a git-shaped unified diff per file in memory; register the before/after texts in a module-level map; add a mode `input` to `mode_file_images` that answers from the map; `main()` calls a new `resolve_input` instead of `resolve_diff`. No downstream caller changes.

**Tech Stack:** Python 3.10+ stdlib (`json`, `difflib`); pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-20-input-mode.md` (read it first; it wins on intent and rationale, this plan orders the work and fixes the interfaces).

## Global Constraints

- Stdlib only; the tool stays a single file (`system_one_reviewer.py`). Python 3.10 compatible; ruff line length 100; mypy `check_untyped_defs`; match surrounding comment density and idiom.
- Constants (module level, named exactly): `INPUT_MAX_BYTES = 64 * 1024 * 1024`, `INPUT_MAX_FILES = 2000`, `INPUT_MAX_TOTAL_LINES = 1_000_000`, `INPUT_MAX_FILE_CHARS = 2 * 1024 * 1024`, `INPUT_MAX_FILE_LINES = 20_000`, `INPUT_MATCH_LINES = 3000`, `INPUT_MAX_LABEL_CHARS = 200`.
- `class InputError(Exception)`: str(e) is the reason; optional attribute `where` (for example `files[3].path`). A rejection prints `system-one-reviewer: --input: <reason> (<where>)` to stderr (the `(<where>)` part omitted when there is none) and exits **2**. Paths are echoed only through `repr()` truncated to 120 characters; file contents are never echoed.
- Flag conflicts (`--input` with `--repo`/`--range`/`--pr`/`--staged`/`--uncommitted`, or neither `--input` nor `--repo`) use `ap.error()` (exit 2). `--repo` is no longer `required=True`.
- Input is read, validated and turned into a diff BEFORE `load_api_key()` and before any model call.
- Control characters in paths: `ord(c) < 0x20 or ord(c) == 0x7F`. `/dev/null` is rejected as a path. Backslashes are normalised to `/`.
- Skip record shape: `{"file": <path>, "reason": <reason>, "line_start": 1, "line_end": 1}`. Reasons: `input-binary` (deliberate triage) and `hunk>input-oversize` (counts toward `size_skipped_code`, so the run reads "incomplete review").
- The mode string is exactly `"input"`; default ledger label `auto:input`; `meta.repo` is the input's `repo` label (default `"input"`); `meta.n_input_autojunk` is an int (0 when none).
- Input mode never shells out: tests that exercise it run with `git` removed from `PATH`.
- Every new test is mutation-checked in a scratch COPY of the repo (never the repo).
- Tooling: wheels venv `/private/tmp/claude-502/-Users-equationalapplications-code-src-github-com-equationalapplications-system-one-reviewer/9215851b-ce55-4a67-8bee-31885431a182/scratchpad/venv2/bin/` (ruff, mypy, python -m pytest); no-wheels venv `.../scratchpad/venv/bin/` (pytest). Scratch files only under `.../scratchpad/<task>/`.

## File Structure

- `system_one_reviewer.py`: all new code (input constants, `InputError`, `load_input`, `validate_input`, `split_lines`, `synthesize_file_diff`, `build_input`, `_INPUT_IMAGES` and its setter/clearer, the `input` branch of `mode_file_images`, `resolve_input`, argparse and `main()` wiring). Tasks 1-3 edit it SEQUENTIALLY, never concurrently.
- `tests/test_input_validation.py` (Task 1), `tests/test_input_diff.py` (Task 2), `tests/test_input_mode.py` (Task 3): new.
- `AGENTS.md`, `README.md`, `INTENT.md` (Task 4, docs only, parallel with Task 1).

---

### Task 1: Reading, validation and argument wiring

**Files:**
- Modify: `system_one_reviewer.py` (constants and `InputError` near the other module constants; `load_input` and `validate_input` before `resolve_diff`; the argparse block in `main()`)
- Test: `tests/test_input_validation.py` (create)

**Interfaces:**
- Produces: `load_input(source: str) -> dict` (`"-"` reads stdin, else a file path; at most `INPUT_MAX_BYTES + 1` bytes are read and more is rejected; strips a leading BOM; `json.loads` with `parse_constant` rejecting `NaN`/`Infinity`; `RecursionError` and decode errors become `InputError("not JSON ...")`); `validate_input(doc: dict) -> dict` returning `{"head": str, "repo": str, "files": [{"path", "old_path", "before", "after"}]}` with normalised paths, files whose `before == after` and no rename dropped, raising `InputError` for every rejection in the spec's "Reading and validating" list (types, empty head/path, duplicate path after normalisation, > `INPUT_MAX_FILES`, total lines > `INPUT_MAX_TOTAL_LINES`, lone surrogates via `.encode("utf-8")`, control characters, `/dev/null`, `head`/`repo` longer than `INPUT_MAX_LABEL_CHARS`, both `before` and `after` null).
- Produces: `args.input` (`--input FILE|-`); `--repo` optional; the conflict rules via `ap.error`.

- [ ] **Step 1: Write failing tests** covering the whole validation matrix: valid minimal doc; BOM accepted; `NaN`; deep nesting (`"[" * 100000`); not an object; `files` not a list; wrong types for each key; missing/empty `head` and `path`; duplicate path and duplicate-after-backslash-normalisation (`a\b` vs `a/b`); 2,001 files; total lines over the cap (use a lowered cap via monkeypatching the constant); lone surrogate in `before`, `path` and `head`; `\n`, `\t`, `\x7f` in a path; `/dev/null`; label too long; both null; `before == after` dropped and a rename with equal texts kept; unknown keys ignored; empty `files` valid. For each rejection assert `InputError`, the reason text, `where`, and that the message never contains file contents. CLI tests (drive `main()` with a stubbed provider and `load_api_key` that fail the test if called): each rejection prints the documented stderr line and exits 2 BEFORE `load_api_key`; flag conflicts exit 2 with usage; `--input -` reads stdin (monkeypatch `sys.stdin`); a file larger than the cap is rejected after reading at most cap + 1 bytes.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** the constants, `InputError`, `load_input`, `validate_input`, the argparse changes, and the call order in `main()` (parse and validate right after `parse_args`, before `load_api_key`). In this task `main()` may stop after validation with a clear internal error such as `NotImplementedError` when `--input` is given and valid; Task 3 completes the wiring. Do NOT build diffs here.
- [ ] **Step 4: Run** the new tests, the full suite in both venvs, `ruff check .`, `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): drop `parse_constant`, the surrogate check, the control-character check, the duplicate check, the `+1` read cap, the BOM strip, the `/dev/null` check; each must fail a test.

---

### Task 2: Line model and diff synthesis

**Files:**
- Modify: `system_one_reviewer.py` (after Task 1's code)
- Test: `tests/test_input_diff.py` (create)

**Interfaces:**
- Consumes: the normalised file entries from `validate_input`.
- Produces:
  - `split_lines(text: str) -> list[str]`: each element keeps its `"\n"`; a final element without `"\n"` is the no-newline line; `""` gives `[]`:
    ```python
    def split_lines(text):
        if not text:
            return []
        parts = text.split("\n")
        last = parts.pop()
        lines = [p + "\n" for p in parts]
        if last:
            lines.append(last)
        return lines
    ```
  - `synthesize_file_diff(entry: dict) -> tuple[str, bool]`: the git-shaped block for one file and whether the `autojunk=True` fallback was used. Header forms exactly as in the spec ("Diff synthesis"): `diff --git a/<old_or_path> b/<path>`; `new file mode 100644` / `deleted file mode 100644` / `rename from <old>` + `rename to <path>`; `--- a/<old_or_path>` or `--- /dev/null`; `+++ b/<path>` or `+++ /dev/null`; hunks `@@ -a,b +c,d @@` (omit `,1`; use `,0` for an empty side; the start of an empty side is `0` for `-0,0` / `+0,0` only when that side is empty, otherwise 1-based); lines prefixed ` `, `-`, `+`; a line lacking `"\n"` is followed by `\ No newline at end of file` once per side. An added or deleted EMPTY file and a pure rename (equal texts) emit headers only, with no `---`/`+++`.
  - Matching: strip the common leading and trailing lines first; if both cores are at most `INPUT_MATCH_LINES` lines use `difflib.SequenceMatcher(None, a, b, autojunk=False)`, else `autojunk=True` (return flag True); take `get_grouped_opcodes(3)` of the core, shift indices back by the stripped prefix length, and re-add up to 3 lines of context from the stripped prefix/suffix as needed so the output equals what `get_grouped_opcodes(3)` on the full sequences would give where the minimal diff is unique.
  - `build_input(doc: dict) -> dict` returning `{"diff": str, "head": str, "repo": str, "skipped": list, "images": {path: (before, after)}, "n_autojunk": int}`: per-file triage first (`input-binary` for a NUL in either side; `hunk>input-oversize` for more than `INPUT_MAX_FILE_CHARS` characters or `INPUT_MAX_FILE_LINES` raw lines on either side; skip records with the shape in Global Constraints; skipped files are not diffed and not in `images`), then synthesis in input order.

- [ ] **Step 1: Write failing tests**. Real-git comparison helper: create a throwaway repo in `tmp_path` with two commits (before, after), run `git diff` with `git -c core.quotePath=false`, normalise by dropping `index ` lines and everything after the second `@@` on a hunk header, and compare with `synthesize_file_diff` output. Cases: add, delete, modify, empty added file, empty deleted file, no trailing newline on one side, change that ONLY adds the final newline, change that ONLY removes the final newline, CRLF lines, a 250-line file with many repeated lines and one change, a change near the start and near the end of a file, two changes 6 lines apart (hunk merging) and 8 lines apart (two hunks), whole-file rewrite, a file with U+2028 and a form feed inside a line (lines must NOT be split there). Plus unit tests of `split_lines` (empty, `"a"`, `"a\n"`, `"a\n\nb"`, `"\n"`), the packager round trip (`package_hunks(synthesized)` yields clusters with the changed line numbers), skip records, `n_autojunk` counting, and the timing test: a 20,000-line all-blank file with one change finishes under one second; a 3,000-line two-symbol repetitive file with a mid-file shift finishes in a few seconds (assert < 10 s).
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** per the interfaces. Do not use `difflib.unified_diff`.
- [ ] **Step 4: Run** the new tests, the full suite in both venvs, `ruff check .`, `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): terminators outside the lines (so a final-newline-only change vanishes), `autojunk` forced True or False everywhere, no prefix/suffix strip (timing test must fail), drop the `\ No newline` marker, `,1` counts not omitted, wrong `,0` form, context 2 instead of 3; each must fail a test.

---

### Task 3: Images, `resolve_input`, `main()` wiring, end-to-end

**Files:**
- Modify: `system_one_reviewer.py` (`mode_file_images`, `clear_runtime_caches`, `resolve_input`, `main()`)
- Test: `tests/test_input_mode.py` (create)

**Interfaces:**
- Consumes: `build_input` (Task 2), `validate_input`/`load_input` (Task 1).
- Produces: module global `_INPUT_IMAGES: dict` and `set_input_images(images: dict) -> None`; `clear_runtime_caches()` also empties it; `mode_file_images(..., mode == "input", ...)` returns `_INPUT_IMAGES.get(path, (None, None))` before touching `repo`, `_IMAGE_CACHE` or git; `resolve_input(bundle) -> tuple[str, str, str]` returning `(diff, head, "input")` and calling `set_input_images`.

- [ ] **Step 1: Write failing tests**:
  1. `mode_file_images` input branch: null sides come back as `None`; unknown path gives `(None, None)`; does not call `subprocess`/`git_show_or_none` (monkeypatch them to raise); `clear_runtime_caches()` empties the map; two documents in one process do not collide.
  2. End to end through `main()` with a stub judge (pattern: `tests/test_out_lines.py::_run_out` and `tests/test_test_class_hold.py::_run`): `--input` over a doc with a Python modify, a TS add (skip the TS assertions without wheels), a delete and a rename produces a report; `meta.mode == "input"`, `meta.repo` is the label, ledger `mode == "input"`, label `auto:input`, `head` is the input's head, `meta.n_input_autojunk == 0`; the test-file hold, `where` and enrichment engage; `git` is removed from `PATH` (monkeypatch `PATH` to an empty temp dir) and `subprocess.run` is monkeypatched to raise.
  3. Equivalence: a throwaway git repo with two commits; run `main()` with `--range base..head` (stub `mode_file_images` NOT stubbed, real git) and with `--input` built from the same before/after texts; the judged units (file, line, span, lines) and the rendered report are equal apart from `mode`, `head`, `repo`. Exclude renames from this comparison.
  4. Skips: a binary file and an oversize CODE file appear in `skipped` with the documented shape; the oversize code file makes `status == "incomplete review"`; the rest of the doc is still reviewed; an all-skipped doc and an empty `files` array report an empty diff / nothing to review and still append a ledger record.
  5. `--golden`, `--negative-golden`, `--max-hunks`, `--label`, `--include-test-findings` work with `--input` (one assertion each, cheap).
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement**. In `main()` replace the placeholder from Task 1: after validation and BEFORE `load_api_key()`, build the bundle; `diff, head, mode = resolve_input(bundle)`; merge `bundle["skipped"]` into the run's `skipped` list at the point where `triage` results are combined (read how `triage(hunks)` output and `skipped` flow, and keep the banner denominator and `size_skipped_code` consistent); `meta["repo"] = bundle["repo"]`; `meta["n_input_autojunk"] = bundle["n_autojunk"]` (0 for the git modes, so the key is always present); pass `repo=None`-safe values everywhere `args.repo` is used (`mode_file_images` calls, `_runtime_split_unit_factory`, the locator call, `os.path.realpath(args.repo)`). Grep every use of `args.repo` and confirm none dereferences it in input mode.
- [ ] **Step 4: Run** the new tests, the full suite in both venvs, `ruff check .`, `mypy`.
- [ ] **Step 5: Mutation-check** (scratch copy): input branch ignores the map; map not cleared; `resolve_input` returns a mode other than `"input"`; skips not merged; validation after `load_api_key`; `meta.repo` still `basename(realpath(args.repo))`; each must fail a test.

---

### Task 4: Docs (parallel with Task 1; docs files only)

**Files:** `AGENTS.md`, `README.md`, `INTENT.md`

- [ ] **Step 1: AGENTS.md** "The interpreter gotcha": correct the sentence that says the E5 self-check makes measurement runs abort. The tool never aborts on missing wheels in any mode; it falls back to line windows and records `meta.wheels`; the aborts are in `scripts/enrichment_ab.py` and `scripts/enrichment_census.py`. Keep the advice to verify `python3 -c "import tree_sitter"` before any measurement run.
- [ ] **Step 2: README** documents `--input FILE|-` in Usage: the JSON contract (copy the example from the spec), the validation exit code 2, the caps, the skip reasons, the `mode: input` ledger stamp, that `head` should be the 40-hex SHA, the Lambda notes (API key, `JEV_REVIEW_METRICS=/tmp/...` until #25, wheels optional and silent with `meta.wheels`), and the difflib-versus-git limit.
- [ ] **Step 3: INTENT.md** gets one sentence in rule 2's Status line: `--input` supplies the pre/post images deterministically for hosts without git (pointer to the spec). No restatement of the contract.
- [ ] **Step 4:** `grep -rn "\-\-input" README.md INTENT.md AGENTS.md docs/` and confirm consistent wording.

---

### Task 5: Gates and PR (controller)

- [ ] Full suite with and without wheels, `ruff check .`, `mypy`, `ast.parse(feature_version=(3,10))` on changed files.
- [ ] One Sonnet review at high depth of the combined diff; fix findings.
- [ ] Commit per task; PR title `feat: --input mode, review before/after file images without git` (squash-merge cuts a minor release); the body states what is unmeasured, links the spec and `Closes #23`.

## Follow-up fixes after the second review (done)

Applied after a Sonnet high-depth review of the implementation: reject every
`splitlines()` boundary character (U+0085, U+2028, U+2029) in path, old_path,
head and repo; path length cap 1,024; closed stdin and `--range ""` handled;
`old_path` normalised for added/deleted files; head warning; exact matching
limited to 400 lines with a per-run budget (`INPUT_MATCH_BUDGET`) and a bounded
anchored fallback (`autojunk=True` was found to be unbounded); path triage
before the oversize check; `INPUT_MAX_LINE_CHARS`; the all-skipped banner;
`n_input_autojunk` in the ledger; boundary, round-trip and header-format tests.
The constants in Global Constraints above are the original plan values;
`INPUT_MATCH_LINES` is now 400 and `INPUT_MATCH_BUDGET`, `INPUT_MAX_PATH_CHARS`
and `INPUT_MAX_LINE_CHARS` were added.

## Self-Review

- **Spec coverage:** contract and validation (T1), line model, diff form, matching, caps and triage (T2), images, mode, ledger, meta, flags, no-git, equivalence, skips, empty input (T3), deployment and AGENTS.md correction (T4). Timing, mutation and no-git tests are in T2/T3. Post-release evaluation is out of the plan, as in the spec.
- **Placeholders:** none; the one deliberate stub (T1's `NotImplementedError` after validation) is removed in T3.
- **Type consistency:** `InputError`, `load_input`, `validate_input`, `split_lines`, `synthesize_file_diff`, `build_input`, `set_input_images`, `resolve_input`, `_INPUT_IMAGES` and the constants are named identically in every task; `build_input` returns the keys `diff`, `head`, `repo`, `skipped`, `images`, `n_autojunk`.
