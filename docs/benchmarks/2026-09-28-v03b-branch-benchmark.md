# v0.3b branch benchmark — fixtures re-run on the corroboration-round code

**Date:** 2026-09-28, branch `v03-field-evals`, provider `jev`,
`PACKAGING_VERSION=v03b`.

## Build provenance per record (Opus r5 m3)

The six records were NOT all produced by the same commit, but all by
builds with an IDENTICAL model-input shape (all post-B1: ledger carries
rubric/references_remaining/change_type; field-identity verified at
extraction time):

- `v03b-pos2-1`, `v03b-neg2-1`: re-run on the **r3-fixes build**
  (70b6fcc) to pick up the B1 ledger fields Opus r2 required.
- `v03b-pos2-2`, `-3`, `v03b-neg2-2`, `-3`: produced on the
  **r2-fixes build** (d80f275).

Labeled order in `2026-09-28-v03b-branch-metrics.jsonl` follows run
order within each build, not global wall-clock time. No threshold or
prompt bytes changed between the two builds, so one version tag is
correct; the split is recorded here rather than silently merged.

## Negative fixture (3 runs; includes the benign whole-file-deletion
cluster added for the #45 failure shape)

- Verdict: Approved ×3, **0 false positives**.
- The benign whole-file-deletion cluster scores sev 0.03,
  is_real ≈ 0.2, confidence 0.97 — vs sev 2.73–2.82 / conf 0.73–0.82
  under the v0.2 questions that produced the #45 false BLOCKER.
- `references_remaining` computed False on every deletion cluster
  (nothing survives that names the removed modules).

## Positive fixture (3 runs)

- Verdict: Changes requested ×3; the planted bug is reported each run
  (some run-to-run variance in which adjacent hunks also get flagged —
  consistent with the v0.2 record).

## Goldens

`examples/fixture-shas.txt` (positive) and `examples/negative-golden.tsv`
(negative) pin the fixture heads; every record's `fixture_head` matches.

## Open

Deletion-rubric threshold (0.70) is provisional — sweepable only after
the curated-journal PRs are re-run under v03b with their own golden set
(tracked in the eval brief, F2 executability plan).
