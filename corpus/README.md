# Real-PR corpus

Pointer-only ground truth for evaluating system-one-reviewer on real PRs
(spec: `docs/superpowers/specs/2026-09-28-corpus-eval-design.md`).

- `prs.tsv`, `issues.tsv`, `dismissed.tsv` are **generated** by
  `scripts/mine_corpus.py build` from `corpus/work/` inputs. Don't hand-edit
  them; change the inputs (adjudications, spot-check, promotions) and rebuild.
- Every issue/dismissed row's `verify_substring` is checked against the
  pinned SHA at build time.
- Private repos live in gitignored `corpus/local/` (same schema).
- Session transcripts are never committed.

## Provenance and counts

Built 2026-09-28 from 9 of the 10 plan repos
(`equationalapplications/clanker-functions` no longer exists on GitHub or
in the cache and was skipped, not renamed). Inputs are in `corpus/work/`:
`adjudicated.jsonl` (auto-judge), `spot-check.md` (human-verified sample),
and per-repo thread anchors from `gh api graphql`.

### Sample counts

| metric                 | committed | private (`local/`) | total |
|------------------------|----------:|-------------------:|------:|
| PRs (samples)          |        36 |                 11 |    47 |
| ↳ `kind=clean`         |        20 |                  8 |    28 |
| ↳ `kind=positive`      |        16 |                  3 |    19 |
| ↳ `split=train`        |        23 |                  9 |    32 |
| ↳ `split=holdout`      |        13 |                  2 |    15 |
| Issues                 |        47 |                  9 |    56 |
| Dismissed              |        16 |                 13 |    29 |
| Dropped (verify fail)  |          |                   |    18 |

Holdout share over the 47 distinct PRs is 0.32 (gate `[0.25, 0.35]`).
Private repos: `equationalapplications/axon`,
`equationalapplications/equationalapplications.com` — written to the
gitignored `corpus/local/`.

### Repos and splits

| repo                                                  | train | holdout |
|-------------------------------------------------------|------:|--------:|
| equationalapplications/axon-runtime                   |     4 |       0 |
| equationalapplications/clanker                        |     0 |       2 |
| equationalapplications/curated-journal                |     3 |       1 |
| equationalapplications/curated-thoughts               |     3 |       4 |
| equationalapplications/curated-thoughts-integrations  |     6 |       0 |
| equationalapplications/expo-llm-wiki                  |     2 |       5 |
| equationalapplications/system-one-reviewer            |     5 |       1 |
| equationalapplications/axon *(private)*               |     3 |       2 |
| equationalapplications/equationalapplications.com *(private)* | 6 | 0 |

### Issue mix

| severity_class | issues | dismissed |
|----------------|-------:|----------:|
| blocker        |      1 |         0 |
| major          |     17 |         2 |
| minor          |     38 |        27 |

| category       | issues |
|----------------|-------:|
| bug-risk       |     35 |
| maintainability|      8 |
| security       |      7 |
| test           |      6 |

| dismissal_reason | count |
|------------------|------:|
| false-positive   |    20 |
| style            |     9 |

### Adjudication and spot-check

- All 85 rows were auto-adjudicated; the spot-check sampled 21 random rows
  plus every disposition-vs-label disagreement for human verification
  against the cached repo clones.
- Agreement on the 21 random rows: **19/21 = 90.5%** (gate ≥85%). The other
  2 random-sample rows disagreed, and 1 further disagreement came from the
  disposition-vs-label scan — 3 re-adjudicated rows in total
  (curated-journal#27, curated-thoughts#73,
  equationalapplications.com#35); the spot-check sheet records the
  correct labels and rationales.

### Known losses

18 rows were dropped at verify time because the anchored line fell
outside the cited file at the pinned SHA — files shrank, lines moved, or
the cited substring wasn't present at the head. The build logs a
candidate ID and verifier error for each. Rebuild against current
heads to recover rows whose fix was already merged (e.g.
`system-one-reviewer#7` PRRT_kwDOUusgms6m539R is fixed at the head SHA
this build ran against but anchored at the pre-fix commit).