# Opus review dispositions — main..v02-evaluation (2026-09-27)

Dispositions for every finding of the Opus code review of
`main..v02-evaluation` (1 BLOCKER, 4 MAJOR, 8 MINOR). Every disposition
below is literally true at the time of writing: FIXED means the fix is
committed on `v02-evaluation` with the commit noted; REJECTED means the
finding was verified but deliberately not acted on, with the reason.

## BLOCKER

**B1 — Published benchmark explains the two misses wrongly (packaging
artifact, not model scores): FIXED** (commits 136c928, 5e02af5, 0598a68,
e6a5d41).
Verified against the committed v02-final metrics first: every positive
run's `judged` array had exactly 4 entries (17, 11, 14, 4) — plants at
golden 19/22 were never separately judged — and on the old fixture plants
4+5 formed one contiguous changed run anchored at 17. Fixed on both sides:
- fixture: plants separated by unchanged lines (a `clip` helper between
  render and the duplicate import); the new positive fixture
  (ea5df10e1624b095fecd657b12ee23b46e808386) packages into 5 distinct
  clusters (anchors 4, 11, 14, 17, 24);
- packaging: M1's window isolation (same commit set) stops neighbouring
  clusters' changed entries from diluting a cluster's context;
- re-run: 6 fresh `v02-r2-*` live runs; benchmark doc + README rewritten
  (TP 4/5, raw precision 4/5, F1 0.80; the doc supersedes v02-final and
  says why).

## MAJOR

**M1 — E2 window isolation not implemented: FIXED** (commit 5e02af5).
`package_hunks` now expands each cluster's window outward over context
lines only, within ±CTX and the hunk bounds, stopping at any neighbouring
cluster's +/- entry. Plan-required test added
(`tests/test_package.py::test_cluster_window_excludes_neighbouring_clusters_changed_lines`):
on `tests/data/v01-fixture.diff`, cluster 2 (anchor 14) contains no
non-space entries of cluster 1 or cluster 3, and every cluster's window
holds exactly its own changed entries. The v01 anchor contract
[11, 14, 17, 20, 26] still passes; `tests/data/v01-fixture.diff` unchanged.

**M2 — Sweep does not implement the spec precision/FP formula: FIXED**
(commit e2d8cbb). `scripts/sweep-thresholds.py` now computes
precision_i = TP_i / (TP_i + FP_pos_i + FP_neg_mean), folded into an F1
against recall_i; FP_pos excludes MINOR-style notes (sev_level 1 AND
category style — the same class `eval_negative` exempts); negative-run FPs
enter the curve at every threshold. `tests/test_sweep.py` updated to the
spec formulas (the old `test_candidate_is_argmax...` expectations now hold
under the spec math; `min_f1` key renamed to per-run F1 rows).

