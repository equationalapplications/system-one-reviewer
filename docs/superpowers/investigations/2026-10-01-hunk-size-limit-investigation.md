# Investigation: the `hunk>120 lines` coverage hole

**Status:** step-zero investigation, rev 19 — **APPROVE WITH NITS**
per Opus r13 (f02d4998). **ALL DECISIONS RULED (2026-10-01):**
clearance batch 1 via Gemini review + Kurt approval (D1, 2, 3, 5, 9,
10); batch 2 via Kurt (D4 guard-band, D6 measured in implementation,
D7 interim loss accepted, D8 p95 measured in implementation).
**Rev 18: Gate 3 tolerance made numeric (CodeRabbit/Gemini blocker
resolved):** windowed-cluster FP rate ≤ 1.5× the ordinary per-cluster
rate (≈0.315; hard fail >2× ≈0.42), derived from the baseline ledgers
(14.2 clusters/clean run × fp_per_clean 2.98 ⇒ ≈0.21/cluster).
**Rev 19 amendment: windows INHERIT `change_type: code-change`; no
per-window recomputation** (zero-`+` windows must not reclassify as
deletion-shaped — the ratio floor handles them via unplaceable).
**Step 0′ IMPLEMENTED (d2a981e), verified live; Approach A next.**
**Ask:** 2–3 architectural approaches to close the coverage hole without
turning sor into a slow reviewer. Kurt's prior: "some kind of loop" —
algorithmically fast; a bounded, measured latency increase is acceptable.

## Problem

`MAX_HUNK_LINES = 120` (`system_one_reviewer.py:50`) makes
`package_hunks` (`:439`) mark any hunk whose rendered window exceeds 120
lines `too_large` (`:694–696`), and `triage()` drop it with reason
`hunk>120 lines` (`:717`). Those lines are never model-judged. A PR whose
core payload is one large new file is "reviewed" with the heart of the
change skipped and can still print a bare `Approved`.

## Field triggers (verified)

- **CTI PR #22** (DSH/DeepSeek wisdom, merged 2026-10-01): shadow runs on
  3 commits skipped `wisdom.ts` (507-line hunk) and `test_wisdom.ts`
  (966-line hunk) in every run — the PR's core files were never judged
  (shadow tally: `~/Documents/equational-wiki/immutable-source-files/agents/memories/sor-shadow-tally.md`,
  row 2 — vault path given for in-repo reviewers, r7-m4).
- **Systemic.** v06-postmerge corpus runs (local
  `corpus/work/runs/v06-postmerge/`, gitignored via `.gitignore:6`): 198
  `hunk>120` skip records across 54 of 108 ledgers; 52 distinct skipped
  (file, span) clusters. Precedent: `docs/evals/2026-09-28-v03b-cj-field-proof.md`
  flagged CJ PR #43's 274-line `importMachine.ts` and proposed "judge
  large hunks in slices". Worst case: `…system-one-reviewer_7_final/r1`
  — 22 hunks, 12 analyzed, **8 size-skipped**, verdict `Approved`.
- **Applicability near-total; golden target exact (measured):** every
  `-` entry carries the same tracked new-side line (`:569–570`); the
  span is built from those lines (`:661`); so a deletion-only hunk's
  span is ≤ 2·CTX+1 = 9 lines, and any skip record wider than 9 lines
  necessarily contains `+` lines. Of the 52 clusters, **51 are
  code-change** (span > 9); **at most 1 is deletion-shaped**
  (`jev-review.py [1-1]` — span ≤ 9 does not prove deletion-only, a
  200-`-`/2-`+` rewrite also has a small span; 1 is an upper bound on
  deletions, tightened when Step 0′ starts carrying real
  `change_type`, r7-m5). **All 24 size-skip golden-miss instances sit
  in code-change clusters — 0 in the deletion-shaped one** (computed
  via `classify_miss` + `_covers` + covering-skip spans, 108 ledgers).

## Denominators (defined once)

- Corpus: **36 distinct sample runs × 3 repeats = 108 ledgers** (the
  scorer reports 108 sample-repeats: 48 positive + 60 clean). Span
  figures are new-file line spans; rendered-window counts (`h["size"]`)
  are larger and computed at spec time (r6-m2).
- Fixture benchmarks (F1 0.91 source): built by
  `examples/build-fixture.sh` / `build-negative-fixture.sh`, SHAs pinned
  in `examples/fixture-shas.txt` — **not** `tests/data/v01-fixture.diff`.

## Step-zero baseline (measured on this machine, replay, no model calls)

`python3 scripts/score_corpus.py --config v06-postmerge --split all`
(requires the gitignored ledger tree; **re-run before the spec** — r5-m5):

| metric | value |
|---|---|
| golden issues | 138 (48 positive / 60 clean sample-repeats) |
| recall strict / cluster | 0.02 / 0.11 |
| skipped-triage misses | 60 of 138 golden-instances (43%) |
| FPs per clean PR | 2.98 |
| verdict accuracy | 0.70 |

