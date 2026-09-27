# jev-review v0.2 — evaluation completion: packaging fix, negative controls, threshold tuning, tests

Date: 2026-09-27 (rev 4 — after dual review cycles 1–3; cycle-3 findings
tightened reproducibility: deterministic fixtures, SHA-gated sweep evidence,
single-candidate combination rule. Design items E1–E7; E-numbers avoid
clashing with the private decision-log D-numbers)
Status: reviewed — 3 doc cycles done, cycle-3 fixes applied; proceeding to
plan per Kurt's flow with dispositions in
2026-09-27-jev-review-v02-dispositions.md
Scope: `jev-review.py` + `examples/` + new `tests/`, `scripts/`, `docs/benchmarks/`.
Context: v0.1 shipped the reviewer (deterministic git plumbing + Jev judgments).
Cycle-1 review (GLM self-review: 3 minors, fixed; Opus: 2 blockers, 4 majors,
8 minors) proved the evaluation plan was tuning against mislabeled data. This
revision makes the packaging fix and label fix prerequisites for any tuning.

## Problem

1. **Cluster anchoring and context windows are buggy (review-confirmed).**
   `package_hunks` anchors each cluster on the first `+` line in its ±4
   context window, not on the cluster's own first changed line, and the
   window freely contains neighboring clusters' changed lines. Traced on the
   fixture (plants at lines 11/14/17/20/26): cluster anchors come out
   11/11/14/17/26 — plant 2's cluster reports line 11 and includes plant 1's
   code in its before/after state. This is the same dilution class the
   v01→v06 iterations fixed at whole-diff scale; it survives at cluster scale.
2. **The committed golden labels are wrong.** `examples/fixture-golden.tsv`
   claims HEAD lines 13/17/20/24/29; the plants really sit at 11/14/17/20/26
   (`grep -n PLANT /tmp/jev-review-test/src/app.py`). Combined with ±5
   tolerance and greedy first-unmatched matching, the published "precision
   2/3, F1 0.50" contains mislabeled matches (the anchor-26 cluster was
   credited against plant 4's golden line). All published numbers are
   provisional until re-measured on fixed packaging + fixed labels.
3. **No precision-side measurement.** No clean-diff fixture exists; the false
   positive rate on benign changes is unmeasured.
4. **Thresholds are guesses.** `REAL_THRESHOLD = 0.50` predates the data.
   Measured v0.1 runs (labels `fixture-v07-structured-state`,
   `post-generalize` in metrics.jsonl — the earliest labels with a `judged`
   array, which was added mid-v0.1) show true bugs at is_real 0.66–0.72 and
   nits at 0.22–0.41. No sweep has been computed, and the sweep inputs
   proposed in rev 1 (`--out` reports) cannot work: `result["findings"]`
   contains only post-threshold findings. metrics.jsonl `judged` arrays are
   the only complete data source, and `golden_eval` lacks the full plant
   list needed to re-match at other thresholds — so matching must be
   recomputed from a `--golden` TSV, not replayed from the log.
5. **Zero automated tests.** 500+ lines of deterministic logic is validated
   only by API-spending end-to-end runs.

## Design

### E1 — Fixture redesign (prerequisite for everything below)

**The v0.1 fixture gives away its labels.** Plants 1, 2, 3, 5 are comment-only
diffs: the buggy code (`return None`, unguarded `a / b`, duplicate `import
json`, `+=` concatenation) sits in the base commit, and the HEAD diff only
adds `# PLANT n: ...` comments. Recall on that fixture measures whether Jev
believes a comment claiming a bug, not whether it finds bugs — and the
negative fixture (comments) would differ from the positive one only by
comment wording. Every published number is re-measured after this redesign.

`examples/build-fixture.sh` is rewritten so that:
- The **base commit contains clean code** (lookup returns a sentinel the
  caller checks, `divide` guards, single import, efficient loop, explicit
  open mode).
- The **HEAD commit introduces the five real bugs as code changes** — no
  PLANT comments, no label text anywhere in the diff. Labels live only in
  the golden TSV.
- **Builds are deterministic:** fixed `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`
  and fixed author/committer identity, so a rebuilt fixture reproduces the
  committed expected `head` SHA byte-for-byte (the sweep's run-identity
  gate in E5 depends on this).
