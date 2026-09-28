# v0.3b field proof — curated-journal PRs #43–#47 re-run live

**Date:** 2026-09-28 · provider `jev` · `PACKAGING_VERSION=v03b` (merged
main, `2a72e21`) · labels `v03bcj-prNN-20260928T163214Z` (ledger:
`~/.local/state/jev-review/metrics.jsonl`, copy committed alongside the
sweep benchmark).

## What this proves

The #45 fix (deletion rubric + corroboration gate) was fixture-proven at
merge time; these five live re-runs make it **field-proven**: the exact PRs
that produced the v0.2 false-BLOCKER (and the rest of the original field
cohort) re-reviewed under the shipped v0.3b build, against the squash
commits now on main — the same merge-base ranges F5 made the default.

## Ground truth (bot + human, verified at each MERGED head)

| PR | Delta reviewed | Bot/human findings during review | At merged head |
|----|----------------|----------------------------------|----------------|
| #43 | `99711a4^...99711a4` perf(import): linear-time OKF import | 3 `major` inline (aws-cloud-agent-pr-review, mid-PR revisions): abort/cleanup race ×2, stale importDump-signature claim | all addressed at head (`stopped` flag + two-step CANCEL handshake + `completed`-decides-outcome; tests use the 3-arg signature) → **clean** |
| #44 | `2dc4085^...2dc4085` fix(night-shift): finished-run copy | 2 `major` inline — both rebutted as stale (fixed at final head, tests present) → **clean** |
| #45 | `b43825c^...b43825c` chore: remove unused Expo components | 0 inline findings (deletions verified safe) → **clean** |
| #46 | `861f1ad^...861f1ad` feat(dev): cached LLM auto-load + mock mode | CodeRabbit 4 (2 minor, 2 major) + bot 1 major; the real ones (document-chunk ordering, model preservation) **fixed at head** — verified in the merged tree (`mockLlmProvider.ts` checks `Document Chunk:` first; `pushAndroid` skips when the installed model matches) → **clean** |
| #47 | `67262aa^...67262aa` fix(ui): button border | 0 findings → **clean** |

Net: **5/5 merged heads defect-free** — all five are negative goldens
(`examples/cj-field-goldens.tsv`, SHA-pinned to the squash commits).

## Results (v03b, live)

| PR | Verdict | Reported findings | vs ground truth |
|----|---------|-------------------|-----------------|
| #43 | **Changes requested** | 11 (sev 1.4–2.1, is_real 0.5–0.79) | FP on a clean head — but see caveats |
| #44 | Approved | 0 | ✅ |
| #45 | Approved | **0** (7 deletion clusters, all is_real ≤ 0.55, refs_remaining=False → suppressed) | ✅ **the #45 false-BLOCKER is gone in the field** |
| #46 | Approved | 2 MINORs (verdict unaffected) | ✅ |
| #47 | Approved | 0 | ✅ |

**4/5 verdicts correct; the single miss is over-reporting on #43, not a
false BLOCKER on deletions.** Under v0.2 the same PRs produced a false
Changes-requested driven by deletion findings at sev 2.7–2.8; under v0.3b
every deletion cluster on clean heads is either suppressed by the rubric
gate (#45) or corroboration-starved (#43's two deletion findings never
reach the verdict).

## Caveats (honest ones)

1. **`MAX_HUNK_LINES` blind spot on #43.** `src/machines/importMachine.ts`
   (274-line hunk — the heart of the PR, and where the review bot's
   abort-race findings lived) and `__tests__/importMachine.test.ts` (152)
   exceeded the 120-line triage cap and were noted-not-judged. 30 of 32
   hunks were analyzed; the two skipped were the two biggest. The #43 FP
   count therefore measures the tool's behavior on the *rest* of the PR,
   not on its core file. A "judge large hunks in slices" follow-up is the
   obvious F-series candidate.
2. **Single sample per PR.** One run each, no repeat-variance measure
   (the fixture benchmark uses n=3 per fixture). Labels are unique per
   PR, so re-runs need fresh labels before any sweep re-selection.
3. **Single provider** (jev). Laya field runs remain undone (local stack
   required).
4. **Ground truth is bot+human review, not execution.** The five heads
   all pass CI and were human-merged; residual defects would be shared
   blind spots of every reviewer involved.

## Ledger

The five records are copied to
`docs/benchmarks/2026-09-28-v03b-cj-field-metrics.jsonl` (verbatim from
`~/.local/state/jev-review/metrics.jsonl`) so the sweep is reproducible
without the local ledger:

```
sweep-thresholds.py --metrics docs/benchmarks/2026-09-28-v03b-cj-field-metrics.jsonl \
  --label v03bcj- --field --field-goldens examples/cj-field-goldens.tsv
```