**Attribution:** of the 60, **24 in `hunk>120` skipped clusters — all
24 code-change (exact)**; 9 in docs skips inside the same runs; 27 in
runs with no size-skips. **The chunking target is exactly those 24**
(17% of all goldens; 40% of skipped-triage). Gate 2 keys on them.

## RESEARCH_REQUEST answers (r3–r8, consolidated)

1. **Latency** (96 parseable ledgers): `total_latency_ms` median
   **1406 ms**, max **7110 ms** (sum of per-call times, not wall-clock;
   excludes the PR-level call, `:1314/:1337`); per-call median
   **165 ms**, max **300 ms**. No sub-3 s target exists in the repo;
   the spec proposes the wall-clock budget as a new explicit README
   number and adds `wall_clock_ms` to the ledger. Chunking
   `sor_7_final`'s ≥20 windows is **≥3.3 s serial; the upper bound is
   unmeasured** — the corpus per-call band was measured on mostly small
   inputs, so this is a floor, not a range (r7-m1/r8-m1), until
   `wall_clock_ms` exists. No parallel-speedup projection is claimed
   (r5-m4); pool size set by the Jev policy answer.
2. **`sor_7_final`:** 8 size-skipped clusters, spans 121–491; **≥20
   windows by span (lower bound)**; true count from `h["size"]` at
   spec time (Gate 7), including the **per-run total** window count
   over the corpus (Gate 2's precondition, r8-M1).
3. **Fixtures** (rebuilt, SHAs verified, via the tool's own
   `package_hunks`): positive 6 hunks max window **11 lines**; negative
   7 hunks max **9 lines**; `too_large` False everywhere. Fixture
   prompts and verdicts are byte-identical under Step 0′.
4. **Jev concurrency/rate-limit policy: NOT FOUND** (repo docs + vault
   searched). Open Kurt-decision; default pool 2 with
   `--serial-windows` escape hatch; **concurrent 429 handling per
   r8-m2 below** (a 429 raises `_NoRetry`).
5. **Golden-miss attribution:** 24 / 9 / 27; the 24 all code-change.
6. **Cluster composition:** ≤1/52 deletion-shaped (upper bound); the
   insertion-vs-rewrite split needs a live `package_hunks` pass over
   the corpus PR diffs (repos not local) — Gate 7.

## Why the limit exists (hypotheses)

H1 context quality (never measured); H2 cost/latency — serial judge
loop (`judge()` `:920`, per-hunk `for` `:935`), ≈165 ms/call; H3 score
comparability (fixture calibration; F1 0.91 from the v02/v03 fixture
benchmarks, `docs/benchmarks/2026-09-27-threshold-sweep.md` — itself
5 TP / 1 FP, hence the tolerant Gate 4, r7-m2); H4 simplicity — the
reason string is asserted in
`tests/test_triage_and_failreason.py:147,152` and
`tests/test_score_corpus.py:97`.

## Mechanism (file:line)

- `package_hunks(diff)` (`:439–697`): parse + cluster + window in one
  function; `CTX = 4` local (`:456`); contiguous ±/− runs form clusters
  (`:604–611`); cluster `size` counts rendered lines including `-`.
  A cluster's only context is ±CTX at its **two outer edges**
  (`:622–627`); E2 (`:613–617`) forbids neighbouring changed lines from
  appearing as context — there is no interior context to hand a
  window cut (r8-M2).
- **Model output has no line locations (r6-M1):** `HUNK_QUESTIONS`
  (`:724–748`) returns one severity / is_real / category per hunk
  state; a window's finding span is the whole window.
- **Model state has no read-only region (r7-M1):** `hunk_state()`
  (`:892–909`) sends only `code_before_change` / `code_after_change`;
  context lines go into both (`:899–901`). A `+` line emitted as
  context would falsely tell the model it pre-existed — which is why
  interior windows get **zero** context (Approach A) and the rev-6
  overlap idea is withdrawn.
- **Transport:** `_get_conn()` (`:130–135`) is a single global
  keep-alive `HTTPSConnection` to Jev — not sqlite (r1 claim,
  withdrawn). `_drop_conn()` (`:138–145`) mutates the shared global;
  `http.client` connections are not thread-safe. `laya` uses one local
  router per process (`:204`) — **concurrency applies to Jev only;
  laya serial.**
- `main`: kept hunks sorted largest-first, truncated to `--max-hunks`
  (default 40, `:1282`, `:1309–1311`); unjudged kept-hunks downgrade to
  `(incomplete review — X of Y clusters judged)` (`:1326–1335`);
  `render()` maps any verdict containing `"(incomplete"` to a last line
  of `Incomplete` (`:1263–1264`) — a documented grep-ledger interface
  (`docs/evals/2026-09-28-field-evals-cj-prs.md:163`, tested
  `tests/test_package.py:529–546`); `render()` prints
  `hunk["lines"][:6]` (`:1234`), so window previews must lead with the
  window's own changed lines. `log_run` (`:1382–1395`) currently logs
  **none of** `n_dropped`, `n_unjudged`, `n_size_skipped_code` — the
  counts gate_run needs (r8-M5). Size-skips sit inside `n_triaged`
  (`:1308`) and `judge_pr_level` (`:1037–1044`) never sees them.
- **Rewrite clusters (r4-M3):** a large rewrite is one cluster; naive
  size windows can produce a (near-)all-`-` window, routed by inherited
  `change_type="code-change"` to `HUNK_QUESTIONS` — the pairing
  `:766–769` documents as over-scoring pure removals to BLOCKER.
- Deletion clusters: deletion rubric over-scores (`:766–776`);
  `references_remaining` empty for whole-file deletions (`:834–835`);
  in `compose()` (`:1100–1105`) same-file code-change findings
  corroborate deletion findings — sub-ratio windows must therefore
  **never** be routed to `DELETION_QUESTIONS` (r8-M3), and they would
  pollute `field_fp`'s deletion bucket driving `sweep_field`
  KEEP/RAISE (`:475–481`).
- Replay/sweep: `score_corpus.replay_indices` (`:54–58`) and
  `sweep-thresholds.rewrap()` (`:170–174`) keep only `file, line,
  is_real, severity, category, rubric, references_remaining`;
  `cluster_matched`/`classify_miss` use `_covers` over the judged
  entry's own `line_start`/`line_end` (`score_corpus.py:49–51, 100`),
  fed from `**_span(f["hunk"])` (`:1340`) — spans on judged entries
  must therefore stay **window-level** (r8-M6). `compose()` accepts
  `skipped` but never reads it; matched goldens leave `misses`
  entirely; `anchor-offset` is its own bucket.
- **Sweep gating:** `gate_run` (`:88–100`) rejects any verdict
  containing `"(incomplete"` and requires `len(judged) == n_analyzed`;
  `select_field_runs` calls it at `:401` without `try/except
  SystemExit` and requires exactly one run per PR (`:409–411`) — one
  gated run kills the whole field sweep; CJ #43 is a field golden
  recorded as defect-free at merge (`examples/cj-field-goldens.tsv`
  rows 4, 18: expected issues 0), so every finding A adds on
  `importMachine.ts` is a *reported* field FP — it does **not** drive
  `sweep_field` KEEP/RAISE, which reads `deletion_total` alone
  (`:479–481`); code-rubric FPs appear only in a `note:` line
  (`:511–515`), and A's windows stay code-rubric (r9-m1).
  `eval_negative` (`:1139–1148`) counts every reported
  finding, as does the precision denominator (`:1186`).

## Architectural approaches

**Step 0′ — verdict honesty for size-skips (ships first, ONE commit
with the gate_run change — r5-M2).**
`n_size_skipped_code` joins the downgrade trigger and the denominator,
never the numerator (trigger `:1333` becomes `n_unjudged or n_dropped
or n_size_skipped_code > 0`; `sor_7_final` reads "12 of 20"). Deletion
size-skips do not count (Kurt-decision 3). **This counter is interim**
(r6-m5): once A ships, cap remainders become *partially judged* with
their own counters and `n_size_skipped_code` is retired.
Implementation: carry `change_type` into skip records; add the
`base_verdict` ledger field; **add `n_dropped`, `n_unjudged`,
`n_size_skipped_code` to `log_run` (`:1382–1395`) in the same commit**
(r8-M5 — `gate_run` must not `rec.get(..., 0)` counts the ledger never
wrote); feed the digest input to `judge_pr_level`. **No
`PACKAGING_VERSION` bump (r6-M4):** fixture hunks are all ≤11 lines, so
no fixture prompt or verdict changes. **Caveat stated (r8-m5):** CJ
#43-style field runs *do* size-skip, so their `judge_pr_level` digest
changes — harmless today because `pr_level` is consumed by neither
`compose()` nor the sweeps; recorded as the justification. Note
(r8-m1): Step 0′ also **raises the reported cluster/hunk counts**
(`code_total_at_shipped`-style report fields); this affects selection
only if windows were deletion-rubric — under Approach A's rules below
they never are.
**Consumers:** `gate_run` keys on `base_verdict` plus explicit counts —
still rejecting `n_dropped > 0` / `n_unjudged > 0`, **admitting
`n_size_skipped_code` only**; **a ledger with `base_verdict` but
missing any of those counts is malformed → die** (never default to 0);
fallback to the suffix check for legacy ledgers lacking
`base_verdict`. This covers `select_field_runs` (no try/except is
added — that would conflict with the exactly-one-per-PR rule; the
point is gate_run no longer *dies* on size-skip-only runs). Retires
the suffixed string as an API. `score_corpus.py:112` needs no change
(compares replayed `compose()` output). **Known cost, explicit
(r6-M3, Kurt-decision 7):** after Step 0′, every run with a
size-skipped code cluster — 54 of 108 corpus ledgers, **including
"Changes requested" ones** — ends its grep-able last line `Incomplete`
until A ships. Mitigation: last-line consumers (e.g. the shadow
tally) read the `Verdict:` line or the JSON `base_verdict`; new test
asserts a size-skip-only "Changes requested" keeps its base verdict
machine-readable in the JSON.

**A. Bounded chunked windows (Kurt's loop instinct — the lead
approach):**
split oversize **code-change** clusters only (51/52 observed), into
≤120-line windows.

- **Window partition (r8-M2, exact):** windows are non-overlapping;
  each `+`/`-` line is judged in exactly one window. **Interior window
  edges carry ZERO context** — a cluster by construction is a
  contiguous run of changed lines with no interior context to give
  (`:604–627`), and emitting a neighbour's `+` lines either double-
  judges them (as `+`) or falsifies history (as context, landing in
  `code_before_change` via `:899–901`). Only the **source cluster's
  two outer edges** keep the existing ±CTX=4. Boundaries prefer
  blank/dedent lines where the language allows; hard cut at 120
  (cluster-context included) as universal fallback. Tests: no entry
  appears in two windows; **no `+`/`-` entry appears with kind `" "`**;
  rendered previews (`:1234`) lead with the window's own changed
  lines.
- **Sub-ratio windows & rewrite alignment (r8-M3, r11-M1, r12-m3 —
  final):** **before cutting a cluster into windows, align its
  deletion and insertion lines: proportional pairing over the
  cluster's `-`/`+` sub-runs in diff order** (a cluster is any
  interleaving of adjacent `-`/`+` runs, `:606` — not necessarily one
  block of each; git's rewrite shape is all-`-` then all-`+`).
  `difflib.SequenceMatcher` is at most an optional character-ratio
  refinement — at line level it finds almost nothing, because equal
  lines were already pulled out as context (`:604–611`). Each window
  then carries old lines alongside their replacements, and no window
  shows a removal without its replacement (the `:766–769` over-scoring
  shape). A sub-ratio `-` run smaller than its window's budget merges
  into the adjacent `+` window (attached `-` lines count toward the
  120-line budget). **Under pure proportional pairing every `-` line
  is placeable; "unplaceable" is reached only through the
  Kurt-decision 6 ratio floor** (a window whose placement would fall
  below the minimum `+`-line ratio). Unplaceable is per-window
  (partly-judged clusters possible), so the bucket precedence is
  reachable. Unplaceable clusters are **not** sent to
  `DELETION_QUESTIONS` (which would revive the #45 over-scoring via
  `:1118–1137` corroboration and pollute the `field_fp` deletion
  bucket). **Windows inherit `code-change` from their source cluster —
  `change_type` is NOT recomputed per window (rev 19 amendment):** a
  recomputed zero-`+` window would become deletion-shaped and route to
  `DELETION_QUESTIONS` (forbidden above), while forcing it through
  `HUNK_QUESTIONS` as a pure removal recreates the `:766–769`
  over-scoring shape; inheritance keeps every window on the paired
  code path, and the ratio floor — not reclassification — is the
  mechanism for hopeless windows. Tests: a
  200`-`/200`+` rewrite yields paired windows, no `-`-only window, and
  no window showing a removal without its replacement; the ratio-floor
  case downgrades honestly instead of misrouting.
- **Ledger counts (r8-M4/M5, r9-M1, r10-M1, r11-M2 — per-cluster
  records checked against an independently computed count):** before
  any scheduling, `triage()`'s `too_large` **code-change** clusters are
  counted into **`n_oversize_code`** (its own ledger name — defined
  independently of the records, so a bug that drops a record cannot
  shrink both sides of the check). Each oversize cluster then logs a
  **named ledger field** of per-cluster records
  **`window_records: [{source_cluster, bucket, windows_scheduled,
  windows_judged}]`**, `bucket ∈ {full, partial_cap, unplaceable,
  failed}`, precedence **failed > unplaceable > partial_cap > full**
  (reachable: `unplaceable` is per-window sub-range, so a cluster can
  be partly placeable AND partly failed). A **window parse error
  counts as a window failure**. Run-level: `n_analyzed` keeps today's
  meaning (`len(kept)`, `:1354`/`:1214`/`sweep-thresholds:88–93`) —
  NOT redefined; plus `n_failed_windows` (windows, informational),
  `n_windowed_failed` (clusters — **the one `gate_run` rejects on**),
  and `n_windows`. **`n_windowed_unplaceable` / `n_windowed_partial_cap`
  are run-level sums derived from `window_records[*].bucket`
  (r12-m2).** **`gate_run` completeness (new ledgers): ordinary
  judged entries (excluding `windowed: true` entries — a filter
  change to the existing `len(judged)` comparison, r12-m6) ==
  `n_analyzed`** (unchanged) **AND `window_records` has exactly one
  record per `source_cluster` AND that record count ==
  `n_oversize_code` AND the buckets sum to it** (nothing silently
  vanishes — a dropped record now breaks the equality because the
  right side is computed before scheduling; a test where a deliberately
  dropped record fails the check). `gate_run` **rejects
  `n_windowed_failed > 0`, admits cap-only partials and
  unplaceables** (both honest degradation; each joins the downgrade
  trigger). **Downgrade trigger and denominator after A (r11-m3,
  r12-m8, one expression each): `trigger = n_unjudged or n_dropped or
  any(window_records[*].bucket != "full")`; denominator =
  `len(hunks) - n_triaged + n_oversize_code`; numerator =
  `len(kept) - n_unjudged + #{bucket == "full"}`.** Oversize
  judged entries are marked **`windowed: true` + `window_index`** so
  mixed runs are distinguishable (r10-m3). **Oversize clusters leave
  the `skipped` list when fully judged; a skip record with a new
  reason (`window-cap` / `unplaceable`) is kept only for unjudged
  windows — this keeps `render()`'s triage line (`:1245–1256`), the
  header `skipped=` count (`:1215`), and `classify_miss`'s
  skipped-triage bucket (`:71–74`) honest (r12-m7). **The run header
  gains `windowed={n_oversize_code} clusters/{n_windows} windows`
  alongside `analyzed=`/`model_calls=` so big-PR runs don't read as
  calls doing nothing (`:1214–1217`; header is outside the closed
  last-line grep set, r13-m3).** Tests: cap cuts a
  cluster partway; cap leaves a whole cluster at zero judged windows; all
  windows of a cluster parse-error; a cluster both partly unplaceable
  and partly failed (precedence); a mixed ordinary+oversize run; an
  ordinary-only run behaves byte-identically to today; a deliberately
  dropped `window_record` fails the completeness check; a mixed run
  passes `gate_run` only after the `windowed: true` filter (r12-m6).
- **The window is the unit of honesty (r5-M1):** any unjudged window
  makes its source cluster *partially judged*, joining the downgrade
  trigger; the verdict numerator counts only fully-judged clusters;
  findings from successful windows are still reported and count
  toward the verdict.
- **Scheduling & order (r7-M3, r8-m3):** oversize source clusters are
  scheduled **outside the `kept`/`--max-hunks` path** — never in the
  largest-first sort, so ordinary clusters can't be pushed into
  `n_dropped`. **Execution order: the ordinary serial loop runs first
  (kept order), then pooled windows run afterward in source-cluster
  order** — deterministic, and it makes `wall_clock_ms` and fail-open
  ordering well-defined.
- **Fail-open under concurrency (r3-m3, r8-m2, r9-M2, r10-M2, r11-M3 —
  precise):** the **ordinary loop keeps today's code unchanged**
  (`CALL_FAIL_LIMIT` consecutive-failure rule `:951/:1017` and the
  all-failed check `:1027`) — an ordinary-only run behaves exactly as
  today. **If the ordinary loop failed open, no windows are scheduled**
  (windows are skipped; the run is `Unavailable` as today). **If the
  ordinary loop succeeded (or `kept` was empty — `judge([])`
  returns `[]`, not `None`, so this check is new code living in
  `judge()`'s caller, stated here): run-level `Unavailable` happens
  only when the ordinary loop judged nothing AND no window
  succeeded.** **The window phase has its own breaker (r11-M3): after
  K consecutive window failures across the pool, stop scheduling
  remaining windows; their clusters land in the `failed` bucket** —
  a dead provider costs at most **≤2·(K + pool − 1) requests**, the
  ×2 being `jev_ask`'s EXISTING single retry on 5xx/transport/parse
  errors (`:183`, `:189–192`) — now also on 429; dropping the 429
  retry would NOT halve the bound. Worst-case wall clock for the
  window phase ≈ ⌈(K+pool−1)/pool⌉ · 2 · 15 s (per-call timeout,
  `:134`) — an input to Kurt-decision 8 (r13-m2). **K reuses
  `CALL_FAIL_LIMIT` (`:51`); "consecutive" includes parse errors
  (a window parse error is a window failure) and is defined in
  completion order, which can vary between repeats — clusters landed
  in `failed` by the breaker are therefore excluded from Gate 6's
  repeat-variance check.** Window failures — transport OR parse —
  feed **`n_failed_windows`** (windows) and the per-cluster
  `window_records`; they never touch the ordinary loop's
  `failures`/`parse_failures` counters. **429 retry (r11-m1, r12-m5):**
  `_NoRetry` gains a `status` attribute; the single backoff retry
  fires only on `status == 429` — other 4xx keep today's exactly-one-
  request contract; the `_NoRetry` docstring (`:152–153`) is amended
  and `tests/test_package.py:515`'s table gains `(429, 2)` alongside
  an unchanged `(401, 1)`. `--serial-windows` forces `pool_size=1`
  (windows are still judged, only serially — it does NOT restore
  today's no-windowing behavior; rev 19 wording fix). Thread-local
  `HTTPSConnection` per worker —
  **including `_drop_conn()`, which must close the worker's own
  connection, never the shared global (`:138–145`)** (`_get_conn()`
  is a shared global today, `:130–145`); laya serial; only
  oversize-cluster windows join the pool. Results placed back in
  input order.
- **Spans (r8-M6):** `line_start`/`line_end` on hunks and judged
  entries stay **window-level**; the source cluster's span lives only
  under `source_cluster` — otherwise one window finding "covers" every
  golden in the cluster and Gate 2 becomes gameable via `_covers`
  (`score_corpus.py:49–51, 100`). Test: a finding in window 1 does not
  cover a golden in window 3.
- **Corroboration containment (r12-M1, Kurt-decision 9):** in
  `compose()`, `corroboration_pool` (`:1107–1108`) holds every reported
  code-rubric finding, and a same-file finding of any non-style
  category at ANY severity corroborates a deletion finding
  (`:1102–1104`) — once A ships, windowed `HUNK_QUESTIONS` findings
  join that pool, so one sev-1 `logic` window finding can unlock a
  report-only deletion finding into a BLOCKER/MAJOR (`:1114–1119`) and
  flip the verdict: the #45 shape returning from the other side.
  **Rule: `windowed: true` findings are EXCLUDED from
  `corroboration_pool`** (option a — the conservative choice; option
  b, sev ≥2-only corroboration, is the alternative if Kurt prefers
  recall). Test: a same-file sev-1 window finding must not unlock a
  deletion finding. **Gate 3's reported costs gain "verdicts flipped
  by window-sourced corroboration"** (corroboration changes the
  verdict, not `reported`, so neither `sweep_field` nor the FP
  gate sees it).
- **Grouping & verdict:** `compose()` groups by `source_cluster`;
  verdict counts each source cluster once (Kurt-decision 4 for the
  two-majors case). Every gate-passing window finding is reported;
  cluster verdict-severity = most severe gate-passing window.
  Per-window prompts carry a window-local anchor.
- **Replay/sweep:** `rewrap()` (`:170–174`) carries `source_cluster` +
  window span (legacy default: each entry its own cluster — **the same
  default applies to ordinary judged entries in new ledgers, which also
  carry `source_cluster` = their own id, so the distinct-cluster count
  is defined for mixed runs, r9-m4**), rewrap→compose round-trip test,
  replay==live test.
- **One `PACKAGING_VERSION` bump, in A** (r6-M4): new tag in
  `RUBRIC_VERSIONS` (`sweep-thresholds.py:41`), `--packaging-version`
  default (`:535`), the `"v03b"` defaults on
  `gate_run`/`select_runs`/`select_field_runs` (`:72`, `:123`,
  `:383`), **≥3 fresh fixture runs per fixture AND fresh CJ field
  runs (one per PR) at the new version** before the gates below are
  evaluable (`:141–143`). The bump is required: windowed prompts are a
  prompt-shape change — the H3 concern — even though fixtures
  themselves never chunk.

**B. Two-pass summarize (fallback):** structural pass compresses the
oversize hunk, then a scored pass on the outline. Different input
shape than calibration (H3), exact lines lost; own version bump and
fixture re-validation. Not the lead.

**C. Raise/eliminate the limit (rejected):** unmeasured H1/H3 risk,
regresses fixture-by-design behavior.

## Latency budget (honest version)

**Time policy (Kurt ruling, 2026-10-01): no fixed wall-clock limit —
the budget scales with the length of the review task**
(Kurt-decision 10). Concretely: run time = windows × ≈165 ms/call, so
it already grows linearly with PR size; the per-run window cap is the
budget and exceeding it degrades honestly (partial, never abort); the
per-call 15 s timeout (`:134`) and the window breaker bound worst-case
behavior; `wall_clock_ms` in the ledger keeps the reporting honest.

Measured today: median 1.4 s, max 7.1 s (`total_latency_ms`, not
wall-clock), 165–300 ms/call. Chunking `sor_7_final`'s 8 clusters:
**≥3.3 s serial; upper bound unmeasured** (full 120-line windows are
larger inputs than the per-call band was measured on); ordinary
clusters stay serial and run first, so only the oversize tail pays.
The spec reports measured `wall_clock_ms` before vs after; pool size
set by the Jev policy answer, not assumed throughput. Levers: bounded
pool + a per-run window cap whose remainder lands its clusters in
`n_windowed_partial_cap` so a huge PR degrades honestly rather than
slowly. README states the wall-clock baseline as a *reporting*
number, not a kill switch; `wall_clock_ms` enters the ledger.

## Validation gates (strict)

1. **Before/after are back-to-back LIVE `run_corpus` passes of the
   current build**, same repeats, same day — minimizing
   unpinned-`jev-latest` drift (`:159`); pinning preferred if Kurt
   approves.
2. **None of the 24 (all code-change, exact) remain in
   `skipped-triage` or `not-judged`** — evaluated at a **per-run**
   window cap **≥ the maximum per-run total window count over the
   corpus measured in Gate 7** (r8-M1 — a per-cluster bound does not
   protect a per-run cap); matched goldens leave `misses` entirely
   (`anchor-offset` is its own bucket) — **and cluster recall
   increases**; strict recall must **not drop** and **is not expected
   to rise materially** (window anchors are new, so a golden within
   ±1 of one can newly match, `:1175` — stated so a flat strict
   number is not misread as failure, r8-m4 softened by r11-m4).
3. **FP gate on the right denominator (r6-M2), with hard numbers
   (rev 18 — resolves the CodeRabbit/Gemini "undefined tolerance"
   blocker):** derived from the baseline ledgers — clean sample-repeats
   judge a mean of **14.2 clusters** each (median 7.5), and
   `fp_per_clean` = 2.98, so the **ordinary per-cluster FP rate is
   ≈0.21**. The gate: **windowed clusters' FP rate (FPs attributed to
   windowed clusters ÷ windowed clusters judged, on clean samples)
   must be ≤ 1.5 × that ordinary rate (≈0.315)** — the 1.5× band
   allows for first-generation noise on newly judged code while still
   failing a windowing scheme that systematically over-flags. **Hard
   fail above 2× (≈0.42).** "fp_per_clean does not increase" was
   withdrawn at r6-M2 — it would demand zero FPs on all newly judged
   code and fail A by construction. **Reported costs, not gates:** the
   raw per-PR `fp_per_clean` delta, the clean `verdict_accuracy`
   delta, the CJ field FP delta on #43 (`importMachine.ts` + its test
   are newly judged; #43 is recorded defect-free at merge — these are
   *reported* field FPs that do **not** drive `sweep_field`
   KEEP/RAISE, which reads `deletion_total` alone (`:479–481`);
   code-rubric FPs appear only in a `note:` line (`:511–515`), and
   A's windows stay code-rubric — r7-m3 corrected by r9-m1), and
   "verdicts flipped by window-sourced corroboration" (r12-M1).
4. Fixture regression (tolerance form, r7-m2): **per-run TP/FP set
   unchanged on ≥2 of 3 fresh runs per fixture** at the new
   `PACKAGING_VERSION` (exact-F1 is fragile: 0.91 = 5 TP / 1 FP);
   new test asserts no hunk in the **built** fixtures is `too_large`
   (max 11/9).
5. Step 0′ check independent of replay: unit test on the
   trigger/denominator; live check that a size-skipping run's verdict
   carries the incomplete suffix and its JSON keeps `base_verdict`
   machine-readable; `gate_run` admits such runs while rejecting
   `n_dropped`/`n_unjudged`; **a truncated run with `base_verdict`
   set but missing counts is rejected as malformed** (r8-M5);
   **a legacy v03b size-skip run with neither `base_verdict` nor the
   suffix is still admitted** (the two admission paths are
   intentionally coexisting — stated on purpose, r9-m3).
6. Determinism: repeat-variance unchanged; **replay verdict == shipped
   `base_verdict`** on all sample-repeats. New tests: 300-line rewrite
   → no `-`-only/sub-ratio window; **every changed line judged in
   exactly one window; no `+`/`-` entry rendered with kind `" "`**;
   `gate_run` completeness via the per-cluster records (ordinary
   judged == `n_analyzed`; one record per `source_cluster`; bucket
   sums == `n_oversize_code`),
   incl. the zero-judged-window and parse-error cluster cases and a
   mixed ordinary+oversize run; rewrap→compose round-trip;
   `gate_run` rejects `n_windowed_failed > 0` and admits
   cap-only partials and unplaceables; window preview leads with
   changed lines; **a window-1 finding does not cover a window-3
   golden**.
7. Spec-time measurement (before window counts and the Gate 2 cap
   finalize): live `package_hunks` pass over the corpus PR diffs for
   the insertion-vs-rewrite split, true window counts, and the
   **maximum per-run total window count** (deletion share ≤1/52;
   golden target exact: 24/24 code-change).

## Kurt-decisions for the spec

1. Architecture: A (bounded chunked windows) vs B (summarize).
   Recommendation: **A**, Step 0′ + `gate_run` change as one commit.
   **RULED (2026-10-01): A.** Step 0′ first.
2. Per-run window cap value (Gate 2 requires cap ≥ Gate 7's measured
   per-run max) — or pool-only with no cap.
   **RULED (2026-10-01, via Gemini review): cap = 2× the maximum
   per-run window count measured in Gate 7** — guarantees zero
   regression on existing corpus PRs with headroom for outliers.
3. Deletion clusters over 120 lines: stay skipped (current scoping;
   ≤1/52 observed, holds 0 goldens) or bounded treatment later.
   **RULED (2026-10-01): stay skipped.**
4. Two gate-passing MAJOR windows in one source cluster: 1 or 2
   toward the `len(majors) >= 2` verdict flip (guard-band option:
   escalate the cluster, not the verdict, and say so in the report).
   **RULED (2026-10-01, second batch): guard-band** — escalate the
   cluster's severity, do NOT flip the verdict on one cluster alone;
   the report says so.
5. Jev concurrency/rate-limit policy (pool 2 default until answered).
   **RULED (2026-10-01): pool 2, conservative** (limits remain
   undocumented; revisit only if the breaker trips in practice).
6. Minimum `+`-line ratio for `HUNK_QUESTIONS` windows (rewrite
   guard); value TBD in spec. **RULED (2026-10-01, second batch):
   pinned by measurement during implementation** (spec-time Gate-7
   data decides the value; recorded as a spec parameter with its
   derivation).
7. Accept the interim last-line `Incomplete` signal loss (≤54 of 108
   ledgers, incl. "Changes requested" runs) between Step 0′ and A,
   with consumers moved to `Verdict:`/`base_verdict` — or pull A's
   windowing forward into the same delivery.
   **RULED (2026-10-01, second batch): accept the interim loss** —
   consumers (incl. the shadow tally) migrate to the structured
   `base_verdict` JSON, which heavily mitigates the grep breakage.
8. **Wall-clock latency budget** (r9-m2): the README number (p95
   wall-clock per run) and the allowed post-A increase (e.g. p95
   delta ≤ N ms measured by Gate 1's before/after passes) — without
   this the latency gate cannot fail. **RULED (2026-10-01, second
   batch): the p95 baseline number is pinned by actual measurements
   during implementation** (Decision 10 already makes it a reporting
   baseline, not a gate; the implementation-phase before/after passes
   produce the number for the README).
9. **Window corroboration policy (RULED 2026-10-01): exclude
   `windowed: true` findings from `corroboration_pool`** (the
   conservative option a; the #45-revival risk is not worth the
   recall).
10. **Time policy (KURT RULING 2026-10-01, Discord): no fixed global
    wall-clock timeout; the review budget scales with review size.**
    Workable because run time is already length-proportional by
    construction (windows × per-call): (a) there is deliberately NO
    global timeout that aborts a run — the only timeouts are the
    per-call 15 s network timeout (`:134`) and the window-phase
    breaker; (b) the per-run window cap (decision 2) is set
    generously and IS the length-proportional budget — exceeding it
    degrades through the honest path (remaining windows unjudged →
    partially judged → incomplete verdict), never a mid-run kill;
    (c) `wall_clock_ms` is logged per run so the README p95 number
    stays a *reporting* baseline, not a kill switch; (d) long PRs
    should be fully reviewed whenever the window budget allows — a
    hard time cap that truncates review regardless of progress is
    explicitly rejected. If a future hard wall-clock cap is ever
    wanted, it must degrade through the same honest partial path,
    never abort.

## Verification performed (rev 19)

- Rev 19 also amends the Step 0′ field plan (r8-MINOR-1): after A
  ships, the ledger KEEPS writing `n_size_skipped_code` with its
  current expression, structurally 0 on non-fail-open runs — written
  for schema stability only (option B, plan rev 4); the word
  "retired" in the Step 0′ section above means "retired from the
  verdict arithmetic" (the spec's three trigger/denominator/numerator
  expressions never mention it), not "removed from the ledger".

- All r1–r8 file:line claims re-verified on this branch; the r1
  "sqlite" error, rev-3 wrong-fixture error, rev-4 `score_corpus:112`
  claim, rev-5 "≥1 window ⇒ judged" clause, and rev-6 span-dedup,
  overlap-context, and rev-7 "CTX at every window edge" designs are
  each corrected or withdrawn above.
- Golden attribution exact: 24 size-skip instances, **24/24 in
  code-change clusters**, 0 in the deletion-shaped one (scorer's own
  `classify_miss` + `_covers` + covering-skip spans, 108 ledgers).
- Deletion-shaped count stated as an upper bound (r7-m5).
- Fixtures rebuilt (SHA-verified), measured via `package_hunks`.
- Denominators: 36 × 3 = 108 ledgers; 198 skip records / 54 ledgers /
  52 clusters (51 code-change by the span argument).
- Jev rate limits: not found in repo docs or vault — open decision,
  not guessed. Baseline carries an explicit re-run instruction.