- Golden line numbers are **mechanically verified, not comment-grepped**:
  with no PLANT markers left in the diff, each build script ends by checking
  every committed golden TSV line against the actual file content at that
  line (the expected code substring is a column of the TSV's verification
  block) and fails the build on mismatch; a unit test repeats the check
  against the committed TSVs so a later edit to a build script cannot
  silently skew the labels.
- `examples/build-negative-fixture.sh` builds `/tmp/jev-review-negative`:
  one commit of benign **code** changes — a behavior-preserving
  local-variable rename, an import-block reorder (no duplicates), whitespace
  reformatting, one comment and one docstring among them (comments may
  appear, but a comment must never be the only difference between a
  positive and a negative change). README.md changes too, solely to
  exercise the markdown-skip triage path; asserted `skipped`, never judged.

### E2 — Packaging correctness fix (prerequisite for tuning)

In `package_hunks`:
- **Anchor** = the new-line number of the first `+` entry *inside the
  cluster's own changed run*; a deletion-only cluster anchors on the first
  context line after the deleted run, else the @@ start line (asserted by
  the E6 test of the same name).
- **Context windows never contain another cluster's changed lines.** The
  window extends at most CTX=4 entries from the run's ends, but is trimmed
  to exclude all other clusters' changed indices (window start = previous
  cluster's last changed index + 1; window end = next cluster's first
  changed index). Neighbor context lines may appear; neighbor *changes* may
  not.
- **`hunk_state` consumes structured entries, never formatted strings.**
  The hunk dict keeps its `(kind, lineno, text)` tuples;
  `code_before_change` / `code_after_change` are built from them directly.
  The `": + "`-substring misfile (a context line like `x = {a: + b}` being
  parsed as an addition) becomes structurally impossible.
- The stale docstring ("separated by <=2 unchanged lines") is corrected to
  the GAP=0 rule in the same commit.