**M3 — Negative-fixture build never tested (stale strict xfail): FIXED**
(commit 136c928). `tests/test_fixture_labels.py` no longer xfails: the
negative case parses the builder's real output line
(`negative fixture ready: <root> head=<sha>`), asserts the TSV's real
shape (2 rows, 2 columns), and asserts building twice yields the identical
committed SHA (determinism, plan M5's actual guarantee). Full suite is
xfail-free.

**M4 — README install/usage reference a file that doesn't exist: FIXED**
(commit 15e22ef). Install line is now
`cp system_one_reviewer.py ~/.local/bin/system-one-reviewer`; the example
fixture section builds `/tmp/jev-review-pos` (the builder's real default),
so every usage example invokes an artifact that exists.

## MINOR

**m1 — Deletion-only anchors use old-file line numbers: REJECTED.**
The behavior is deliberate and test-locked
(`tests/test_package.py::test_deletion_anchor_is_not_one`): a deleted
line exists only in the old file, so old-file numbering is the only
address for the deletion site, and at a pure deletion old/new numbering
coincides up to the deletion point, keeping anchors comparable with
HEAD-recorded golden lines. Documented in the `package_hunks` docstring
(commit 5e02af5) instead of changing the contract.

**m2 — fixture SHA gate checks the repo checkout, not the reviewed diff
tip: REJECTED (documented).** `fixture_head` is `git rev-parse HEAD` by
design: the committed fixtures gate runs whose `--range` ends at HEAD, and
`--staged`/`--uncommitted` review HEAD's tree, so the checkout HEAD is the
correct gating value there. Semantics documented in the `resolve_diff`
docstring (commit 15e22ef). A range whose tip is not HEAD would mislabel
— noted as a candidate guard for the v0.3 tuning pass, not fixed here.

**m3 — Rule 2 checks equality instead of "no increase": FIXED**
(commit e2d8cbb). Rule 2 is now `all(c <= b ...)` per run (dFP-neg <= 0),
with a new test proving a candidate that *reduces* negative FPs passes
(`test_candidate_that_reduces_negative_fps_passes_rule_2`).

**m4 — `--packaging-version` and `--negative-golden` ignored: FIXED**
(commit e2d8cbb). `--packaging-version` (default v02) flows through
`main()` -> `select_runs` -> `gate_run`. `--negative-golden` is now used:
its must-skip file column (docs/lockfile-pattern files only, per the
tool's own triage predicates) drives a triage-leakage guard that dies
loudly if a negative run reports a finding there (commit c4451a8).

**m5 — Planted render bug mislabeled (correctness bug labeled
MINOR/perf): FIXED** (commit 136c928). The plant no longer changes
program behavior's substance: render iterates `for item in items` and
renders `str(item)` (label-blind, no PLANT-style comments in generated
content); the planted issue is purely the O(n²) `out +=` accumulation,
which is honestly MINOR/performance. Code and golden classification now
agree.

**m6 — Negative fixture doesn't match spec E1: FIXED** (commit 136c928).
The builder now makes exactly a whitespace-only reformat (4-space to
8-space function-body indent) plus one innocuous comment; the behavioral
`items`->`entries` parameter rename is reverted. README.md change kept
(triage-skipped, asserted by `tests/test_negative.py`). New negative SHA
e7de08b239982e896d9d57981fa07d83aab7cb65 committed to
`examples/fixture-shas.txt`.

**m7 — Three provider tests prove nothing: FIXED** (commit 0d4b81c).
- `test_metrics_carry_provider_and_model` calls the REAL `log_run` and
  asserts on the record it actually wrote (provider/model/label/ts in the
  jsonl), no monkeypatched stub.
- `test_sweep_rejects_mixed_providers_end_to_end` runs the sweep script as
  a subprocess over a mixed-provider metrics file and asserts a non-zero
  exit with a provider error — a real hard error end to end.
- `test_make_provider_laya_uses_router` exercises the lazy-load path:
  `_LAYA_ROUTER` is reset (never pre-seeded), the laya import is faked via
  `builtins.__import__`, and the test proves the router loads through
  `get_laya_router` on first call and is cached for the process.

**m8 — Module docstring shows the old command name: FIXED** (commit
15e22ef). The Usage line now reads `system-one-reviewer --repo <path> ...`.

## Verification

- Full suite: 55 passed, 0 failed, no xfail (`python3 -m pytest tests/ -q`).
- 6 fresh live runs (`v02-r2-baseline-1..3`, `v02-r2-negative-1..3`):
  TP 4/5, raw precision 4/5 (0.80), F1 0.80; negative runs report nothing.
- Sweep: candidate 0.40, rule 1 FAIL, rule 2 PASS -> KEEP 0.50.
- Merge gate: zero blocker_major in every negative run at 0.50 — PASS.
- Numbers: docs/benchmarks/2026-09-27-threshold-sweep.md (+ committed
  metrics jsonl), README.md.

---

# Opus review cycle 2 (r2) — 9 findings, all dispositioned

Review of `main..v02-evaluation` after the r1 fixes (session 0a11272d,
$0.57): 0 BLOCKER, 3 MAJOR, 6 MINOR. Full text:
`.hermes/cache/scratch/sor-opus-review-r2.md` (transient); findings and
dispositions below are the durable record.

## MAJORs

**M1 — Negative fixture's content check can never fail: FIXED**
(commits 48074ee, 914ef29-era test updates). The builder read 3 columns
from a 2-column TSV, so `$substr` was always empty and
`grep -qF -- ""` matched any file. Now reads exactly `fname substr`,
refuses an empty substring with a hard error, and the m6 hardening
(`|| [ -n "$fname" ]`) covers a missing trailing newline. Negative
fixture rebuilds deterministically to the committed SHA
`e7de08b2…` with the real check active.

**M2 — Deletion-only anchors used old-file line numbers: FIXED**
(commit 914ef29). Each `-` entry now tracks the HEAD (`new_line`)
position where the content was removed, and deletion-only clusters
anchor there. Correct even when earlier lines in the hunk shifted the
count; the old-file line rides on the entry for display. This
SUPERSEDES the r1 disposition of m1 (old-file numbering) — Opus's
counterexample (additions before a deletion in one hunk drift the old
numbering, and the ±1 golden tolerance turns the drift into FP + miss)
is correct. `tests/test_package.py` locks the new contract with the
traced hunk shape.

**M3 — Sweep FP_pos used proximity, not one-to-one matching: FIXED**
(commit ae27e29). `_fp_pos` now derives from `eval_against_golden`'s
matched set (via the new additive `matched_reported` return): two
findings on one golden issue count 1 TP + 1 FP_pos. No duplicated
matching logic left in the sweep.

## MINORs

- **m1 matched list could overcount: FIXED** (914ef29) — `matched` now
  lists exactly the pairs the greedy selection chose (`chosen`), never
  more than `true_positives`; new test covers the traced 10/12 vs 11/12
  case.
- **m2 dead 0.75 filter: FIXED** (ae27e29) — removed; grid comment now
  matches the actual `range(9)` grid.
- **m3 stale mixed-provider run aborted the sweep: FIXED** (ae27e29) —
  `check_single_provider_group` moved after the stale-run gate; a stale
  stray with a foreign provider is skipped, not fatal. New test proves
  the skip; the m7 end-to-end mixed test was reshaped to use a full 3+3
  complement so the mixed-survivor error still fires.
- **m4 sev rounding vs `severity >= 1` report gate: REJECTED with
  reason.** The gate is a deliberate noise floor: findings below
  severity 1 are below MINOR even after halves-up rounding and are not
  worth reporting. Empirically a no-op on the v02-r2 runs (minimum
  judged severity 1.22). Documented here rather than changed; the
  mismatch is intentional.
- **m5 laya load error blamed the package: FIXED** (914ef29) — the
  model-load failure message now names the likely cause (missing/invalid
  checkpoint, with `--model` guidance) and mentions `pip install laya`
  only as the alternative cause.
- **m6 last-line-without-newline hardening: FIXED** (48074ee) — both
  builders use `|| [ -n … ]`.

## Verification (r2 fixes)

- Full suite: 60 passed, 0 failed, no xfail.
- Sweep over the committed v02-r2 metrics: candidate 0.40 (tie
  0.30–0.55), rule 1 FAIL, rule 2 PASS -> KEEP 0.50 — identical to the
  committed benchmark doc; the M2/M3 corrections do not change today's
  numbers (as the review itself predicted).
- Negative fixture rebuilds to the committed SHA under the fixed check.

---

# Opus review cycle 3 (r3) — 7 findings + nits, all dispositioned

Review after the r2 fixes (session 747feed0, $0.69): 0 BLOCKER,
2 MAJOR, 5 MINOR, 5 nits (no action). MAJOR trajectory 4 -> 3 -> 2.

## MAJORs

**M1 — Sweep accepted fail-open and incomplete runs: FIXED**
(commit 2ab24ba). `gate_run` now rejects runs where `fail_open` is true
(a model-unavailable run logs `judged: []`, which reads as valid-looking
zero-FP / zero-TP garbage) and where `len(judged) != n_analyzed`
(parse errors and transient judge failures silently drop clusters, and
the replay treats a missing cluster as "not reported"). Both get the
loud-skip path; the >=3-per-fixture bar still applies. All six
committed v02-r2 runs pass the new gate — they were healthy runs, and
the sweep output is byte-identical.

**M2 — The r2 disposition for m2 was FALSE: FIXED, ledger corrected**
(commit 2ab24ba). The r2 child never removed the dead 0.75 filter; my
verification grep used the wrong pattern (`abs(t - 0.80)`) and missed it
spelled `abs(0.30 + 0.05*k - 0.80)` — a verification failure on my side,
not just the implementer's. The filter is now genuinely gone (GRID =
plain range(9), comment updated). Lesson recorded: verify dispositions
against the described end state, never against a re-statement of the
fix; grep for the behavior, not for one spelling of it.

## MINORs

- **m1 argparse prog was still `jev-review`: FIXED** (24b24c3-era,
  commit 2ab24ba set) — `prog="system-one-reviewer"`.
- **m2 leakage guard silently off without --negative-golden: FIXED**
  (2ab24ba) — the flag is now required; the published procedure always
  passes it.
- **m3 negative fixture header overstated the invariant: FIXED**
  (aa70c49) — header now names the import reorder; fixture content
  unchanged (still rebuilds to the committed SHA).
- **m4 gate_run error text blamed --golden: FIXED** (2ab24ba, inside
  the M1 rewrite) — a missing `judged` array now says "pre-v0.1 record".
- **m5 trailing deletion anchored past EOF: FIXED** (24b24c3) —
  deletion entries clamp the tracked HEAD position to the hunk's
  new-side end (`HUNK_RE` now captures counts; count 0 = pure-deletion
  hunk ends at start-1). TDD: failing test written first; the r2-era
  `@@ -5,1 +4,0 @@` expectation updated from 4 to 3 — with a zero new
  count the file ends at line 3, so 4 was the past-EOF anchor m5
  describes. 61 tests pass.

## Nits (no action required, acknowledged)

Dead `if j in matched_golden` guard in the candidate loop; unreachable
third anchor fallback; `_fp_pos` re-replays what `_eval` computed;
duplicate `check_single_provider_group` in main; CI double-trigger
(last one FIXED in aa70c49 anyway — push now fires on main only).

## Verification (r3 fixes)

- Full suite: 61 passed, 0 failed.
- Sweep over the committed v02-r2 metrics: KEEP 0.50, identical output —
  the six committed runs pass the new fail-open/completeness gates.

---

# Opus review cycle 4 (r4) — final cycle under the code cap

Review after the r3 fixes (session aab8fad6, $0.97): 0 BLOCKER,
3 MAJOR, 5 MINOR, nits. MAJOR trajectory 4 -> 3 -> 2 -> 3. Kurt chose
(option 1) to fix all MAJORs + trivial minors before merge rather than
cap out. Full text: `.hermes/cache/scratch/sor-opus-review-r4.md`
(transient); dispositions below are the durable record.

## MAJORs

**M1 — Positive golden for the O(n²) plant could never match: FIXED**
(commit 2915748). The golden pointed at HEAD line 19 while the plant's
cluster anchors at 17 (first changed line of the run) — distance 2,
outside the ±1 tolerance, so a finding the model made (is_real 0.71-0.72)
was scored miss + FP. Golden moved to line 18 (the `for item in items:`
loop line — the defect's home), substring verify still passes
mechanically in the build script. The SAME committed runs replay to
**TP 5/5, raw precision 5/5, F1 1.00** (flat 0.30-0.55).

**M2 — Benchmark doc had the 17/24 cluster rows swapped: FIXED**
(commit d9d4a24). Doc rewritten: correct cluster table, corrected sweep
(1.00 plateau), an explicit "Corrected in place (r4)" section naming the
error and why the raw metrics' embedded `golden_eval` fields are
superseded by the replay, and an honesty caveat (5-plant fixture; 1.00
is the fixture's ceiling). The "one genuine miss is the O(n²) nit"
claim is withdrawn — the model found it.

**M3 — Header lines leaked into windows; whole-file deletions
misattributed: FIXED** (commit 2915748). `diff --git` now flushes the
previous file before the next file's headers can leak as fake context;
`index`/mode/rename/binary header lines are skipped explicitly;
`+++ /dev/null` no longer hijacks attribution (the real name comes from
the `--- a/<path>` side); `+0,0` hunks floor the deletion clamp at 1.
Deletion anchors corrected to git semantics — verified against real
`git diff -U0` output: `@@ -5,1 +4,0 @@` anchors at 4 (new start N with
count 0 means "file ends at line N, deletion after it"), superseding
the r3 off-by-one reading. Two new tests: multi-file leak and
whole-file deletion attribution/anchor sanity. 63 tests pass.

## MINORs

- **m1 line-number prefixes polluting the benchmark markdown: FIXED**
  (d9d4a24 — doc rewritten clean).
- **m2 stray `--model` split jev runs into different sweep groups:
  FIXED** (d9d4a24) — `--model` is now laya-only; jev always logs
  `model: null`.
- **m3 0.5-0.99 severities never reported (sev>=1 gate): REJECTED with
  reason** — same deliberate noise floor as r2's m4; no change.
- **m4 laya tested only against fakes: ACKNOWLEDGED / DEFERRED to
  v0.3** — package not installed here; tested-by-fake is documented in
  the README table footnote; a guarded integration check belongs to the
  v0.3 tuning pass.
- **m5 wrong tuple comment + dead check in eval_against_golden: FIXED**
  (d9d4a24).

## Verification (r4 fixes)

- Full suite: 63 passed, 0 failed.
- Sweep with corrected golden over the committed runs: TP 5/5, F1 1.00
  plateau 0.30-0.55, candidate 0.40, rules FAIL/PASS -> KEEP 0.50.
- Merge gate: unchanged PASS (negative runs untouched).
- Both fixtures rebuild byte-identical to the committed SHAs.

---

# Opus review cycle 5 (r5) — delta verification after the r4 fixes

Review (session 79fc403b, $0.71): 0 BLOCKER, 2 MAJOR, 5 MINOR. The
reviewer explicitly re-verified the r3/r4 machinery (fail-open gates,
tie rules, provider-check ordering, CI isolation, no stale
jev-review.py references) as clean.

## MAJORs

**M1 — README headline numbers were stale after the golden correction:
FIXED.** README still said 4/5 / 0.80 and called the O(n²) plant a
genuine miss. Updated to 5/5 / 1.00 with the correction note and an
explicit small-fixture caveat.

**M2 — Parser swallowed header-lookalike CONTENT inside hunks: FIXED.**
`--- text` / `+++ text` lines *inside* a hunk are content (a removed
line whose text starts `-- `, an added line starting `++ ` — SQL/Lua
comments etc.), but the r4 header handling matched them by prefix
anywhere in the file, silently dropping the changes (0 clusters —
TDD-verified RED before the fix). Header prefixes are now recognized
ONLY between `diff --git` and the first `@@` (`awaiting_hunk` state);
inside a hunk every `+`/`-` prefix is content. Regression test locks
the traced SQL case; line accounting verified. 64 tests pass.

## MINORs

- **m3 sev>=1 vs sev_level rounding: REJECTED with reason (again)** —
  deliberate noise floor; unchanged.
- **m4 --pr usage line claimed gh: FIXED** — now states the local
  `pr/N` ref requirement with the fetch command.
- **m5 dead `_load_golden_lines` + unclosed file handles: ACKNOWLEDGED,
  deferred to v0.3** — harmless in the CLI; the sweep is being
  restructured in v0.3 anyway.
- **m6 double replay per threshold: ACKNOWLEDGED, deferred to v0.3** —
  same reason; correctness is already guaranteed by M3 (r2) deriving
  FP from the tool's own matching.
- **m7 laya shape mismatch would read as "Approved / no findings":
  PARTIALLY ADDRESSED** — the r3 M1 gate already rejects runs where
  `len(judged) != n_analyzed`, so a sweep over such a run fails loudly
  rather than trusting it; the interactive-path loud failure is noted
  for v0.3.

## Verification (r5 fixes)

- Full suite: 64 passed, 0 failed.
- Sweep: KEEP 0.50 unchanged.

---

# Opus review cycle 6 (r6) — delta verification after the r5 fixes

Review (session f6b6e24c, $0.80): 0 BLOCKER, 1 MAJOR, 7 MINOR. The
reviewer re-verified the r2-r5 machinery as OK (halves-up rounding,
deletion-anchor chain, greedy matching, tie rule, fail-open gates, and
— newly — the corrected golden lines against HEAD content).

## MAJOR

**M1 — Renamed files reported under their OLD path: FIXED.**
`--- a/old.py` set `cur_file` first and `+++ b/new.py` only assigned
when it was None, so a renamed+edited file was judged under a path that
no longer exists at HEAD (unmatchable by golden, skippable by triage
under its old name). New side is now authoritative unless `/dev/null`;
the old side is the whole-file-deletion fallback. Regression test locks
the rename case. (The r4 M3 "first header wins" priority was correct
only for the /dev/null case — the reviewer's reading was right.)

## MINORs

- **m1 git diff output not pinned (mnemonicPrefix/color.ui/quotePath
  would break parsing): FIXED** — `run_git` diff calls now pin
  `--no-color --no-ext-diff --src-prefix=a/ --dst-prefix=b/` and
  `core.quotePath=false`.
- **m2 plain unified diffs (no `diff --git`) silently dropped: FIXED**
  — `awaiting_hunk` now starts True; regression test locks v0.1-style
  input. (Root cause: my r5 `awaiting_hunk` change introduced this; the
  reviewer caught the regression.)
- **m3 laya runs said "Jev" in output: FIXED** — banner and fail-open
  line are provider-aware (`provider/model`); `jev_calls` rendered as
  `model_calls` (metrics field name unchanged for log compatibility).
- **m4 laya shape validation: PARTIALLY ADDRESSED (v0.3)** — the
  completeness gate catches shape-mismatch runs loudly in the sweep;
  the first-call shape validation belongs with the v0.3 laya
  integration work.
- **m5 fixture SHAs depend on user git config: FIXED** — both builders
  now pin `commit.gpgsign=false` and `core.autocrlf=false`; both
  fixtures still rebuild byte-identical to the committed SHAs.
- **m6 sweep cleanups (bare open(), duplicate provider check):
  ACKNOWLEDGED, deferred to v0.3** — harmless in the CLI.
- **m7 no compat shim for jev-review.py: ACKNOWLEDGED, deferred to
  v0.3** — the repo rename is announced in the README; no external
  consumers exist yet (D3: built in public, pre-adoption).

## Verification (r6 fixes)

- Full suite: 66 passed, 0 failed.
- Both fixtures rebuild byte-identical to the committed SHAs under the
  new config pinning.
- Sweep over the committed runs: KEEP 0.50, TP 5/5, F1 1.00 — unchanged.

---

# Opus review cycle 7 (r7) — a BLOCKER of my own making

Review (session b2a75889, $0.78): 1 BLOCKER, 1 MAJOR, 5 MINOR. The
reviewer could not execute git and flagged B1 from reading alone;
verified true on this machine before fixing.

## BLOCKER

**B1 — My r6 flag-pinning broke every diff call: FIXED.** I put the
pinned flags BEFORE the `diff` subcommand (`git -C repo --no-color ...
diff`), which git rejects with `unknown option` (verified live: exit
129-equivalent error before the fix). `--range/--staged/--uncommitted/
--pr` all died before any review. Flags now go after the subcommand.
The reviewer's structural point stands: nothing executed `run_git`, so
no string-diff test could catch this. NEW regression test runs
`run_git` against a real throwaway repo and parses the result —
anchors [2, 4] on a two-run diff.

## MAJOR

**M1 — HTTP errors and shape errors never reached fail-open: FIXED.**
`jev_ask` now raises on `resp.status >= 400` (a 401/429 JSON body parses
fine and was silently swallowed), and `judge` counts shape errors
(`KeyError` on `answers`) toward the fail-open counter instead of
recording them as harmless per-hunk parse_errors. A dead API key now
produces a JEV/system-one-UNAVAILABLE banner, never a clean "Approved".

## MINORs

- **m1 plain multi-file unified diffs parsed wrongly: FIXED** — the
  parser tracks remaining old/new counts from each `@@` header; when
  both hit 0, `--- `/`+++ ` is the next file's header. The r5
  content-lookalike case is preserved (counts not yet exhausted ->
  content); regression test covers both files and both behaviors. (An
  intermediate shortcut broke the r5 case and was replaced by the
  count-tracking fix — TDD caught it.)
- **m2 trailing tab on spaced paths: FIXED** — both header paths are
  `.rstrip("\t")`ed.
- **m3 stale README sample output: FIXED** — shows the provider-aware
  banner and `model_calls=`.
- **m4 laya shape validated on first call: FIXED** — `laya_ask` raises
  on a non-`{"answers": ...}` payload, so a wrong API fails loudly via
  fail-open instead of "Approved".
- **m5 plant #2 was not really a MAJOR bug: FIXED** — `missing` now
  defaults to a `_MISSING` sentinel, so dropping it is a real behavior
  change for explicit-`missing=` callers. This changed the fixture ->
  SHA gate caught it (it works!) -> fixture SHAs updated -> **6 fresh
  live runs (v02-r3-*) re-run against the corrected fixture.**
- **nits (triple replay, unclosed files, unused param): the unused
  `router` param FIXED; replay/file-handle cleanups deferred to v0.3.**

## Verification (r7 fixes)

- Full suite: 68 passed, 0 failed.
- Both fixtures rebuild; positive SHA updated to the sentinel fixture.
- Live v02-r3 runs: **complete and healthy.** 3x positive: TP 5/5,
  recall 1.00, raw precision 5/6 (0.83), F1 0.91 (the 6th finding is
  the model flagging the sentinel plant's leftover `return None` line —
  a real sixth change, honestly unlisted in the golden); 3x negative:
  zero findings of any kind. All six pass the fail-open/completeness
  gates (`judged 6 of 6`, `fail_open false`). Sweep on v02-r3: flat
  0.91 plateau 0.30-0.50, candidate 0.40, rules FAIL/PASS ->
  **KEEP 0.50**. Merge gate PASS. Benchmark doc + README + committed
  metrics jsonl updated to the v02-r3 generation.

---

# Opus review cycle 8 (r8) — my r7 fix had a hole; closed

Review (session 1ea755cb, $0.72): 0 BLOCKER, 1 MAJOR, 4 MINOR. The
reviewer re-verified the r7 B1 flag ordering, the tie rules, the gate
ordering, and the golden lines against HEAD content as clean.

## MAJOR

**M1 — The r7 shape-error fix could never fire: FIXED.** `judge` reset
`failures = 0` after transport success but BEFORE parsing, so each
200-with-garbage response reset the counter and it could never reach
CALL_FAIL_LIMIT — a changed API shape still ended in a silent
"Approved". Shape errors now use a dedicated consecutive counter
(`parse_failures`) that only a successful parse resets; transport
failures keep their own. Regression test: 2 hunks + always-wrong-200
fake -> judge returns None after exactly CALL_FAIL_LIMIT calls. (My
first version of the test used 1 hunk — below the limit — and
correctly failed; the limit semantics are now test-locked too.)

## MINORs

- **m1 `diff -ruN` separators parsed as context: FIXED** — once a
hunk's counts are exhausted, `diff ...` separator lines are ignored;
regression test covers a two-file recursive-diff-style input.
- **m2 PR-level error string said "Jev": FIXED** — provider-aware
("laya model"); the internal `jev_calls` metrics field name stays for
log compatibility, documented here.
- **m3 undocumented origin/main assumption: FIXED** — README --pr line
now states the base.
- **m4 inconsistent timestamp formats between builders: FIXED** — both
use `"2026-09-27T12:00:00 +0000"`; negative fixture SHA verified
unchanged.

## Verification (r8 fixes)

- Full suite: 70 passed, 0 failed.
- Negative fixture rebuilds to the committed SHA.
- No live re-runs needed: r8 M1's fix affects only the failure path;
  the v02-r3 success-path runs are unaffected (all six had
  fail_open=false, judged == n_analyzed, healthy payload shapes).

---

# Opus review cycle 9 (r9) — fail-open completeness + sweep cleanups

Review (session e169a514, $0.72): 0 BLOCKER, 2 MAJOR, 5 MINOR. The
reviewer re-verified the r7 B1 fix and the r8 M1 counter semantics as
clean.

**Process note:** an initial draft of this section dispositioned
findings as FIXED before the code existed. It was discarded before
commit; the dispositions below were written after the implementations
landed and the tests pass. (The r2 lesson, applied.)

## MAJORs

**M1 — A fail-open run still reported verdict "Approved": FIXED.**
`judge` returning None raised the banner, but `compose([], ...)` still
returned "Approved", which flowed into the JSON, the metrics log, and
the grep-ledger last line. main() now forces the verdict to
"Unavailable — provider failed (fail-open)" on the fail-open path.
Regression test drives the full main() with a dead transport and
asserts "Unavailable" in the JSON output.

**M2 — Fail-open unreachable on small diffs / alternating failures:
FIXED (both halves of the reviewer's suggestion).** (a) Failed calls
now record a parse_error finding instead of vanishing via `continue`,
so nothing is silently dropped; (b) if EVERY kept cluster's call failed
(no successful call at all), judge returns the fail-open signal
regardless of the consecutive-counter arithmetic — a dead provider on a
1-cluster diff is fail-open, not a quiet parse_error; (c) on partial
failures the verdict is downgraded to "Approved (incomplete review — N
of M clusters judged)".

## MINORs

- **m1 judge_pr_level read SOR_PROVIDER instead of the CLI flag:
  FIXED** — `set_provider_name` records the wired provider at
  make_provider time (jev / laya[/model]); judge_pr_level reads it.
- **m2 non-numeric score ValueError killed the run: FIXED** —
  ValueError joined the parse-error except tuple.
- **m3 GNU diff timestamps left in filenames: FIXED** — header paths
  are `split("\t", 1)[0]`ed at all four sites; regression test with
  timestamped headers.
- **m4 `jev_calls` metrics key: KEPT** — log compatibility (the render
  shows model_calls; the jsonl key name is documented here).
- **m5 sweep duplicate replay + bare open()s: FIXED** — one
  replay+matching per (run, t) shared by curve and FP census
  (`_fp_pos_from_eval`); dead `_eval`/`_load_golden_lines` removed; all
  file handles `with`-managed. Sweep output verified identical.

## Verification (r9 fixes)

- Full suite: 72 passed, 0 failed.
- Sweep over v02-r3: KEEP 0.50 identical.
- No live re-runs needed: r9 changes touch failure paths and sweep
  internals; the sweep output on the committed runs is unchanged.

---

# Opus review cycle 10 (r10) — downgrade noise + a test that lied

Review (session ed7e2d14, $0.74): 0 BLOCKER, 2 MAJOR, 5 MINOR. Both
MAJORs were defects in the r9 round itself; both verified against the
code/data before fixing.

## MAJORs

**M1 — "incomplete review" downgrade fired on deliberate triage skips:
FIXED.** `n_dropped = len(hunks) - len(kept)` counted docs/lockfile
skips as drops — the committed negative runs (n_hunks 6, n_analyzed 5,
README skipped) would all have been downgraded. Now: triage skips are
counted separately (`n_triaged`); only `--max-hunks` truncation counts
as dropped; the "of N clusters judged" denominator excludes triaged
hunks. New test: a diff with a skipped .md + one judged cluster stays a
clean "Approved" with no "incomplete" anywhere in the output.

**M2 — the r9 e2e fail-open test hit the REAL API: FIXED.**
`main()` calls `make_provider()`, which overwrites the module transport
set by the test — the fake never ran, and the test passed via DNS
failure or a real 401. Now the fake is injected by monkeypatching
`make_provider` itself (and `set_provider_name`); the test also asserts
the metrics record's `fail_open`/`verdict`, per its docstring promise.
(Two subsidiary test bugs found while fixing: `METRICS_PATH` is
captured at import time so `setenv` was a no-op — patch the constant;
the ask contract returns `(payload, ms)` — the bare payload raised and
counted as a transport failure.)

## MINORs

- **m1 NaN/inf/non-numeric values crash later stages: FIXED** —
  `judge()` validates `math.isfinite` on the severity score and numeric
  noul up front; bad values become shape errors (fail-open path).
- **m2 PR digest showed failed calls as severity=none: FIXED** —
  parse_error entries are labelled "unjudged (provider call failed)" so
  the PR-level model can't read them as clean hunks.
- **m3 grep-ledger last line no longer closed-set: FIXED** — last line
  is now exactly one of Approved / Changes requested / Unavailable /
  Incomplete; detail lives on the "Verdict:" line.
- **m4 laya no-model branch unreachable: DOCUMENTED** — kept (library
  / test entry point) with a comment; provider_from always resolves a
  model, so CLI users always get `laya.load(model=...)`.
- **m5 HTTP 4xx retried: FIXED** — only 5xx retry; 4xx raises
  immediately on the first attempt.

## Verification (r10 fixes)

- Full suite: 73 passed, 0 failed.
- Sweep over v02-r3: KEEP 0.50 identical (rules FAIL/PASS unchanged).
- No live re-runs needed: r10 changes touch failure/downgrade paths,
  digest text, and render details — no scoring-path change.






