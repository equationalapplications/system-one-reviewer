# v08 gate results — Task 8 (G-A + G-D band check): **STOP — band-check trigger fired**

**Date:** 2026-10-02 (runs 2026-10-02T22:49–2026-10-03T02:58 UTC) · provider
`jev` (live) · build `impl/ast-units` @ `8395b4f` (`v08-ast`) · ledger labels
`task8-*` in `~/.local/state/jev-review/metrics.jsonl`.

## Verdict: STOP — do not land

The G-D defect-positive band check (r8-M2, Kurt's option-1 ruling guard)
MISSED band goldens on the span-containment criterion. Per the pre-agreed
halt (plan rev 14, Task 8 step 4b): STOP, do not land, and take option 2 (a
separate ~120-line AST engagement threshold) back to Kurt with the
missed-anchor data below. G-A and the threshold re-sweep PASSED before the
halt; G-C and the G-D control/enrichment-off arms were NOT run (halt is
immediate by design — the remaining arms cannot change the trigger, which
is evaluated on the v08 arm alone).

## THE MISSED-ANCHOR DATA (what the pending-ruling resolves on)

Band goldens (`examples/cj43-prefix-band-goldens.tsv`, at SHA `11be74c`):
`src/machines/importMachine.ts:16` (signature contract) and
`src/machines/importMachine.ts:119` (abort race, stopped-flag).

**Geometry that produced the miss (root cause, mechanical):**

1. The band cluster is a **new file** (`new file mode 100644`,
   209 lines, `67262aa...11be74c`). Its PRE-image does not exist
   (`git show 67262aa:src/machines/importMachine.ts` → path not in tree).
2. `mode_file_images` correctly returns `pre=None`; `ts_units` still runs
   on the POST-image alone, but **every root node of the file is an
   anonymous `export const importMachine = setup({...})` /
   `export type ...` statement — `child_by_field_name("name")` is None for
   all of them**, so `units == []` and `ts_units` returns None. There is
   no top-level name to split on: the whole file IS one expression.
3. Fallback order: line windows (would cover :16 and :119 in separate
   44/120/45-line windows) and halving are never reached, because the
   engagement gate is TOKEN-based (r1-M4): the whole-file cluster
   serializes to **2,619 estimated tokens — far below
   `SOFT_CAP_TOKENS=28_000`** — so `expand_oversize_units` never splits it.
   The cluster is judged as ONE 1–209 whole-file call with a single
   anchor at line 1, on every run, with enrichment stamped `none`
   (no ast_context for a file with no enclosing symbol either).

This is exactly the plan's flagged consequence for the 121-line…84k-char
band (rev 6 header: "clusters from ~121 lines to ~84k chars … are now
judged as ONE whole call with a single anchor — wisdom.ts never splits;
importMachine.ts-scale evidence sits below the token gate"). The band
check was built to measure precisely this, and it measured it: **the
defect-positive anchors ride in a cluster that (a) never splits and (b)
is only intermittently reported, because `is_real` for the whole file
hovers at the 0.50 threshold.**

**Run-by-run span-containment results (v08 arm, 3 repeats; each label also
has an earlier same-geometry set from the pre-tree-sitter build — 6 runs
total, all identical geometry):**

| run | importMachine.ts judged unit | severity | is_real | reported | :16 HIT | :119 HIT |
|---|---|---|---|---|---|---|
| task8-gd-v08-band-1 | span 1–209 (whole file, 1 anchor) | 1.04 | 0.44 | no | **MISS** | **MISS** |
| task8-gd-v08-band-2 | span 1–209 | 1.23 | 0.47 | no | **MISS** | **MISS** |
| task8-gd-v08-band-3 | span 1–209 | 1.35 | 0.55 | YES | HIT | HIT |

- Runs 1–2: the cluster is judged (span covers both goldens) but NOT
  reported (`is_real` 0.44/0.47 < 0.50) → both goldens MISSED on
  span-containment → **TRIGGER**.
- Run 3: the whole-file cluster IS reported → both goldens HIT — but the
  greedy one-golden-per-cluster rule (r8-M2) credits only ONE golden;
  two goldens in one cluster means band recall is only PARTIALLY
  unmeasured even on the best run (same escalation path per the plan).
- Across 6 live runs (two independent sets of 3), the cluster reported
  2 of 6 times. The "measured-via-split" branch (zero goldens in band
  clusters because the cluster split) does NOT apply — the cluster never
  split.

**Why this is structural, not model noise:** the split decision is
deterministic (token gate) and the failure mode is geometric (one anchor
at line 1 represents 209 lines; ±1-line matching cannot see lines 16/119
when the single-unit verdict lands anywhere below is_real 0.50). Option
1's guard has therefore measured the exact risk Kurt held the ruling
open for: **under a token-only engagement gate, importMachine.ts-scale
band clusters are judged whole, and defect recall inside them depends
entirely on the model's whole-file `is_real` clearing 0.50.** Option 2
(a separate ~120-line AST engagement threshold, splitting this cluster
into the 44/120/45-line windows the fallback already computes) is the
pre-agreed alternative and now has its deciding data point.

## G-A: PASS (run before the halt)

Positive + negative fixtures rebuilt at the committed SHAs
(`3346ca1a…` / `5ca6f013…`, verified by the build scripts). 3× each,
live, labels `task8-ga-pos-N` / `task8-ga-neg-N` (each run logged twice
in the ledger: the first GA batch crashed writing `--out` into a
missing dir AFTER the model calls and ledger write; the second batch is
the scored set — 18 task8 ledger lines total, all geometry-stable).

- Positive: verdict **Changes requested** ×3/3 (stability: 3 of 3 agree
  exactly). TP 5/5, recall 1.0, precision 1.0 (F1 1.0) on ALL THREE
  runs — the v03b-era `return None` sentinel FP_pos is gone on v08
  (matched anchors identical across runs: app.py 6/13/16/20/27).
- Negative: verdict **Approved** ×3/3, **0 findings of any kind** ×3/3,
  0 blocker_major (merge gate holds). The only skip on any fixture run
  is the deliberate `README.md` docs triage (legitimate). Zero
  `hunk>`/`too_large` skips anywhere.
- `n_dropped = n_unjudged = n_size_skipped_code = 0` on all 6 runs
  (`gate_run` semantics clean).

## Threshold re-sweep: PASS — 0.50/0.70 hold on v08

`sweep-thresholds.py` on the 6 v08 fixture runs (default
`--packaging-version v08-ast`): **candidate 0.50, decision KEEP 0.50**
(rule 1 FAIL is the no-candidate-beats-shipped path: 0.45–0.60 tie at
min-F1 1.00 with zero margin over shipped; rule 2 PASS). Code threshold
0.50 stands. The deletion knob (0.70) was not re-derivable from fixtures
alone (no deletion-rubric fixture rows moved); field-mode dt evidence
belongs to G-C, which did not run — flagged in the escalation.

## G-C / G-D control + enrichment-off arms / corpus replay: NOT RUN (halt)

G-D's trigger is defined on the v08 arm alone and fired on its first
sample; the plan's stop is immediate, so the control (v03b) arm, the
`--no-enrichment` arm, the 5-head G-C FP census, the 121-line…84k-char
G-C sub-measure, and the corpus replay were not executed. No gate is
reported as passed or failed without data — they are OPEN, pending
Kurt's option-2 ruling and a re-run.

## Costs / repro

18 live jev runs total (264 cluster calls + 18 PR-level calls; mean
input ≈ 823 tokens/call) ≈ **$0.35–0.50 all-in** — well under budget
because the halt fired on the first G-D sample. Reproduce the band arm:

    cd <sor repo> && .venv/bin/python system_one_reviewer.py \
      --repo <curated-journal checkout at 11be74c> \
      --range 67262aa...11be74c --provider jev \
      --label task8-gd-v08-band-<N>

Full test suite at the halt point: **357 passed, 2 skipped**
(TMPDIR=/tmp).