- After this fix, the positive fixture is re-run and all baseline numbers
  (README, this spec's Verification) are refreshed from the new run.

### E3 — Label and matching fix

- `examples/fixture-golden.tsv` corrected and re-verified after the E1
  rewrite (line numbers will shift — code changes replace comment adds).
- Golden matching tolerance tightens to **±1** on the anchor line (anchors
  are now trustworthy per E2).
- Greedy first-unmatched matching is replaced by **nearest-distance
  assignment** (each reported finding matches the nearest unmatched golden
  line within ±1; ties break to the lower line). Findings are matched in
  ascending anchor order, not `-size` order.
- `eval_against_golden` output gains per-TP severity
  (`tp_severities: [...]` in the `golden_eval` block). metrics.jsonl schema
  change is **additive only**.
- A regression test plants two issues 3 lines apart and asserts both are
  matched to distinct goldens.

### E4 — Negative controls and combined precision

Second fixture from E1. The negative golden TSV
(`examples/negative-golden.tsv`) documents the benign lines; FP counting
never filters by it.

- **FP definition (minor-note exemption symmetric):** FP = (positive-run
  reported findings matching no golden AND not MINOR-style notes) +
  (negative-run reported findings that are BLOCKER/MAJOR or MINOR in a
  non-style category). `eval_against_golden`'s per-run precision is labeled
  **raw precision** (it counts minor-style notes as reports) so it never
  conflicts with the sweep's combined figure, which is the published one.
- **Minor-note exemption applies to BOTH runs** (a MINOR `style` note on a
  benign-looking refactor is correct reviewer behavior, not an FP,
  regardless of which fixture produced it). It is counted separately as a
  "minor-note" and never flips a verdict.
- **Component split (the fix to cycle-2 finding 1):** `eval_negative(reported)`
  in `jev-review.py` is a per-run FP counter only — it sees one run and
  makes no claim about combined precision. Combined precision =
  TP / (TP + FP) across both runs is computed by `sweep-thresholds.py` (and
  by nothing else), from two named metrics lines.
- **Run-to-TSV pairing:** metrics records gain an additive `fixture` field
  (`positive` / `negative`, from a new `--fixture NAME` CLI flag, default
  empty for ad-hoc runs) so the sweep and the aggregator never guess which
  golden TSV belongs to which run.
- **Negative pass bar and merge rule:** zero BLOCKER/MAJOR findings in
  **every** negative run (all N ≥ 3) at the shipped threshold is a **merge
  gate** for this PR.
  If it fails, the PR may not merge with a threshold change; it may merge
  with the threshold unchanged only if the failure is analyzed in the PR
  description and the failure itself becomes a filed v0.3 issue. The pass
  bar does not feed the threshold-change rule (E5 handles that
  independently).

### E5 — Threshold sweep (`scripts/sweep-thresholds.py`)

- **Input:** metrics.jsonl only (`--label` selects runs; requires the
  `judged` array and that the run was made with `--golden`), plus the
  golden TSVs passed explicitly (`--golden`, `--negative-golden`). The exact
  metrics lines used are committed under `docs/benchmarks/` beside the
  published table so the table is reproducible.
- **Post-E1 evidence only:** metrics records carry two additive identity
  fields: `packaging_version` (stamped `v02` by the E2 code fix) and
  `fixture_head` (the reviewed commit SHA, already logged as `head`). The
  fixture build scripts are **deterministic** — fixed `GIT_AUTHOR_DATE` and
  `GIT_COMMITTER_DATE`, fixed author/committer, so a rebuilt fixture
  reproduces a known `head` byte-for-byte. Both build scripts print the
  expected SHA on completion, the expected SHAs are committed constants in
  the scripts, and the sweep **rejects** any run whose logged `head` does
  not match its fixture's committed expected SHA and whose
  `packaging_version` is not `v02`. A stale or hand-edited fixture
  therefore fails loudly instead of silently collapsing recall. The v0.1
  labels (`fixture-v07-structured-state`, `post-generalize`) have
  contaminated anchors and are never tuning input.
- **Sample requirement:** the sweep runs on **N ≥ 3 runs per fixture**
  (fresh runs made for this PR) and a candidate must improve F1 in **every
  positive run** (not on average) — one flipped finding on one run cannot
  move the threshold.
- **Gating replay uses `compose` itself:** `compose` gains a
  `threshold=REAL_THRESHOLD` keyword parameter (default unchanged); the
  sweep imports `jev-review.py` via
  `importlib.util.spec_from_file_location` and calls `compose` per
  threshold — no logic duplication, no drift.
- **Range:** 0.30→0.75 step 0.05. Thresholds within 0.05 of the 0.80/0.90
  plateaus are excluded (plateau rule, per the Jev service note — still
  current as of the Sep 26 threshold adjudication).
- **Tie-break:** if several thresholds share the max F1, the middle of the
  tied range is the candidate.
- **Combining runs (single candidate):** the sweep builds a combined curve
  by taking, per threshold, the **minimum F1 across the N runs** (the
  worst-run figure — a candidate must work everywhere to score). The
  candidate threshold = argmax of that combined curve; the tie-break above
  applies to the combined curve. The every-run margin check (below) is then
  evaluated at that single candidate for every run — one candidate, one
  decision, reproducible from the committed metrics lines.
- **Change rule:** `REAL_THRESHOLD` changes in this PR only if the candidate
  beats 0.50 in EVERY positive run by a margin that exceeds one finding's
  F1 weight (with 5 goldens, one TP is worth ~0.1–0.2 F1, so the margin
  floor is **0.20 F1 in every run** — the previous ≥0.05 accepted a single
  noisy score) AND does not increase FPs on any negative run's `judged`
  data. Otherwise 0.50 ships with the table as evidence.
- **Jitter zone follows the parameter:** `compose`'s jitter detection uses
  the passed `threshold`, not the global; tested.

### E6 — Behavior change: severity rounding, and the test suite (`tests/`, pytest, offline; `jev_ask` monkeypatched)

**Stated behavior change (not a test-only detail):** `sev_level` switches
from banker's rounding (`round(2.5) == 2`) to `floor(v + 0.5)`
(`2.5 → 3`): a fractional severity of 2.5+ now reads as BLOCKER and can
flip a verdict from Approved to Changes requested. This changes what
verdicts are comparable with v0.1 logs; the README notes it when numbers
are refreshed.

Isolation setup (applies to all tests): set `JEV_REVIEW_METRICS` to a
tmp_path before `exec_module` (METRICS_PATH is read at import time), and
point `HOME` at tmp_path for `load_api_key` tests (expanduser).

- `package_hunks`: multi-file diff; gap=0 isolation (two changes separated
  by two unchanged lines produce two clusters); **trimmed windows contain
  no other cluster's changed lines**; **anchor = cluster's own first `+`
  line** (the 3-lines-apart regression case); **deletion-only cluster
  anchors on the first context line after the deleted run, else the @@
  start line**; empty diff returns [].
- `hunk_state`: built from structured entries; includes a line whose text
  contains `": + "` and asserts it lands in `before`/`after` as context,
  not as an addition.
- `triage`: lockfile and docs skips; oversize hunk flagged, not judged.
- `sev_level`: switched to `floor(v + 0.5)` so halves round up
  (0.5→1, 1.5→2, 2.5→3, -1→0, None→0) — tests assert exactly this.
- `compose(threshold=...)`: blocker → Changes requested; two majors →
  Changes requested; single minor → Approved; jitter-zone score lands in
  the jitter list; threshold parameter actually moves the gate.
- `eval_against_golden`: TP within ±1, miss, nearest-distance tie, severity
  capture.
- `judge()`: **fail-open contract** — CALL_FAIL_LIMIT consecutive
  `jev_ask` raises return `(None, latencies)`; **parse_error path** — a
  malformed payload produces a `parse_error` record, not a crash.
- `load_api_key`: env var beats file; file fallback order; friendly error.

### E7 — CI (GitHub Actions)

`.github/workflows/ci.yml`: pytest on push/PR, Python 3.10 and 3.12. No
secrets, no network — the suite is offline by design.

## Deliberately does not change

- Question phrasing and the batched per-cluster call shape (current tuning
  baseline; the sweep depends on them).
- The metrics.jsonl schema except **additively**: new `golden_eval` fields
  (`tp_severities`, per E3), new top-level `fixture` and `packaging_version`
  fields (per E4/E5). Nothing removed or renamed.
- v0.1 CLI surface except two additive flags on `jev-review.py`:
  `--negative-golden FILE` (per-run negative evaluation) and
  `--fixture NAME` (run-to-TSV identity for the sweep). The sweep's own
  flags live on `sweep-thresholds.py`.
- Single-file layout of `jev-review.py` (tests import it via
  `importlib.util.spec_from_file_location`; a split is out of scope).
- The `compose` finding-record shape (`f["hunk"]["file"]`, ...): the sweep
  re-wraps flat `judged` entries into that shape before replaying — no
  change to `compose`'s input contract.

## Cost effect

Cluster count after E1 is re-measured, not assumed (rev 1's "six clusters"
was wrong: the positive fixture alone produced 5 clusters plus one PR-level
call, and the negative fixture adds more). Per-cluster cost stays ~100 ms /
fractions of a cent; a full both-fixtures evaluation stays well under $0.01.
CI is offline and free. The sweep is a local file read.

## Verification

- `pytest -q` green on 3.10 and 3.12 in CI.
- Fixtures rebuilt per E1 (labels verified out-of-band, not in the diff).
- Positive fixture re-run **after E1/E2/E3** (N ≥ 3 runs, labels + fixture
  field recorded): refreshed recall/precision/F1 published in README with
  run labels; the metrics lines are committed under `docs/benchmarks/`.
- Negative fixture run at the shipped threshold: zero BLOCKER/MAJOR
  findings is the merge gate (E4); minor-notes and any FPs are published
  with analysis either way.
- Combined precision TP/(TP+FP) published by the sweep from both fixtures'
  runs.
- If `REAL_THRESHOLD` changes: sweep table committed under
  `docs/benchmarks/` and README numbers refreshed in the same PR; otherwise
  the table documents why 0.50 held.
- README consistency fixes land in the same PR ("the two misses" → correct
  count; `--negative-golden` / `--fixture` in usage; sev_level rounding
  behavior change noted).

## Rollout order

Branch `v02-evaluation`, one PR: fixture redesign + packaging fix + label
fix + tests + negative controls + sweep land together, so published
numbers, the tool producing them, and the tests protecting them are
consistent at merge. Merge with a regular merge commit (repo convention —
no squash). CI green before merge; negative-run merge gate per E4.

## Open questions

- None blocking. If the negative fixture yields BLOCKER/MAJOR findings at
  every swept threshold, that is a question-phrasing finding for v0.3, not
  a blocker here.
