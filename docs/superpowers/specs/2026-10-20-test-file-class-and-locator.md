# Test-file reflex class and a locator on surfaced findings

Status: design approved in chat 2026-10-20; implementation follows the plan
(`docs/superpowers/plans/2026-10-20-test-file-class-and-locator.md`). Effect
UNMEASURED beyond the five field firings below.

## Scope

In: a deterministic, path-based `reflex_class` (`test` or `code`) stamped on
every judged unit; holding the `test` class out of the surfaced findings by
default (still judged, logged and counted); `--include-test-findings` to
restore the old behaviour for measurement; a `where` locator on every
surfaced finding. Out: see the end of this document.

## Problem

Field data (issue #26, comment of 2026-10-20): SOR v0.10.0 over 60 real PR
commits fired 5 times at the 0.80 gate and 1 was true (1.5 counting one
arguable case). All three test-file firings were false or arguable; the two
product-code firings were one true and one false. The earlier Stage A run
produced the same shape: its one false positive,
`tests/unit/custody-stack.test.ts:83-122`, was a test file. Two independent
datasets, two different machines, same class producing the false positives.

| Firing | File | Verdict |
|---|---|---|
| curated-thoughts-integrations#37 | `integrations/deepseek/src/index.ts` | TRUE |
| clanker#812 | `__tests__/drawerTermsGate.test.tsx` | arguable |
| clanker#812 | `__tests__/acceptTermsScreen.test.tsx` | FALSE |
| SynapseTree#55 | `tests/unit/memory-transfer.test.ts` | FALSE |
| curated-thoughts-integrations#80 | `packages/ct-wisdom-core/src/spawn.ts` | FALSE |

INTENT rule 4 says a class whose findings adjudication routinely rejects is
turned off or re-prepared, not tolerated. Rule 5 says SOR's target classes are
the ones a reflex is reliable on; "does this test assert what its name claims"
is a reasoning question, so a new test-specific question is the wrong repair.
ROADMAP S3 already plans a deterministic "test-only" classifier; this change
is its first, narrow slice.

A second observation from the same data: even the true firing needed a reader
to locate the problem inside a 63-line unit. The judge answers only three
questions per unit (severity, is-real, category), so SOR has no statement of
what is wrong to attach and, per INTENT, must not produce prose. It can say
where to look.

## Decision

1. Classify units by path, judge and log all of them, and hold the `test`
   class out of what is surfaced.
2. Add a locator-only pointer to surfaced findings. No claim, no source text.

Both follow INTENT "How changes are made" item 4: they ship behind an off
switch, stamped, with what is unmeasured stated here.

## Design

### Classification

`reflex_class(path)` returns `"test"` or `"code"` from the path alone. `test`
when either holds, matched case-insensitively on `/`-normalised paths:

- a directory segment exactly equal to `tests`, `test`, `__tests__`,
  `__mocks__`, `spec`, `specs` or `e2e`; or
- a filename matching `*.test.*`, `*.spec.*`, `test_*.*`, `*_test.*` or equal
  to `conftest.py`.

Not matched, deliberately: `testing`, `test-utils`, `testutils`, `fixtures`
(often product or infrastructure code). `_test.*` generalises past `.py` so
Go (`foo_test.go`) and `foo_test.ts` classify the same way. Changing the list
is a code change with its own test table, not configuration.

### Stamp and surfacing

- `main()` stamps `reflex_class` on each finding built from a judged unit, and
  on the ledger `judged` entry. Entries without the key (older ledgers) are
  `code`, so historical replays are unchanged.
- `compose(findings, skipped, pr_level, threshold, deletion_threshold,
  hold_classes=("test",))` leaves a finding out of `reported` when its
  `reflex_class` is in `hold_classes`. It is the single place that decides
  what is surfaced, so every caller (`main`, `scripts/enrichment_ab.py`
  `surfaced()`, `scripts/sweep-thresholds.py` `replay()` and
  `scripts/score_corpus.py` `replay_indices()` through `rewrap()`) stays
  consistent. `rewrap()` passes `reflex_class` through when present.
- `--include-test-findings` passes `hold_classes=()` so `compose` surfaces
  everything, as in v0.10.0. Measurement runs and the Stage A golden need it:
  the golden has a real defect at `tests/unit/custody-stack.test.ts:200`,
  which by default can no longer score as found. The A/B harness takes the
  same flag and passes it to both arms.
- The 5-finding cap and the ranking apply after the hold, so a held test
  finding never displaces a code finding.
- Held findings are not silent: `meta.n_test_held` and one report line
  ("N test-file finding(s) held back; --include-test-findings shows them").
  Coverage status is unchanged, because those units were judged. Jitter
  accounting is unchanged.
- Cost: no extra model calls. Held units are still judged, which is what keeps
  the per-class sustained rate measurable.

### Locator

Each surfaced finding gains `where = {"symbol": <chain or null>, "line": <anchor>}`.

- `symbol` is the dotted enclosing chain at the anchor line (for example
  `liveMemoBlockFor`), `null` when none resolves. `line` is the finding's
  existing anchor (`hunk.line`).
- It is computed after `compose()` for the (at most 5) surfaced findings, from
  the file image, not read from `ast_context`. The pointer therefore does not
  depend on enrichment: `--no-enrichment`, missing wheels or a context dropped
  at re-expansion step 0 do not change it, which keeps the A/B off-arm output
  comparable. Python uses `_enclosing_chain`; TS/JS uses the tree-sitter walk
  (`_ts_parse` / `_ts_enclosing_span`); other languages and any failure give
  `null`. Deletion-only units use the pre-image, like enrichment.
- It adds no source text and no claim. It is printed in the report, and
  carried in `--json`, `--out` and the ledger (names and a line number only;
  the ledger still never receives finding source lines).
- Fails open: any error resolving a symbol yields `null`, never an exception.

### Interfaces that change

All additive: new `reflex_class` on judged entries and findings, new
`where` and `meta.n_test_held`, new `--include-test-findings` flag. The
surfaced set shrinks by design. `record_version` and `packaging_version` stay
`v09`: the stamp separates the populations, and replays treat a missing stamp
as `code`.

## INTENT alignment

- Rule 1: no added model calls; the locator parses at most five files.
- Rule 2: classification and location are deterministic code; the model still
  only judges.
- Rule 3: no verdict output is introduced.
- Rule 4: a class with a bad measured rate stops surfacing; it is not
  tolerated. The sustained rate is still tracked per class, so it can earn its
  way back (rule 6b: at least 0.70 over at least 10 adjudicated firings).
- Rule 5: no reasoning question is added for tests.
- Out of scope (INTENT): narrative review. The locator makes no claim about
  what is wrong.

## Validation

Pre-release smoke tests (CI, model-off):

1. A table test of `reflex_class` including the five field paths (three
   `test`, two `code`), `testing/` and `test-utils/` as `code`, Windows
   separators, upper case, `foo_test.go`, `conftest.py`.
2. `compose` holds `test` findings by default, surfaces them with
   `hold_classes=()`, treats a finding with no `reflex_class` as `code`, and
   applies the 5-cap after the hold.
3. `main()` end to end: a test-file unit above the gate is judged, ledgered
   with `reflex_class: "test"` and `reported: false`, absent from `findings`,
   counted in `meta.n_test_held`; `--include-test-findings` restores it.
4. Replay paths: `rewrap` passes the stamp through; the sweep, the corpus
   scorer and the A/B `surfaced()` agree with `main` on the same ledger entry.
5. The locator: TS, TSX, JS and Python symbols, an unresolved line, a
   deletion-only unit (pre-image), a file with a parse error, no wheels, and
   that the output is identical with and without `--no-enrichment`.
6. Mutation checks on every new test, as in the earlier PRs.

Post-release evaluation (does not block the release):

- Track the sustained rate separately for `code` and `test` (issue #26, S0),
  starting from the five firings above: after this change, the replayed field
  data surfaces 2 findings (1 TRUE, 1 FALSE).
- Keep `test` judged-and-held until it shows at least 0.70 over at least 10
  adjudicated firings (adjudicate held findings with `--include-test-findings`
  runs); only then consider surfacing it, as its own labelled class.
- Watch the volume note from the field data: 5 firings in 60 commits means
  per-class evidence accrues slowly, so use the full judged list (issue #24)
  for score-level comparisons.

## Known limits

- Path heuristics: a test helper outside the listed directories or names is
  `code`; a product file that happens to live under `test/` is held. Both are
  visible in the ledger by class.
- The Stage A golden row `custody-stack.test.ts:200` is unscored by default.
  Use `--include-test-findings` for golden runs.
- The locator names a place, not a problem. A unit with no resolvable symbol
  (module level, wrapped callbacks such as `memo(...)`) gets `symbol: null`.

## Open questions (resolved)

- No `held` list in `--json`. The count goes in `meta.n_test_held` only. Hosts
  that need held findings (the aws-cloud-agent shadow) read the ledger; add a
  list on request.
- The class list lives in ROADMAP S3, not INTENT. INTENT states the rule; the
  ROADMAP carries the classes as they ship.

## Out of scope

Surfacing test findings as their own labelled class; a test-specific
question for the judge; the S0 sustained-rate ledger and stats command (#26);
`--input` mode (#23); full judged list in `--json` (#24); the ledger write
crash on a read-only HOME (#25); other S3 classes (docs-only, lockfile,
generated, rename-only, whitespace-only).
