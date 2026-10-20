# `--input`: review before/after file images without git

Status: design approved in chat 2026-10-20 (approach A, contract confirmed by
the aws-cloud-agent). Implementation follows
`docs/superpowers/plans/2026-10-20-input-mode.md`. Closes issue #23.

## Scope

In: a new `--input FILE|-` mode that takes the changed files' before and after
texts as JSON, synthesizes a git-style unified diff in memory, and feeds the
existing pipeline (triage, packaging, cutting, enrichment, judging, the
test-file hold, the locator) with no git and no filesystem. Out: see the end.

## Problem

Every caller needs git and a local repo today: `--repo` is required and the
only modes are `--range`, `--pr`, `--staged` and `--uncommitted`. The
aws-cloud-agent Reviewer is an AWS Lambda that reads PRs through the GitHub
API; it has no git and no checkout, so SOR cannot run there. It is waiting on
this mode before building a log-only shadow (issue #26's integration trigger
depends on that shadow's data). A host that holds the images would otherwise
have to synthesize a two-commit temporary repo.

Git touches the pipeline at only three edges, which is why a bounded change is
possible:

1. `resolve_diff(repo, args)` runs `git diff` / `rev-parse` and returns
   `(diff_text, head, mode)`.
2. `mode_file_images(repo, mode, head, path, old_file=...)` runs `git show` /
   `merge-base`; its callers are the cutters (via the `images` lambda), the
   runtime splitter, enrichment and the locator.
3. `meta.repo` is `basename(realpath(args.repo))`.

Everything downstream is plain text.

## Decision

Approach A: an in-memory source. `--input` is parsed and validated up front;
a git-shaped diff is synthesized per file with `difflib`; the before/after
texts are registered in a module-level map; `mode_file_images` gains a mode
`input` that answers from the map. No downstream caller changes. Rejected:
building a temporary git repo (needs git on the host, which is the problem),
and a new pipeline entry that bypasses diff text (touches the packager and
every cutter).

## Design

### Contract

```json
{
  "head":  "<sha or label>",
  "repo":  "<name>",
  "files": [
    {"path": "src/a.ts", "old_path": null, "before": "...", "after": "..."}
  ]
}
```

- `head` (required): non-empty string, at most 200 characters; recorded as the
  run's head.
- `repo` (optional): label for `meta.repo`; default `"input"`.
- `files` (required): array; each entry has `path` (required string),
  `old_path` (optional string or null), `before` and `after` (string or
  null). Status is derived from the contents, never stated: `before: null` is
  an added file, `after: null` is a deleted file, `old_path` set and different
  from `path` is a rename (with or without edits). `before == after` (and no
  rename) is ignored. Both null is invalid.
- Unknown top-level or file keys are ignored (forward compatible).

### Validation (before any model call; exit code 2, message on stderr)

- Not JSON, not an object, `files` not an array, wrong types, missing or empty
  `head` or `path`.
- `path` / `old_path` containing a NUL or any control character (including
  `\n` and `\r`): a newline in a path would inject lines into the synthesized
  diff header. Paths are labels (there is no filesystem access), so absolute
  paths and `..` segments are allowed but backslashes are normalised to `/`.
- Duplicate `path`.
- Total input over 64 MiB, or more than 2,000 files.
- `--input` together with `--repo`, `--range`, `--pr`, `--staged` or
  `--uncommitted`; neither `--input` nor `--repo` given. (`--repo` is required
  only when `--input` is absent.)

### Per-file triage (the run continues; the file is skipped, listed in
`skipped` with a reason, like other deterministic skips)

- `input-binary`: a NUL character in `before` or `after`.
- `input-oversize`: more than 2 MiB of text or 20,000 lines on either side
  (difflib is quadratic in the worst case; a single generated file must not
  fail or stall the run).
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

- Lines are split on `"\n"` only, never `str.splitlines()` (which also splits
  on U+2028, form feed and friends and would shift every line number after
  them); a trailing `\r` stays part of the line, as in git.
- Hunks come from `difflib.SequenceMatcher(None, a, b, autojunk=False)
  .get_grouped_opcodes(3)` formatted by this module. The stock
  `difflib.unified_diff` is not used because it builds its matcher with
  `autojunk=True`, which treats frequent lines in files of 200 or more lines
  as junk and produces poor diffs. Three lines of context matches git's
  default. The `@@` header omits `,1` counts and uses `,0` for empty sides,
  as git does.
- Equivalence with `git diff` is guaranteed for the set of changed lines when
  the minimal diff is unique; where several minimal diffs exist, difflib and
  git's Myers algorithm may pick different ones, so hunk boundaries and
  anchors can differ. This is a known limit, covered in Validation.

### Images

`mode_file_images(repo, mode, head, path, old_file=None, ...)` with
`mode == "input"` returns `(before, after)` for `path` from the module-level
map (`None` for a null side) and ignores `repo`. The map is set once per run
and cleared with the other runtime caches (`clear_runtime_caches`). Renames
need no `old_file` lookup because the before text is carried directly.

