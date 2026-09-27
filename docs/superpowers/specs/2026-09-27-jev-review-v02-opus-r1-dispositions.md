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
