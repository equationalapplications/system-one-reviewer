# `--input`: review before/after file images without git

Status: design approved in chat 2026-10-20 (approach A, contract confirmed by
the aws-cloud-agent), revised after a Fable review of this spec. Plan:
`docs/superpowers/plans/2026-10-20-input-mode.md`. Closes issue #23.

## Scope

In: a new `--input FILE|-` mode that takes the changed files' before and after
texts as JSON, synthesizes a git-style unified diff in memory, and feeds the
existing pipeline (triage, packaging, cutting, enrichment, judging, the
test-file hold, the locator) with no git and no subprocess. Out: see the end.

## Problem

Every caller needs git and a local repo today: `--repo` is required and the
only modes are `--range`, `--pr`, `--staged` and `--uncommitted`. The
aws-cloud-agent Reviewer is an AWS Lambda that reads PRs through the GitHub
API; it has no git and no checkout, so SOR cannot run there. It is waiting on
this mode before building a log-only shadow (issue #26's integration trigger
depends on that shadow's data). A host that holds the images would otherwise
have to synthesize a two-commit temporary repo.

Git touches the pipeline at only three edges (verified against the code by
the review: every other use of `repo` and every `subprocess` call routes
through them), which is why a bounded change is possible:

1. `resolve_diff(repo, args)` runs `git diff` / `rev-parse` and returns
   `(diff_text, head, mode)`.
2. `mode_file_images(repo, mode, head, path, old_file=...)` runs `git show` /
   `merge-base`; its callers are the cutters (via the `images` lambda), the
   runtime splitter, enrichment and the locator.
3. `meta.repo` is `basename(realpath(args.repo))`.

Everything downstream is plain text.

## Decision

Approach A: an in-memory source. `--input` is parsed and validated up front;
a git-shaped diff is synthesized per file; the before/after texts are
registered in a module-level map; `mode_file_images` gains a mode `input` that
answers from the map. No downstream caller changes. Rejected: building a
temporary git repo (needs git on the host, which is the problem), and a new
pipeline entry that bypasses diff text (touches the packager and every
cutter).

## Design

### Contract

```json
{
  "head":  "<40-hex commit SHA>",
  "repo":  "<name>",
  "files": [
    {"path": "src/a.ts", "old_path": null, "before": "...", "after": "..."}
  ]
}
```

- `head` (required): non-empty string, at most 200 characters, recorded as
  the run's head. It MUST be the 40-hex head commit when the host has it: the
  field sweeps map runs to PRs through the recorded head (`fixture_head`), so
  a free label breaks run-to-PR mapping.
- `repo` (optional): label for `meta.repo`; a string of at most 200
  characters with no control characters; default `"input"`.
- `files` (required): array; each entry has `path` (required string),
  `old_path` (optional string or null), `before` and `after` (string or
  null). Status is derived from the contents, never stated: `before: null` is
  an added file, `after: null` is a deleted file, `old_path` set and different
  from `path` is a rename (with or without edits). `before == after` with no
  rename is ignored. Both null is invalid. An empty string is a real empty
  file: a host that failed to fetch one side must omit the file, not send `""`.
- Unknown top-level or file keys are ignored (forward compatible). An empty
  `files` array is valid: an empty diff, the report says "Empty diff — nothing
  to review", and the ledger record is still appended.

### Reading and validating (all before `load_api_key()` and any model call)

- Input is read from the file or stdin with a hard cap of 64 MiB (read at most
  64 MiB + 1 byte and reject). A leading BOM is stripped (UTF-8 with BOM).
  JSON is parsed with `parse_constant` rejecting `NaN`/`Infinity`;
  `RecursionError` (deep nesting) and any decode error are reported as "not
  JSON".
- Reject: top level not an object, `files` not an array, wrong types, missing
  or empty `head`/`path`, duplicate `path` (after backslash normalisation),
  more than 2,000 files, more than 1,000,000 lines in total across all files
  and both sides (memory: 64 MiB of newlines is 67 million line objects).
- `path`, `old_path`, `head` and `repo` may not contain any character that
  `str.splitlines()` treats as a line boundary: the control rule below plus
  U+0085, U+2028 and U+2029. The packager splits the diff with `splitlines()`,
  so such a character in a path forges a `+++` header (reproduced in review:
  a source file's findings were routed to a test path and held back). The
  same applies to file CONTENT, closed at the root in the packager (see Known
  limits); this rule is defense in depth. Paths
  are limited to 1,024 characters (`INPUT_MAX_PATH_CHARS`).
- `old_path` is kept only for a real rename (both sides non-null and different
  from `path`); for an added or deleted file it is normalised to null (the
  packager would otherwise name the hunk after `old_path` while the images are
  keyed by `path`). A `head` that is not a 40-hex SHA is accepted as a label
  and a warning is printed on stderr.
- `head`, `repo`, `path`, `old_path`, `before` and `after` must round-trip
  `.encode("utf-8")`: `json.loads` accepts lone surrogates (`"\ud800"`), which
  later raise `UnicodeEncodeError` in `print(render(...))` after the model
  calls are paid for.
- `path` / `old_path`: no control characters, defined as `ord(c) < 0x20` or
  `ord(c) == 0x7F` (a newline would inject diff lines, a TAB truncates the
  packager's path parse); not `/dev/null` (the packager reads it as an
  addition or deletion); backslashes are normalised to `/`. Paths are labels
  (there is no read of the reviewed code), so absolute paths and `..` segments
  are allowed.
- `--input` together with `--repo`, `--range`, `--pr`, `--staged` or
  `--uncommitted`, or neither `--input` nor `--repo`, is an argument error via
  `ap.error()` (exit 2, usage format). `--repo` is required only when `--input`
  is absent.
- Document rejections print
  `system-one-reviewer: --input: <reason> (files[<i>].<key>)` to stderr and
  exit 2 (the existing `sys.exit("...")` calls exit 1; input rejection is a
  caller error and is distinguished). Paths are echoed only through `repr()`
  truncated to 120 characters, and file contents never.

### Per-file triage (the run continues; the file is skipped)

Skip records have the shape the renderer and coverage code already read:
`{"file": <path>, "reason": <reason>, "line_start": 1, "line_end": 1}`.

- Path triage first, by `triage()`'s own predicates (lockfiles, docs,
  generated, data/snapshot), with its reason strings, however large the file:
  these are deliberate triage and never unjudged code.
- `input-binary`: a NUL character in `before` or `after`. Deliberate triage,
  like a lockfile.
- `hunk>input-oversize`: more than 2 MiB of text, 20,000 raw lines, or any
  single line over 100,000 characters (`INPUT_MAX_LINE_CHARS`; minified code
  makes tree-sitter parse the file several times) on either side. An oversize
  DELETION is `whole-file-deleted>cap` with `change_type: "whole-file-deleted"`,
  as in the git modes, so it stays triage. The `hunk>` prefix is deliberate: coverage code counts only skip
  reasons with that prefix as unjudged code (`size_skipped_code`,
  `n_size_skipped_code`), so an oversize CODE file makes the run read
  "incomplete review" and never "ok" (INTENT rule 7).
- Existing triage still applies by path afterwards (lockfiles, generated
  directories, docs-only).

### Diff synthesis

For each remaining file a git-shaped block is emitted, in input order:

```
diff --git a/<old_or_path> b/<path>
[new file mode 100644 | deleted file mode 100644 | rename from <old> / rename to <path>]
--- a/<old_or_path>    (or /dev/null for an added file)
+++ b/<path>           (or /dev/null for a deleted file)
@@ -a,b +c,d @@
 context / -removed / +added
\ No newline at end of file     (when a side lacks a final newline)
```

What the packager actually requires: only the `--- ` / `+++ ` lines and the
`@@` headers matter. `new file mode`, `deleted file mode`, `rename from/to`
and `similarity index` are ignored, and `index` lines are not emitted. The `@@`
counts must be exact, because the packager's remaining-line counters decide
when a `--- ` line is a header again. An added or deleted EMPTY file, and a
pure rename, emit headers only and yield no cluster.

- **Line model.** A side's text is split so that each element keeps its
  terminator: `parts = text.split("\n"); last = parts.pop(); lines = [p +
  "\n" for p in parts]; if last: lines.append(last)`. A final element without
  `"\n"` is the no-newline line. Empty text is `[]` with no marker. This is
  required for a change that only adds or removes the final newline, which git
  shows as `-b` / `\ No newline at end of file` / `+b`; with the terminator
  outside the lines the two sides compare equal and a real change would be
  invisible. The split is on `"\n"` only, never `str.splitlines()`, which also
  splits on U+2028 and form feed. A trailing `\r` stays part of the line.
- **Emission.** `prefix + line` for each line; when `line` lacks `"\n"`, the
  marker `\ No newline at end of file` follows immediately, once per side,
  after that side's last `-`, `+` or context line, as git does.
- **Matching.** Common leading and trailing lines are stripped first (git does
  this; difflib does not). If both cores are at most `INPUT_MATCH_LINES` (400)
  lines and the per-run `INPUT_MATCH_BUDGET` (400,000, summed `len(core_a) *
  len(core_b)`) is not spent, the core is matched with
  `difflib.SequenceMatcher(None, a, b, autojunk=False)`, grouped with 3 lines
  of context. Otherwise a bounded fallback is used and the file is counted in
  `meta.n_input_autojunk`: the core is split at lines unique to both sides
  (keeping the longest increasing chain of such anchors), common ends are
  stripped in each stretch, a stretch within the size limits is matched with
  `SequenceMatcher(autojunk=True)`, and any other stretch becomes one coarse
  replace, delete or insert. Why: `autojunk=False` is cubic-ish (alternating
  blank lines took 1.4 s at 500 lines, 93 s at 2,000), and `autojunk=True` is
  NOT bounded either (3,000 to 20,000 lines with lines repeated 300 to 10,000
  times took 25 s to 301 s). The fallback's measured worst cases are under
  0.2 s per file, and the budget keeps a 2,000-file document of the worst
  exact-matching shape near 2 s. The stock `difflib.unified_diff` is not used.
  Three lines of context matches git's default; the `@@` header omits `,1`
  counts and uses `,0` for empty sides as git does.
- Equivalence with `git diff` holds for the set of changed lines when the
  minimal diff is unique; where several minimal diffs exist difflib and git's
  Myers algorithm may pick different ones.

### Images

`mode_file_images(repo, mode, head, path, old_file=None, ...)` with
`mode == "input"` returns `(before, after)` for `path` from a module-level map
(`None` for a null side) and ignores `repo`. It does not use `_IMAGE_CACHE`.
The map is a module global set once per run and cleared by
`clear_runtime_caches()`, so two input documents in one process cannot collide.
A rename needs no `old_file` lookup because the before text is carried.

### Mode, head, ledger and output

- `resolve_input(doc)` returns `(diff, head, "input")`; `main()` calls it
  instead of `resolve_diff` when `--input` is given. `args.repo` is `None` and
  nothing dereferences it in input mode.
- `meta.mode` and the ledger `mode` are `"input"`; `meta.repo` is the input's
  `repo` label; the default ledger label is `auto:input`.
- The input's contents are never stored: the ledger still never receives
  finding source lines.
- `--max-hunks`, `--golden`, `--negative-golden`, `--label`, `--fixture`,
  `--out`, `--json` and `--include-test-findings` work unchanged.
- Output shape is unchanged, plus `meta.n_input_autojunk` (0 when none).

### What does not change

The judge and its three questions, scoring, the 0.80 gate, the test-file hold,
the locator, the 5-cap, the cutters, enrichment, and the stamps. A reviewer
should see the same units and findings from `--input` as from `--range` on the
same change, apart from `mode`, `head`, the diff-algorithm limit above, and
renames (below).

### Deployment notes for hosts (the Lambda)

- **API key:** `TYPESAFE_API_KEY` in the environment, as today.
- **Ledger:** `log_run` runs BEFORE the report is printed and `--out` is
  written, and its `os.makedirs` on a read-only HOME raises uncaught. Without
  `JEV_REVIEW_METRICS` pointing at a writable path (for example
  `/tmp/metrics.jsonl`) the run crashes after the model calls are paid for and
  prints nothing at all. Issue #25 (a separate follow-up) will make the write
  non-fatal; until then this variable is required on Lambda.
- **tree-sitter wheels are optional and absence is silent.** Verified in the
  code: `check_cutter_availability()` returns `(False, None)` and the tool
  falls back to line windows; it never aborts on missing wheels, in any mode
  including `--golden`. The aborts that exist are in `scripts/enrichment_ab.py`
  and `scripts/enrichment_census.py`, which are measurement scripts, not the
  tool; the AGENTS.md sentence saying measurement runs abort is corrected in
  this change. Without the wheels the host gets line-window cutting for TS/JS,
  no TS enrichment, and `where.symbol: null` for TS/JS findings. Python files
  use stdlib `ast` and are unaffected. The degradation is visible in
  `meta.wheels` (`{ts: {available: false}, ...}`); a host that cares should
  check it, or package the pinned wheels (`tree-sitter==0.26.0`,
  `tree-sitter-typescript==0.23.2`, `tree-sitter-javascript==0.25.0`) into a
  layer built for the Lambda's architecture.
- Other environment facts (read, not run on Lambda): TLS uses the system CA
  store (`ssl.create_default_context()`); the HTTP timeout is 15 s with two
  attempts, then the run fails open; no tempfile, signal or multiprocessing is
  used; a failed `__pycache__` write is silent.

## INTENT alignment

- Rule 1: no added model calls; synthesis is in-memory, with caps chosen so a
  run stays in the seconds envelope.
- Rule 2: input handling, diff synthesis and triage are deterministic code.
- Rule 3 and 4: no verdict output; the hold and the 0.80 gate are untouched.
- Rule 5/6: no new question or stimulus for the judge.
- Rule 7: an oversize code file reads as an incomplete review, not "ok".
- Out of scope in INTENT: SOR posts nothing; this mode reads JSON and prints a
  report, delivery stays the caller's job.

## Validation

Pre-release smoke tests (CI, model-off):

1. Synthesized diff versus real `git diff` on throwaway repos: add, delete,
   modify, empty file, file without a trailing newline, a change that ONLY adds
   or removes the final newline, CRLF content, a file over 200 lines with
   repeated lines (the autojunk case), U+2028 and form feed inside a line.
   Comparison normalises what git adds and difflib does not: `index` lines and
   anything after the second `@@` (git appends a function-name context). Exact
   text equality where the minimal diff is unique; for ambiguous cases,
   equality of the changed-line set and of the packager's clusters.
2. End to end: `--input` and `--range` over the same change, with a stub
   judge, give the same units, anchors, spans and rendered report apart from
   `mode`/`head`/`repo`; the test-file hold, the locator and enrichment engage
   under `--input`. Renames are excluded from the equivalence test (below).
3. Validation matrix: every rejection above exits 2 with the documented
   message and makes no model call (the provider and `load_api_key` are stubbed
   to fail the test if called): not JSON, BOM accepted, NaN, deep nesting, lone
   surrogate, control characters in a path, `/dev/null`, duplicate path, caps,
   wrong types, flag conflicts.
4. `--input -` reads stdin; `--input FILE` reads a file.
5. Per-file triage: binary and oversize files appear in `skipped` with the
   documented shape; an oversize CODE file yields `status == "incomplete
   review"`; the rest of the input is still reviewed; an empty `files` array
   reports an empty diff.
6. No git needed: tests 2 and 5 run with `git` absent from `PATH`; nothing in
   input mode may shell out.
7. Timing: a 20,000-line all-blank file with one change is diffed in
   milliseconds; the alternating-blank worst case at the exact-matching limit
   (400 lines) is fast and a 40-file document of that shape stays inside the
   budget time; every adversarial shape measured in review (3 to 10,000
   distinct repeated values, 20,000 lines) finishes in under 0.2 s per file.
   A seeded round trip (2,000 cases in each of the exact, anchored and
   budget-spent modes) proves the synthesized hunks reproduce the after-text.
8. Mutation checks on every new test, as in the earlier PRs.

Post-release evaluation (does not block the release): the aws-cloud-agent
shadow records `meta.mode == "input"` runs log-only and its adjudications feed
issue #26's per-class sustained rate. No new gate is introduced here.

## Known limits

- difflib versus git's diff algorithm: ambiguous diffs can differ in hunk
  boundaries; anchors are comparable within a mode, not guaranteed identical
  across modes. Cores above 400 lines, and every file once the budget is
  spent, use the bounded fallback: always correct, sometimes coarser (a region
  with no unique lines becomes one replace). The budget is spent first-come.
  On 39 realistic large-file edits (300 to 3,000 lines) the output equalled
  `git diff` exactly.
- When every changed file is skipped the report says `Nothing to review: all N
  changed file(s) were skipped (see below).` (this banner applies in every
  mode); a PR whose only files are binary reads `status ok`, as in git mode.
- No rename detection: the host supplies `old_path`. `--input` enriches renamed
  files better than `--range`: `package_hunks` never emits `old_file`, so in the
  git modes a rename's pre-image is `None` today, while input mode carries
  `before`.
- Binary and very large files are skipped, not partially reviewed.
- Diff parsing and file content (fixed in this change, all modes): the
  packager used to split the diff with `str.splitlines()`, and the git modes
  read git's output with universal newlines. File CONTENT is attacker-
  controlled, so a changed line containing a lone CR, U+2028, U+2029, U+0085,
  VT, FF or FS/GS/RS followed by a forged `diff --git` / `---` / `+++` / `@@`
  block made the packager attribute the following lines to another file (for
  example a test path, where `reflex_class` then held the findings back).
  This affected the released git modes as well as `--input`. The packager now
  splits the diff on `"\n"` only (stripping a trailing `\r`, so CRLF diffs are
  unchanged), `run_git` reads bytes and decodes them without newline
  translation, and file images already used the same line model. The
  path/label line-boundary rejection above remains as defense in depth.
- The host must supply full file texts; see the contract on empty strings.

## Open questions

- Should `review_input(doc)` also be importable as a function for Python
  hosts? Not needed for the Lambda today; add on request.
- Should the size caps become flags? Constants for now.

## Out of scope

Git-backed modes (unchanged); `--pr` for hosts; the ledger write crash on a
read-only HOME (#25, separate); full judged list in `--json` (#24); the S0
sustained-rate ledger (#26); packaging the wheels into a Lambda layer (host
side).