### Mode, head, ledger and output

- `resolve_input(doc)` returns `(diff, head, "input")`; `main()` calls it
  instead of `resolve_diff` when `--input` is given. `args.repo` is `None` and
  nothing dereferences it in input mode.
- `meta.mode` and the ledger `mode` are `"input"`; `meta.repo` is the input's
  `repo` label (default `"input"`); the default ledger label is `auto:input`.
- The input's contents are never stored: the ledger still never receives
  finding source lines, and nothing in the input is persisted beyond what the
  existing record already holds (file paths, scores, spans).
- Output (`--json`, `--out`, stdout report) is unchanged in shape.

### What does not change

The judge and its three questions, scoring, the 0.80 gate, the test-file hold,
the locator, the 5-cap, the cutters, enrichment, and the stamps. A reviewer
should see the same units and findings from `--input` as from `--range` on the
same change, apart from `mode`, `head` and the diff-algorithm limit above.

### Deployment notes for hosts (the Lambda)

- **API key:** `TYPESAFE_API_KEY` in the environment, as today.
- **Ledger:** HOME is read-only on Lambda, so a ledger write fails after the
  model calls are paid for (issue #25, a separate follow-up). Until it lands,
  set `JEV_REVIEW_METRICS=/tmp/...`.
- **tree-sitter wheels are optional and absence is silent.** Verified in the
  code: `check_cutter_availability()` returns `(False, None)` and the tool
  falls back to line windows; it never aborts on missing wheels, in any mode
  including `--golden`. (The aborts that exist are in
  `scripts/enrichment_ab.py` and `scripts/enrichment_census.py`, which are
  measurement scripts, not the tool. The AGENTS.md sentence that says
  measurement runs abort is corrected in this change.) Without the wheels the
  host gets line-window cutting for TS/JS, no TS enrichment, and
  `where.symbol: null` for TS/JS findings. Python files use stdlib `ast` and
  are unaffected. The degradation is visible in `meta.wheels`
  (`{ts: {available: false}, ...}`); a host that cares should check it, or
  package the pinned wheels (`tree-sitter==0.26.0`,
  `tree-sitter-typescript==0.23.2`, `tree-sitter-javascript==0.25.0`) into a
  layer built for the Lambda's architecture.

## INTENT alignment

- Rule 1: no added model calls; synthesis is in-memory and capped.
- Rule 2: input handling, diff synthesis and triage are deterministic code.
- Rule 3 and 4: no verdict output; the hold and the 0.80 gate are untouched.
- Rule 5/6: no new question or stimulus for the judge.
- Out of scope in INTENT: SOR posts nothing; this mode reads JSON and prints a
  report, delivery stays the caller's job.

## Validation

Pre-release smoke tests (CI, model-off):

1. Synthesized diff versus real `git diff` on throwaway repos: add, delete,
   modify, rename (with and without edits), empty file, file without a
   trailing newline, CRLF content, a file over 200 lines with repeated lines
   (the `autojunk` case), U+2028 and form feed inside a line. Exact text
   equality where the minimal diff is unique; for ambiguous cases, equality of
   the changed-line set and of the packager's clusters.
2. End to end: `--input` and `--range` over the same change, with a stub
   judge, give the same units, anchors, spans and rendered report apart from
   `mode`/`head`; the test-file hold, the locator and enrichment engage under
   `--input`.
3. Validation matrix: every rejection above exits 2 with the documented
   message and makes no model call (the provider is stubbed to fail the test
   if called).
4. `--input -` reads stdin; `--input FILE` reads a file; the `--repo`
   conflicts.
5. Per-file triage: binary and oversize files are listed in `skipped` and the
   run still reviews the rest.
6. No git needed: the tests for 2 and 5 run with `git` absent from `PATH`
   (the pipeline must not shell out in input mode).
7. Mutation checks on every new test, as in the earlier PRs.

Post-release evaluation (does not block the release): the aws-cloud-agent
shadow records `meta.mode == "input"` runs log-only and its adjudications feed
issue #26's per-class sustained rate. No new gate is introduced here.

## Known limits

- difflib versus git's diff algorithm: ambiguous diffs can differ in hunk
  boundaries; anchors are comparable within a mode, not guaranteed identical
  across modes.
- No rename detection: the host supplies `old_path`.
- Binary and very large files are skipped, not partially reviewed.
- The host must supply full file texts; a fetch failure on one side should be
  omitted from `files`, not sent as an empty string (an empty `before` reads
  as "the file was emptied", and an empty `after` as "emptied", not deleted).

## Open questions

- Should `review_input(doc)` also be importable as a function for Python
  hosts? Not needed for the Lambda today; add on request.
- Should the size caps become flags? Constants for now.

## Out of scope

Git-backed modes (unchanged); `--pr` for hosts; the ledger write crash on a
read-only HOME (#25, separate); full judged list in `--json` (#24); the S0
sustained-rate ledger (#26); packaging the wheels into a Lambda layer (host
side).
