# Approach A: Bounded Chunked Windows — Implementation Plan

> **STATUS: SUPERSEDED by `docs/superpowers/investigations/2026-10-01-architecture-ast-batching-brief.md` (rev 6, 2026-10-02).**
> The architecture brief cancels the window-cutting core of this plan: Step 0′ + honest-verdict + Gate-3 framework survive, but the bounded-window work below is replaced by Arch 2 (AST-grouped units, per-cluster transport + AST context enrichment, per-file batching downgraded to G-B-gated). Tasks 0′–1 (windowing unit) and Tasks 2–6 (triage / pooled judge / compose / ledger / sweep gate) DO NOT land as written; the doc carries the full text for traceability only. The only steps that still execute as-is are the investigation-doc Step 0′ patch (already merged at `d2a981e`) and the architectural plan the brief owns. Rev 8 is the final revision of this plan.
>
> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
>
> **GATE-3 UNIT — PENDING KURT RULING (r8 BLOCKER-1, 2026-10-01).**
> The 0.21 baseline is FPs per MODEL CALL (1 call = 1 cluster, 1:1
> enforced). A windowed cluster costs W ≥ 2 calls, so an implementation
> at exact parity scores 0.21×W̄ — at W̄=2 that IS the 0.42 hard-fail
> line. Gate 3 as written fails by construction (the r6-M2 class of
> mistake again). Task 0′ gains: report W̄ (mean windows per oversize
> cluster on clean samples) and the expected parity rate 0.21×W̄.
> Options: **(a)** keep 0.315/0.42, denominator = windows judged
> (recommended — measures in the baseline's own unit); **(b)** keep
> the per-cluster denominator, scale thresholds by W̄. Until ruled,
> Task 6b implements the mechanism with the unit as a named constant;
> Task 9 does not run.
>
> **Rev 8** — revised per Opus plan review round 7 (02d7c462, REQUEST
> CHANGES): r7-MAJOR-1 Gate-3 numerator pinned to the windowed subset's
> count of `blocker_major + other_fp` FINDINGS (the clusters-with-FP
> reading caps the rate at 1.0/cluster and hides over-flagging; that
> ratio kept as context only); r7-MAJOR-2 aggregation pinned to the
> POOLED ratio Σfp ÷ Σclusters over all clean sample-repeats
> (per-sample rate = None on zero denominator; two-sample straddle
> test).
>
> **Rev 7** — revised per Opus plan review round 6 (8b327aba, REQUEST
> CHANGES): r6-MAJOR-1 window-field gate requirements version-scoped
> via `WINDOWING_VERSIONS = {"v04-windowing"}` (v03b records and
> `--packaging-version v03b` sweeps keep working; suite never red);
> r6-MAJOR-2 Gate-3 denominator restored to the SPEC's ruled
> per-cluster definition (my per-window unit would have loosened the
> 0.315/0.42 thresholds ~3–5×; per-window rate kept as reported
> context only); minors: `windowed_fp` pinned to the
> `eval_negative(reported)` `blocker_major + other_fp` basis (m1),
> `_variance` exclusion reworked to the between-repeats mechanism
> (m2), scored repeats require `n_windowed_failed == 0` with re-run
> (m3), 429-backoff-included-in-latency noted in eval doc (m4).
>
> **Rev 6** — revised per Opus plan review round 5 (943dc0e6, REQUEST
> CHANGES): r5-MAJOR-1 gate fields written AND required (Task 5 emits
> `n_windowed_failed`/`n_windowed_unplaceable`/`n_windowed_partial_cap`
> from `window_records`; Task 6 requires `n_oversize_code` +
> `window_records` present, no `.get(...,0)` fallback, gate recomputes
> `n_windowed_failed` and dies on disagreement); r5-MAJOR-2
> `test_replay_equals_live_verdict` moved to Task 6 (must include the
> two-MAJOR guard-band case); minors: per-window recomputed fields
> enumerated + asserted (m1), windows outside `--max-hunks` test (m2),
> window errors collected input-order for `fail_reason` (m3), cites
> fixed (`:766–769`→`:773–776`/`:894–897`, rev 19, `rewrap :176`) (m4),
> placeability checked on ALL goldens up front with holdout caveat (m5),
> no live runs between Tasks 2–7 (m6).
>
> **Rev 5** — revised per Opus plan review round 4 (a28ed2d4, REQUEST
> CHANGES): r4-MAJOR-1 verdict formulas corrected (n_size_skipped_code
> keeps today's expression, schema-stability only, structurally 0
> after A, appears in NO trigger/denominator/numerator expression —
> double-count hazard named; spec's three expressions adopted
> verbatim + cap-truncation denominator test); r4-MAJOR-2 Gate-3
> attribution keyed on `windowed: true` (not `source_cluster`, which
> ordinary findings also carry) and units pinned (FP findings ÷
> windows judged; partial_cap contributes judged windows); minors:
> spec cites → section anchors (m1), caller-list contradiction removed
> (m2), window-phase interim position stated (m3), field ownership
> assigned to Tasks 3/5 (m4), `corroborate_windowed=False` compose
> hook (m5), synthetic replay ledger (m6), fail_open=True + fail_reason
> on the Unavailable path (m7), 250 ms backoff recorded as plan-level
> choice (m8), rewrap carries window span (m9), R derived on train
> split with holdout placeability check (m10), byte-identical carve-out
> for shared transport (m11).
>
> **Rev 4** — revised per Opus plan review round 3 (f28b9038,
> REQUEST CHANGES): r3-MAJOR-1 spec amended to rev 19 (windows
> INHERIT `code-change`, never recomputed — with reasoning recorded
> in the spec itself); r3-MAJOR-2 option B adopted (ledger keeps
> writing `n_size_skipped_code`, simply 0 when nothing size-skips —
> drops the version-dependent gate-field complexity and all
> intermediate-commit hazards); r3-MAJOR-3 all 10 `triage()` test
> call sites listed, the two by-design Step 0′ test rewrites named,
> window judge stubbed in main()-level tests; r3-m1 `_covers`/
> `cluster_matched` is the asserted anti-gaming path (not
> `eval_against_golden`); r3-m2 swapped spec citations fixed;
> r3-m3 `pr_level is None` assertion moved to Task 5; r3-m4 grouping
> fields live at finding level in both `rewrap` and `compose`;
> r3-m5 window failures never enter `findings` (tested); r3-m6 spec
> L381 reworded — `--serial-windows` = serial windows, not
> today's semantics.

**Goal:** Close the `hunk>120 lines` coverage hole in system-one-reviewer: oversize code-change clusters get split into ≤120-line windows that are each model-judged, with honest partial-coverage verdicts, per the approved investigation doc (PR #9, rev 18, all 10 decisions ruled).

**Architecture:** `package_hunks` gains a windowing pass for oversize code-change clusters (proportional −/+ pairing, no overlap, zero interior context). `judge()` gains a pooled concurrent window phase (pool 2, breaker K=CALL_FAIL_LIMIT) after the ordinary serial loop. `compose()` groups window findings by `source_cluster` (verdict counts a cluster once; guard-band for two majors). The ledger gains `n_oversize_code` + per-cluster `window_records` checked by `sweep-thresholds.gate_run`. Windows are excluded from `corroboration_pool` (D9). One `PACKAGING_VERSION` bump with fresh fixture + CJ field runs before the validation gates run.

**Tech Stack:** Python 3.14 stdlib only (no new deps); pytest; the repo's own `score_corpus.py`/`run_corpus.py` for validation.

**Spec:** `docs/superpowers/investigations/2026-10-01-hunk-size-limit-investigation.md` (rev 19) on this branch — the authoritative source for every number cited below. Decisions referenced as D1–D10.

**Baseline (already merged on this branch):** Step 0′ commit `d2a981e` (size-skips count as unjudged; `base_verdict` + counts in ledger; `gate_run` structured path). Suite: 254 passed, 1 skipped.

**Hard constraints from the doc (do not deviate):**
- Windows are non-overlapping; every changed line judged in exactly one window; interior edges carry ZERO context; only the source cluster's outer edges keep ±CTX=4 (`:456`, `:622–627`).
- No `+`/`-` entry may ever be emitted as kind `" "` context (would falsify `code_before_change`, `hunk_state :899–901`).
- Proportional −/+ pairing in diff order; a window never shows a removal without its replacement (over-scoring rationale: code `:773–776` and the `hunk_state` docstring `:894–897` — r5-MINOR-4 corrected the `:766–769` miscite).
- Unplaceable windows come ONLY from the D6 ratio floor; they are NOT routed to `DELETION_QUESTIONS` (`:1118–1137` corroboration + field_fp pollution) — windows keep `change_type: code-change` inherited from the cluster, never recomputed.
- Windows excluded from `corroboration_pool` (D9).
- Ordinary loop stays byte-identical **in loop logic and verdicts** — shared-transport changes (429 retry, thread-local conns in `jev_ask`/`_get_conn`) necessarily touch the ordinary path's request behavior on 429 (r4-m11); "byte-identical" never refers to transport internals. Ordinary clusters serial first; windows pooled afterward in source-cluster order; thread-local connections (including `_drop_conn`, `:130–145`); laya serial.
- Verdict denominator/numerator: denominator `len(hunks) - n_triaged + n_oversize_code`; numerator `len(kept) - n_unjudged + #{bucket=="full"}`; trigger adds `any(window_records[*].bucket != "full")` (r12-m8).
- Oversize clusters leave `skipped` when fully judged; skip records (`window-cap`/`unplaceable` reasons) only for unjudged windows (r12-m7).
- `gate_run`: ordinary judged == `n_analyzed`; one record per source_cluster; bucket sums == `n_oversize_code` (computed BEFORE scheduling); reject `n_windowed_failed > 0`; admit partials/unplaceables (r8-M4, r11-M2).
- Judged entries: window-level spans only (`_span` of the window, never the cluster — r8-M6); `windowed: true` + `window_index`; ordinary entries get `source_cluster` = own id (r9-m4).
- Time policy (D10): no wall-clock cap; the cap is the per-run window cap = 2× Gate-7-measured max (D2).
- `PACKAGING_VERSION` bump in A (one bump, r6-M4): new tag in `RUBRIC_VERSIONS` (`scripts/sweep-thresholds.py:41`), `--packaging-version` default (`:557`), `"v03b"` defaults on `gate_run`/`select_runs`/`select_field_runs` (`:72`, `:145`, `:405`).

---

## Task 0′ (runs AFTER Task 1): Gate-7 measurement pass

**Objective:** Produce the measured numbers later tasks bake in: max per-run window count (→ D2 cap via Task 2's flag), per-cluster window counts, insertion-vs-rewrite split, and the **D6 ratio floor value with its derivation** (M1): e.g. R = (lowest `+`-share among measured clusters that hold goldens) − 0.05 margin, clamped to [0.1, 0.3]; the derivation must be written down.

**Depends on:** Task 1 (imports `window_cluster`).

**Files:** Create: `docs/evals/2026-10-02-gate7-window-measurements.md` (results only; scratch script in /tmp).

**Steps:**
1. Read-only script: for each corpus PR diff (shallow clone as needed), run `package_hunks`, select `too_large` code-change clusters, run `window_cluster` with the measured ratio candidates, report: per-cluster window counts, **max per-RUN total**, **W̄ = mean windows per oversize cluster on clean samples + expected Gate-3 parity rate 0.21×W̄ (r8 BLOCKER-1)**, rewrite/insertion split, per-cluster `+`-share distribution.
2. Derive R per the rule above; record R + derivation + the **cap = 2× max per-run window count** (D2). **Placeability check (r2-m1, reworked r5-MINOR-5, CodeRabbit r4-MINOR-1): placeability is a structural property, not a scored outcome — verify up front that ALL TRAINING golden clusters remain placeable under the chosen R (including per-window rounding), and say so openly; the [0.1, 0.3] clamp's lower bound is ADVISORY — if the check fails, lower R below 0.1 and record the adjustment. Holdout goldens are NOT used to drive R: their placeability is reported as a structural observation, and any unplaceable holdout cluster is a Gate-2 fail (it counts toward the 24-golden rescue target's complement), not a reason to retune R. The earlier "one-way fit to the holdout" caveat leaked evaluation data into threshold selection and is retired; an independent fresh holdout (or a held-out subset of the v06-postmerge corpus) is what Gate 2 measures against.** Without this, Gate 2 fails by construction.
3. Commit: `docs(eval): Gate-7 window measurements — cap <N>, ratio floor <R> (derivation included)`.

**Verification:** eval doc states cap and R; later tasks import these as defaults.

---

## Task 1: Windowing unit — pure function `window_cluster()`

**Objective:** Split one oversize code-change cluster into ≤120-line windows per the doc's partition rules. Pure function: cluster in, list of window dicts out. No I/O, no model calls.

**Files:**
- Modify: `system_one_reviewer.py` (new function after `package_hunks`, ~line 698)
- Test: `tests/test_windowing.py` (new file)

**Steps:**
1. **Failing tests first** (`tests/test_windowing.py`):
   - `test_insertion_split_exact`: 300 `+` lines → 3 windows (120/120/68 rendered incl. the 4+4 outer CTX), sizes all ≤120; union of changed lines == original set; **no line in two windows**.
   - `test_no_plus_minus_as_context`: for every window, no entry with kind `" "` carries text equal to a `+`/`-` line of the cluster (the r8-M2 falsified-history invariant).
   - `test_interior_windows_have_zero_context`: middle window's `entries` contain no `" "`-kind lines; first/last windows have CTX=4 only at the cluster's outer edge.
   - `test_rewrite_proportional_pairing`: 200 `-` followed by 200 `+` (diff order) → windows each contain paired `-`/`+`; **no `-`-only window**; every `-` line appears in exactly one window.
   - `test_alternating_runs_pair_in_order`: interleaved `- - + + - - + +` clusters pair proportionally in diff order (r12-m3 generalization).
   - `test_hard_cut_fallback`: a cluster with no blank/dedent break still yields all windows ≤120 including CTX.
   - `test_blank_dedent_preference`: where a blank line exists near the cut, the cut lands there.
   - `test_unplaceable_from_ratio_floor`: with ratio floor R, a window whose `+` share < R is marked unplaceable (per-window flag), not deleted, not routed to deletion rubric. **`ratio_floor` is a REQUIRED parameter (> 0) — no `None` default (r2-M2): with fewer `+` lines than windows, proportional pairing yields zero-`+` windows, and those must ALWAYS come out unplaceable (assert this case explicitly).**
   - **`test_window_type_inherits_code_change` (r2-M2):** every window inherits `code-change` from its source cluster; `change_type` is NEVER recomputed per window — a zero-`+` window must not become `deletion-only` (that would route it to `DELETION_QUESTIONS`, forbidden), and placeable windows go to `HUNK_QUESTIONS` as paired chunks, not the over-scoring all-removal shape.
   - **`test_window_anchors_distinct` (M3):** each window's `line` = its **first `+` entry's tracked line number**, falling back to the first `-` entry's tracked line when a window has no `+`. **Distinctness is asserted across PLACEABLE windows only (r2-M2): deletion-only windows anchor on the block's shared `new_line` and may legitimately collide with the next window's `+` anchor.** Anchor lies within the window's span.
   - **`test_source_cluster_identity_json_native` (M4):** `source_cluster` is the string `f"{file}:{line_start}-{line_end}"` of the **source cluster's** span (identical across all windows of one cluster); `json.dumps`→`loads` round-trips it unchanged; ordinary hunks receive the same-format string built from their own span.
   - `test_determinism`: same input twice → identical output (exact list equality).
2. Run: `.venv/bin/python -m pytest tests/test_windowing.py -q` → FAIL (function missing).
3. Implement `window_cluster(h, max_lines=120, ctx=4, ratio_floor)` — `ratio_floor` required, > 0 (r2-M2) — returning `[{...h-like dict, "line": <window anchor per M3>, "window_index": i, "source_cluster": "<file>:<start>-<end>" per M4, "change_type": inherited "code-change", "unplaceable": bool}]`. **Recomputed per window (r5-MINOR-1): `entries` (the slice — never the whole cluster), `lines`, `size`, `too_large=False`, `n_changed`, `line_start`/`line_end` (span via `e[4]` for `-` entries, the `:661` rule — `e[1]` is the old-file number), `header`, `line`. `test_insertion_split_exact` gains assertions for each: no window's `lines`/`n_changed`/`header` leaks the cluster's totals.** Keep the cluster's outer CTX.
4. Run tests → PASS. Run full suite → 254+green.
5. Commit: `feat(windowing): pure window_cluster() — proportional pairing, zero interior context, ratio floor, JSON-native cluster identity`.

---

## Task 2: Scheduling + oversize accounting in `triage()`/`main()`

**Objective:** Wire windowing into the pipeline: `triage()` classifies oversize code-change clusters as `oversize` (a third bucket, not kept, not skipped-yet); `main()` schedules windows for them, computes `n_oversize_code` BEFORE scheduling, and produces `window_records` + updated `skipped`.

**Files:**
- Modify: `system_one_reviewer.py` (`triage` ~:706; `main` ~:1305–1335)
- Test: `tests/test_windowing.py` (integration-level)

**Steps:**
1. Failing tests:
   - `test_triage_three_way`: oversize code-change cluster → `oversize` bucket (not in kept/skipped); oversize deletion-shaped → skipped with `hunk>120 lines` reason + change_type (Step 0′ path unchanged); ordinary → kept.
   - `test_n_oversize_code_independent`: `n_oversize_code` computed from triage output before scheduling; dropping a window_record must not change it.
   - `test_window_records_shape`: each record `{source_cluster, bucket, windows_scheduled, windows_judged}`; buckets ∈ {full, partial_cap, unplaceable, failed}; precedence failed > unplaceable > partial_cap > full.
   - `test_fully_judged_leaves_skipped`: a fully-judged oversize cluster produces NO skip record; a cap-truncated one produces a `window-cap` skip record for its unjudged windows (r12-m7).
   - **`test_windows_outside_max_hunks` (r5-MINOR-2):** with `--max-hunks 1`, one ordinary + one oversize cluster → `n_dropped == 0` (windows are scheduled OUTSIDE the `kept` sort/truncate path at :1327–1329; appending windows to `kept` would push ordinary clusters into `n_dropped` and `gate_run` would reject the run).
2. Implement: `triage()` returns `(kept, skipped, oversize)` — **note (r2-m9): `n_triaged` becomes `len(hunks) - len(kept)`, i.e. it now counts oversize code clusters too; the verdict denominator `len(hunks) - n_triaged + n_oversize_code` relies on this — add the arithmetic to a test assertion**; `main()` builds windows via `window_cluster`, applies the per-run cap (default from Task 0′'s measured value, overridable via **new `--window-cap` flag**) and the ratio floor (default R from Task 0′, **new `--min-plus-ratio` flag** — M1 wiring; also update the `--help` text), builds `window_records`, and assembles the final `skipped` list per the honesty rules. **(Step 3 below carries the full 10-call-site list; this task's `main()`-level tests stub the window judge.)**
3. Tests → PASS; **Step 0′ test updates (r3-MAJOR-3): `triage()` has 10 test call sites across 3 files — `test_line_span.py:31`; `test_negative.py:32/44/62`; `test_triage_and_failreason.py:64/74/79/136/144` — update ALL to 3-tuple unpacking, not just "four".** Two Step 0′ tests change behavior BY DESIGN and are rewritten here, not "kept passing": `test_triage_size_skip_carries_change_type` (:135 — its oversize code cluster now lands in `oversize`, assert there instead of `skipped`) and `test_main_downgrades_on_size_skipped_code` (:148 — its 150-line cluster now gets windowed; **stub the window judge** (`_judge_windows` or the ask passed to it) so no test hits the real provider/network). Suite green after these rewrites. **NO live runs are logged between this task and Task 7 (r5-MINOR-6): windowed ledgers written before the `PACKAGING_VERSION` bump would be tagged `v03b` and mix into real v03b baselines in `gate_run`/`select_runs` — ad-hoc verification uses `--out /tmp/...` with logging disabled or temp `JEV_REVIEW_STATE` only.**
4. Commit: `feat(windowing): triage three-way split + window scheduling + n_oversize_code before scheduling (+ --window-cap, --min-plus-ratio)`.

---

## Task 3: Pooled concurrent judge phase

**Objective:** Judge windows after the ordinary loop: bounded pool (2), thread-local `HTTPSConnection`, breaker K=CALL_FAIL_LIMIT, results in input order, failures → `n_failed_windows` + cluster buckets, 429-only single backoff retry.

**Files:**
- Modify: `system_one_reviewer.py` (`jev_ask` ~:157, new `_judge_windows()` after `judge` ~:1030; `main` call site)
- Test: `tests/test_windowing.py` + `tests/test_pooled_judge.py` (new)

**Steps:**
1. Failing tests:
   - `test_jev_429_retries_once_then_raises`: stub transport: **429 then 429 → `_NoRetry`; 429 then 500 → `RuntimeError` (the second-attempt non-429 path raises RuntimeError at :183/:191–192, NOT `_NoRetry` — r2-m4); 401/403 still exactly 1 request** (extend `tests/test_package.py:515` table with `(429, 2)` — r12-m5). **Also per spec (`_NoRetry` section): `_NoRetry` gains a `.status` attribute and its docstring documents the retry contract — one 429 retry, 250 ms apart (r4-m8: 250 ms is a plan-level choice; the spec says only "single backoff retry"; recorded here and in the Task 9 eval doc). The test monkeypatches `time.sleep` and asserts it was called once with 0.25 (r8-MINOR-2 — the backoff sits in the shared transport, so every 429-hitting test would otherwise really wait).**
   - `test_thread_local_connections`: two worker threads get distinct connection objects; `_drop_conn` in one does not close the other's (patch `_get_conn` counting constructions).
   - `test_results_in_input_order`: shuffled completion order → output ordered by input index.
   - `test_breaker_stops_scheduling`: 12 windows, K=2: after 2 consecutive failures scheduling stops; **≤ 2·(K+pool−1) requests attempted total (the spec's bound, r13-m4 — no extra `+pool` slack)**; remaining clusters bucket `failed`.
   - `test_window_failures_dont_touch_ordinary_counters`: ordinary loop's `failures`/`parse_failures` unchanged by window failures; run verdict NOT `Unavailable` when ordinary succeeded (r10-M2). **Window failures count ONLY in the ledger field `n_failed_windows` (per-window count), which is distinct from the per-cluster bucket name `n_windowed_failed` used by the gate — both recorded, never conflated (r13-m1).** **Window failures NEVER enter the ordinary `findings` list (r3-m5): `n_unjudged` counts `parse_error` findings (:1354) and `gate_run` rejects `n_unjudged > 0`, so a parse-errored window that leaked into `findings` would fail every gate — asserted here: failed windows appear only in `n_failed_windows` + `window_records`.**
   - **`test_ordinary_failopen_schedules_no_windows` (M2):** ordinary loop fail-open (`fail_open=True`) → zero windows scheduled, all oversize clusters skipped with an explicit reason, no pool threads created.
   - **`test_empty_kept_all_windows_failed_is_unavailable` (M2):** `kept == []` (e.g. the PR's only change is one 491-line file) and every window fails → verdict `Unavailable`, NOT `Approved (incomplete review)`. Implemented at the `main()` call site (new check — `judge([])` returns `([], [])`, so `judge()` itself can't see this). **Also asserts `fail_open=True` + a `fail_reason` are set on this path (r4-m7): without them the ledger shows `fail_open=False` alongside `Unavailable`, render skips the `!!` lines (:1236–1240), and `base_verdict` goes through the wrong split path. `fail_reason` comes from the last window error in INPUT order (r5-MINOR-3 — window errors are collected input-ordered like results; `call_errors[-1]` at :1335 follows completion order and would make ledger diffs nondeterministic under pool 2).** **`pr_level is None` is asserted for this scenario starting in Task 5 (r3-m3): the relocation of `judge_pr_level` after the window phase happens there; in THIS task the assertion is deferred because `judge_pr_level` still runs at :1338 before any window phase exists.**
   - `test_no_windows_no_pool`: an ordinary-only run produces zero extra threads/calls (byte-identical path).
   - `test_laya_serial`: laya provider never opens a pool.
2. Implement `_judge_windows(windows, ask, pool_size=2)` + connection threading; **new `--serial-windows` flag (r2-m5 — it does not exist today, argparse :1291–1313) forcing pool_size=1, with `--help` text; named in this task's commit alongside the flag additions.** **Window-phase position (r4-m3): in THIS task the window phase runs AFTER `judge_pr_level` (which still sits at :1338) — Task 5 relocates the PR-level call after windows; the interim order is stated so no test asserts the wrong sequence. `_judge_windows` reuses `judge()`'s parsing block by refactoring it into a shared helper (touching :966–1027) — the ordinary loop's verdict-relevant behavior stays byte-identical (r4-m11 carve-out below).**
3. Tests → PASS; full suite green.
4. Commit: `feat(windowing): pooled window judge — thread-local conns, breaker K=CALL_FAIL_LIMIT, 429-only retry, fail-open rules`.

---

## Task 4: compose() grouping, guard-band, corroboration exclusion

**Objective:** Verdict semantics: windows grouped by source_cluster; cluster counts once; two gate-passing MAJOR windows in one cluster escalate the cluster but never alone flip the verdict (D4 guard-band); `windowed: true` findings excluded from `corroboration_pool` (D9); findings reported per window (gate-passing ones).

**Files:**
- Modify: `system_one_reviewer.py` (`compose` :1080–1139)
- Test: `tests/test_compose.py` (extend)

**Steps:**
1. Failing tests:
   - **`test_cluster_grouping_changes_request` (r2-m3, replaces `test_cluster_counts_once`):** MINORs never reach the verdict (`compose()` counts level 2+ only, :1130–1138), so a two-MINOR test passes without any grouping logic. Exercise grouping for real: a BLOCKER window + a MAJOR window in the same cluster → `Changes requested` (cluster counted once at max severity); and a MAJOR window + an ordinary MAJOR in a different cluster → `Changes requested` (two distinct groups).
   - `test_guard_band_two_majors`: two MAJOR windows, same cluster, nothing else ⇒ verdict stays `Approved`, BOTH findings reported, cluster severity shows MAJOR (report line says escalated).
   - `test_two_majors_different_clusters_flip`: same two MAJORs in different clusters ⇒ `Changes requested` (the existing rule is untouched across clusters).
   - `test_windowed_findings_dont_corroborate`: same-file sev-1 `logic` window finding + report-only deletion finding ⇒ deletion stays report-only (D9; the r12-M1 scenario).
   - **`test_grouping_windowed_only` (r2-m2):** grouping by `source_cluster` applies ONLY to findings with `windowed: true`; every other finding (including legacy replays) is its own group keyed by object identity — `rewrap()` rebuilds hunks with only `file`/`line` (:192), so legacy entries cannot reconstruct a span-string own-id, and two ordinary clusters' span strings are not guaranteed distinct (a collision would merge two real MAJORs into the guard-band and suppress a `Changes requested`, breaking the byte-identical ordinary path).
   - `test_replay_legacy_default`: a `judged` entry without `source_cluster` behaves as its own cluster (legacy ledgers).
2. Implement in `compose()`: group by `source_cluster` (default = own id); cluster severity = max gate-passing window severity; guard-band escalation flag on the cluster; corroboration pool filter. **Grouping fields are read from the FINDING dict (r3-m4/r4-m4) — and `compose()` gains a sweep-only keyword `corroborate_windowed=False` (r4-m5, following the `deletion_threshold` precedent at :1093–1097): when True, windowed findings join `corroboration_pool`; used ONLY by Task 6b's counterfactual replay, never by production callers.** **Field ownership (r4-m4): `_judge_windows` (Task 3) copies `windowed`/`window_index`/`source_cluster` from the window hunk onto each judge record's finding; the `judged` builder (:1379–1391, Task 5) emits the same three fields into the ledger.**
3. Tests → PASS; full suite green (existing compose tests must pass unchanged).
4. Commit: `feat(windowing): compose groups by source cluster — guard-band D4, corroboration exclusion D9`.

---

## Task 4b (r2-M4): spec-mandated window tests that live in render/coverage/cap paths

**Objective:** The spec requires tests the other tasks don't naturally produce; they get their own task so Gate 6's coverage claim is real.

**Files:**
- Test: `tests/test_windowing.py` + `tests/test_render_windows.py` (new)

**Steps:**
1. Failing tests:
   - `test_window_preview_starts_with_changed_lines` (spec "window report" section; `render()` prints `lines[:6]`, :1252): the rendered preview of a window leads with changed (`-`/`+`) lines, not the 4 leading context lines — adjust `render()` window preview construction so context doesn't push changed lines out of the 6-line preview.
   - `test_window_finding_does_not_cover_distant_golden` (the `_covers` anti-gaming check, spec "_covers" section — r3-m2/r4-m1: cite sections, not line ranges): assert on **`score_corpus._covers` / `cluster_matched`** (`score_corpus.py:49–51`, `:100` — the gameable path, r3-m1), using a v04 judged entry with window-level `line_start`/`line_end`: a window-1 finding's span does NOT cover a golden/cluster anchored in window-3. (An `eval_against_golden` ±1 anchor test alone would pass even with cluster-span spans — the r8-M6 hole.)
    - Cap scenarios (spec "cap scenarios" section — r4-m1 section cites), driven through `main()`'s scheduling with synthetic oversize clusters:
     - `test_cap_cuts_cluster_partway`: first windows judged, tail windows produce `window-cap` skip records.
     - `test_cap_leaves_cluster_zero_judged`: a cluster scheduled after the cap → all its windows skipped, bucket `partial_cap` with `windows_judged == 0`.
     - `test_all_windows_parse_error_buckets_failed`: every window of a cluster parse-errors → bucket `failed`, findings none, `n_failed_windows` counts them.
     - `test_bucket_precedence_partial_failed`: a cluster both partly unplaceable and partly failed → bucket `failed` (precedence failed > unplaceable > partial_cap > full).
     - **`test_replay_equals_live_verdict` moved to Task 6 (r5-MAJOR-2 — it was scheduled here in rev 4, before `rewrap`/`judged` carry the window fields; a two-MAJOR-guard-band run would replay as `Changes requested` and either fail the suite or silently dodge the one case that matters).**
2. Implement the render preview fix; everything else is test-only unless a failure exposes a code bug (fix and note it).
3. Tests → PASS; full suite green.
4. Commit: `test(windowing): spec-mandated preview/coverage/cap/replay tests (r2-M4)`.

---

## Task 5: Ledger fields, render, verdict formulas, and PR-level digest ordering

**Objective:** Everything the doc requires in the output: `n_oversize_code`, `window_records`, `n_windows`, `n_failed_windows`, **`n_windowed_failed`, `n_windowed_unplaceable`, `n_windowed_partial_cap` (r5-MAJOR-1 — run-level fields derived from `window_records`, per the spec's ledger-counts section)**, `wall_clock_ms`; downgrade trigger/denominator/numerator formulas; header `windowed=... clusters/... windows`; **and `judge_pr_level` moved AFTER the window phase with full inputs (M7)**. Also: the `judged` builder (:1379–1391) emits `windowed`/`window_index`/`source_cluster` per finding (r4-m4 field ownership, from Task 4).

**Files:**
- Modify: `system_one_reviewer.py` (`main` result/log_run — result block is at ~:1399; `judge_pr_level` call site ~:1339; `render` header ~:1232, triage line ~:1263; `judge_pr_level` already Step 0′-aware)
- Test: `tests/test_windowing.py` (extend)

**Steps:**
1. Failing tests:
   - `test_trigger_denominator_numerator`: synthetic run with 1 partial cluster → verdict suffix `X of Y` matches `len(kept) - n_unjudged + #full` of `len(hunks) - n_triaged + n_oversize_code` (r12-m8 expressions).
   - `test_wall_clock_logged`: `wall_clock_ms` present, **> 0, and ≥ the ordinary-phase latency** — window latencies DO join `total_latency_ms` (sum of per-call times, spec "reporting baseline" section), but with pool 2 the sum can exceed wall clock, so no `≥ total_latency_ms` assertion (M6).
   - `test_header_windowed_count`: `windowed=N clusters/M windows` appears when oversize exists, absent otherwise (r13-m3).
   - `test_render_skips_line_honest`: judged cluster absent from triage line; unjudged windows appear with `window-cap`/`unplaceable` reasons.
   - **`test_pr_level_after_windows` (M7):** the PR-level call happens after the window phase and its digest receives (a) ordinary findings + window findings, and (b) unjudged lines for `window-cap`/`unplaceable` skip records alongside Step 0′'s `hunk>` ones. Fully-judged oversize clusters contribute findings, not unjudged lines. **Also (r3-m3): `test_empty_kept_all_windows_failed_is_unavailable` from Task 3 is EXTENDED here with the `pr_level is None` assertion — possible now that the PR-level call sits after the window phase.**
2. Implement; keep the closed last-line set untouched (`Incomplete` logic already correct via Step 0′ suffix — D7 accepted). **Step 0′ field note (r3-MAJOR-2 option B, corrected per r4-MAJOR-1):** the ledger KEEPS writing `n_size_skipped_code` **with today's expression at `:1360–1364` UNCHANGED** (records whose reason starts with `hunk>`, excluding `deletion-only`/`whole-file-deleted`) — after A it is structurally 0 on non-fail-open runs (size-skips became windowed clusters; cap/unplaceable records don't match the `hunk>` prefix), and it is written for SCHEMA STABILITY only. **The downgrade trigger and denominator/numerator are replaced with exactly the spec's three expressions (spec "Verdict semantics" section): trigger adds `any(window_records[*].bucket != "full")`; denominator `len(hunks) - n_triaged + n_oversize_code`; numerator `len(kept) - n_unjudged + #{bucket=="full"}` — `n_size_skipped_code` appears in NONE of them** (adding it on top would double-count cap-truncated clusters: today's denominator `:1370` becomes wrong). `gate_run`'s required-field set is untouched — no version-dependent fields, no intermediate-commit hazards. Task 6 version-dependence tests from rev 2 stay DROPPED. Step 0′ downgrade tests updated in Task 2. **New test (r4-MAJOR-1): a cap-truncated run's denominator equals `len(hunks) - n_triaged + n_oversize_code` exactly** (the trigger/denominator/numerator test above asserts this case).
3. Tests → PASS; full suite green.
4. Commit: `feat(windowing): ledger fields + verdict formulas + PR-level digest after window phase`.

---

## Task 6: gate_run completeness for windowed ledgers

**Objective:** Sweep gate accepts windowed runs exactly per the doc: ordinary judged == `n_analyzed`; `window_records` one-per-cluster; bucket sums == `n_oversize_code`; reject `n_windowed_failed > 0`; admit partials/unplaceables; oversize judged entries carry `windowed: true` so the ordinary judged-count filter works (r12-m6).

**Files:**
- Modify: `scripts/sweep-thresholds.py` (`gate_run` ~:72; `rewrap` :176)
- Test: `tests/test_sweep.py` (extend)

**Steps:**
1. Failing tests (**records built with `pv="v04-windowing"` explicitly** — r6-MAJOR-1; pre-windowing records stay as-is):
   - `test_gate_admits_windowed_full_run`: judged = ordinary + windowed entries; records sum == n_oversize_code → admitted.
   - `test_gate_rejects_failed_windows`: `n_windowed_failed > 0` → die.
   - `test_gate_admits_partial_and_unplaceable`: cap-only partial and unplaceable buckets → admitted.
   - `test_gate_rejects_missing_window_record`: record count < `n_oversize_code` → die (the r11-M2 drop-a-record scenario).
   - **`test_gate_rejects_missing_window_fields` (r5-MAJOR-1):** a **v04-windowing** record with `windowed: true` judged entries but NO `window_records` / `n_oversize_code` key → die (missing ≠ 0).
   - **`test_gate_recomputes_windowed_failed` (r5-MAJOR-1):** logged `n_windowed_failed` disagreeing with the count recomputed from `window_records` → die.
   - **`test_gate_v03b_still_admitted` (r6-MAJOR-1):** a v03b `_run0` record (Step 0′ shape, no window fields) is STILL admitted — the window-field requirements apply only to `WINDOWING_VERSIONS = {"v04-windowing"}` (new module constant, `RUBRIC_VERSIONS` pattern), so `--packaging-version v03b` sweeps keep working against the Step 0′ baselines and the suite never goes red at this commit.
   - `test_gate_filters_windowed_from_judged_count`: mixed run where `len(judged)` > `n_analyzed` but ordinary entries == `n_analyzed` → admitted only after the `windowed: true` filter (r12-m6).
   - **`test_replay_equals_live_verdict` (moved here from Task 4b, r5-MAJOR-2; spec "replay" section): generate the ledger synthetically through `main()` with a stubbed `ask` and captured `log_run` (the `test_triage_and_failreason.py:148` pattern — no shipped v04 ledger exists until Task 9, r4-m6)**; the synthetic run MUST include the two-MAJOR-window guard-band case (r5-MAJOR-2). Run `rewrap` on it and assert the replayed verdict string equals the ledger's `base_verdict` — this is the Gate-6 test for the exact grouping path the earlier round-trip test only checks field-wise.
   - `test_rewrap_carries_source_cluster_and_windowed`: round-trip preserves grouping fields at **finding level (r3-m4): both `rewrap` and `compose` read/write `source_cluster` and `windowed` on the FINDING dict (not `f["hunk"]`) — stated here and in Task 4 so live and replay group identically.** **`rewrap` also carries the window span (`line_start`/`line_end`) onto the rewrapped hunk (r4-m9, per the spec's replay section) — `_covers` reads `judged` directly, but the span keeps replay-side span data complete.**
2. Implement the window-record completeness checks (bucket sums vs `n_oversize_code`, one record per cluster, `n_windowed_failed` rejection); **the windowed filter EDITS the existing `len(judged) != n_analyzed` check at `:97–102` in place (r8-MINOR-3 — it runs on every record before any version branch; new checks only inside the v04 branch would let every windowed run die at :98 first)**; **required fields (r5-MAJOR-1, version-scoped per r6-MAJOR-1): new module constant `WINDOWING_VERSIONS = {"v04-windowing"}` — `n_oversize_code` and `window_records` MUST be present (die on absence, NO `.get(..., 0)` fallback) ONLY when `rec["packaging_version"] in WINDOWING_VERSIONS`; pre-windowing records keep exactly the Step 0′ required trio (`n_dropped`/`n_unjudged`/`n_size_skipped_code`), so v03b baselines and `--packaging-version v03b` sweeps keep working. Gate on `n_windowed_failed` RECOMPUTED from `window_records`, dying if it disagrees with the logged run-level field (v04 records).**
3. Tests → PASS; full suite green.
4. Commit: `feat(sweep): gate_run windowed completeness + rewrap finding-level source_cluster`.

---

## Task 6b (M5): scorer extension for Gate 3

**Objective:** Make Gate 3 computable: `score_corpus.py` gains windowed-cluster FP attribution and the corroboration-flip count. Without this, Task 9 has no tool to produce the number it gates on.

**Files:**
- Modify: `scripts/score_corpus.py` (new fields on the per-sample result; no change to existing `clean_fp`/golden fields)
- Test: `tests/test_score_corpus_windowed.py` (new)

**Steps:**
1. Failing tests (synthetic clean-sample ledger with windowed findings):
   - `test_windowed_fp_attribution`: **attribution keys on `windowed: true` (r4-MAJOR-2) — ordinary findings also carry `source_cluster` (their own id, spec's "per-cluster identity" rule), so keying on the field alone would count every FP as windowed.** `windowed_fp` / `windowed_clusters_judged` produced; findings with `windowed` falsy count in the ordinary rate only. **`windowed_fp` = the windowed subset of `eval_negative(reported)`'s `blocker_major + other_fp` (`score_corpus.py:105–107`, via `replay_indices`' `idx`) — the SAME basis as `fp_per_clean`, so minor style notes and unreported severities never enter the numerator (r6-MINOR-1).**
   - **`test_windowed_fp_units` (r4-MAJOR-2, revised r6-MAJOR-2 + r7-MAJOR-1):** the gate follows the SPEC's ruled definition (validation-gates section, rev 19) with BOTH sides pinned to findings/clusters on the same basis as the 0.21 baseline: **numerator = the windowed subset's count of `blocker_major + other_fp` FINDINGS** (r7-MAJOR-1 — the "clusters with ≥1 FP" reading caps the rate at 1.0 per cluster and hides systematic over-flagging across multi-window clusters; the spec's literal text is findings); **denominator = WINDOWED CLUSTERS JUDGED** (r6-MAJOR-2; per-window rejected as ~3–5× looser than the ruled thresholds). `partial_cap` clusters count iff ≥1 window judged. Test: a 3-window cluster with 2 FP windows → `windowed_fp=2`, `windowed_clusters_judged=1`, rate 2.0 (NOT 1.0). **The clusters-with-FP ratio is computed and reported in the Task 9 eval doc as context only.**
   - `test_ordinary_rate_unchanged`: existing `clean_fp`/per-sample fields byte-identical for a legacy (non-windowed) ledger.
   - **`test_corroboration_flip_counterfactual` (r2-M3):** `n_corroboration_flips` is a COUNTERFACTUAL REPLAY metric, not a ledger-provenance read (the ledger records no corroboration provenance, and D9 makes live flips impossible by construction): for each clean sample, run `compose()` twice — **once with `corroborate_windowed=True` (the Task 4 sweep hook)** and once as shipped — and count samples whose verdict differs. The test builds a synthetic case where the counterfactual flips; legacy ledgers yield 0 (no windowed findings to inject).
2. Implement: per clean sample, output `windowed_fp`, `windowed_clusters_judged`, `windowed_fp_rate` (**`None` when the denominator is 0** — most clean samples have 0–1 windowed clusters; r7-MAJOR-2), and `n_corroboration_flips` (counterfactual definition above — it measures what D9 containment actually prevents); **the GATE VALUE is the POOLED ratio Σ`windowed_fp` ÷ Σ`windowed_clusters_judged` over all clean sample-repeats (r7-MAJOR-2 — the same pooled construction as the baseline: 2.98 ÷ 14.2; a mean-of-per-sample-rates would let one 1.0-rate sample outweigh ten clean ones and is NOT used; a two-sample test asserts mean-of-rates and pooled ratio straddle 0.315)**; the summary prints the Gate-3 comparison (pooled windowed rate vs **the same-day ordinary per-cluster rate from Task 9's "before" run** (r2-m10) vs the 0.315/0.42 thresholds from **the spec's Gate-3 section (rev 19)** — the thresholds decide the gate; the same-day rate and the clusters-with-FP ratio are reported next to them for context). **Also (r2-m7, reworked r6-MINOR-2): `score_corpus._variance` (:156–172) excludes windowed entries of any `source_cluster` whose bucket is `failed` in ANY repeat, before comparing — failed windows never reach `judged` within a run (r3-m5), so the mismatch is BETWEEN repeats (repeat A judges cluster X, repeat B fails it; the raw `json.dumps(judged)` differs at :161). Test: synthetic repeat pair where one repeat succeeds and the other fails the same cluster → `identical=True` after exclusion.**
3. Tests → PASS; run the scorer on the Step 0′-era ledgers (no windowed findings) → ordinary numbers unchanged.
4. Commit: `feat(score): windowed-cluster FP attribution + D9 counterfactual flip count + variance exclusion (Gate 3 tooling)`.

---

## Task 7: PACKAGING_VERSION bump + test-suite full green

**Objective:** The one bump (r6-M4): new tag `v04-windowing` end-to-end; suite fully green including the new version defaults.

**Files:**
- Modify: `system_one_reviewer.py` (`PACKAGING_VERSION` at `:71`), `scripts/sweep-thresholds.py` (`RUBRIC_VERSIONS` :41, defaults :72 (gate_run), :145 (select_runs), :405 (select_field_runs), :557 (--packaging-version)), `tests/` version-string assertions (grep `v03b` in tests/)
- Test: full suite

**Steps:**
1. Grep `v03b` across the repo; update the version constant + sweep defaults + test expectations.
2. Full suite → all green (expect >260 tests).
3. Commit: `chore(version): PACKAGING_VERSION v04-windowing — one bump per r6-M4`.

---

## Task 8: Fixture re-validation (≥3 fresh runs per fixture, Gate 4)

**Objective:** Prove fixture behavior is unchanged modulo model noise: per-run TP/FP set unchanged on ≥2 of 3 fresh runs per fixture at the new version (r7-m2 tolerance form); new test asserting no built-fixture hunk is `too_large` (max 11/9).

**Files:**
- Test: `tests/test_windowing.py` (add `test_no_built_fixture_hunk_is_too_large` — rebuild fixtures via `examples/build-fixture.sh`/`build-negative-fixture.sh`, run `package_hunks`, assert no `too_large`)
- Create: `docs/evals/2026-10-02-v04-fixture-rerun.md` (results)

**Steps:**
1. Add + run the too_large assertion test → PASS (deterministic, no model).
2. Run 3× positive + 3× negative fixture runs with the new version (`run_corpus.py` or direct CLI with `--fixture` + `--label v04-fixture-*`).
3. Compare TP/FP sets across runs vs the v03b baseline (`docs/benchmarks/2026-09-27-threshold-sweep.md`); record in the eval doc.
4. Commit: `test(fixture): no built fixture hunk is too_large + v04 rerun results`.

---

## Task 9: Corpus live before/after (Gates 1–3, 5–7)

**Objective:** The main validation: back-to-back live `run_corpus` passes before (current main) and after (this branch, at v04), same repeats, same day. Then the scorer comparisons for every remaining gate.

**Files:**
- Create: `docs/evals/2026-10-02-v04-corpus-before-after.md` (results; the Gate-2/3 numbers)

**Steps:**
1. Fresh CJ field runs (one per PR, `v04` version) — needed by `select_field_runs` (r6-M4 checklist).
2. Live corpus pass on main baseline (label `pre-v04-*`) and on this branch (label `v04-*`), same repeats, back-to-back (Gate 1).
3. Gate 2: `score_corpus.py` both trees — none of the 24 size-skip goldens remain in `skipped-triage`/`not-judged` on the after-run (at cap ≥ Gate-7 max); cluster recall increases; strict recall not dropped. **Precondition (r6-MINOR-3): `score()` never calls `gate_run` (it skips only `fail_open`, `:202–204`), so every scored repeat must be checked for `n_windowed_failed == 0` first — re-run any repeat that trips the breaker before scoring, and report the count of re-runs; otherwise a transient breaker trip turns goldens into false `not-judged` misses and shifts Gate 3's denominator.**
4. Gate 3: run the Task 6b scorer — windowed-cluster FP rate ≤ 0.315 (hard fail > 0.42, per-cluster denominator per the spec's ruled definition); report `fp_per_clean` delta, `verdict_accuracy` delta, CJ #43 field FP delta, `n_corroboration_flips`, **the per-window rate as context, the Gate-3 unit definition, and a note that any 429-backoff time is included in per-call latencies (`t0` starts before the retry loop at :163, r6-MINOR-4)**.
5. Gates 5–7: Step 0′ live check (suffix + `base_verdict` in JSON), determinism/replay==base_verdict on all repeats **(replay replays a Jev-variant ledger: exclude repeat-variance, not code variance — compare v04 replays against v04 base runs, r13-m5)**, Gate-7 measurement recorded (if Task 0′ deferred any piece).
6. Any gate failure → stop, diagnose, fix, re-run the affected gate. **Gate 6 (replay) failures invalidate any Gate-2/3 conclusion drawn from the same ledgers — fix and re-run the corpus pass before reporting either (r13-m5). No partial success claims.**
7. Commit: `docs(eval): v04 corpus before/after — gates 1-7 results`.

---

## Task 10: README + final review

**Objective:** Document the wall-clock reporting baseline (D8 number from Task 9), the window cap, the new flags; final self-review against every "Hard constraint" bullet above; push; Opus review of the implementation diff.

**Files:**
- Modify: `README.md` (windowing section: what gets windowed, cap, time policy D10, new flags `--window-cap`, `--serial-windows`, `--min-plus-ratio`)

**Steps:**
1. README section + constraint checklist appended to the investigation doc's verification section. README documents `--window-cap`, `--serial-windows`, `--min-plus-ratio` defaults from Task 0′.
2. Push; dispatch Opus review of the full Approach A diff (same doc-mode flow as step zero).
3. Address findings; land per the dual-review-cycle loop.

---

## Validation gates reference (from the doc — all must pass)

| Gate | Criterion | Where |
|---|---|---|
| 1 | Back-to-back live runs, same repeats/day | Task 9 |
| 2 | 24 goldens leave skipped-triage/not-judged; cluster recall ↑; strict not dropped | Task 9 (needs Task 0′ golden-placeability) |
| 3 | Windowed FP rate ≤ 0.315 (hard fail 0.42) + reported costs | Tasks 6b (tooling), 9 (numbers) |
| 4 | Fixture TP/FP set stable ≥2/3; no fixture hunk too_large | Task 8 |
| 5 | Step 0′ suffix + base_verdict machine-readable | Task 9 |
| 6 | Replay == base_verdict; partition/dedup/render tests | Tasks 1–6 + **4b** (preview, _covers, cap scenarios, replay==live) |
| 7 | Gate-7 measurements recorded; cap = 2× max | Tasks 0′, 9 |

## Risks / notes

- **Jev model drift** (`jev-latest` unpinned, `:159`): Gate 1 mitigates by same-day back-to-back; if gate 2/3 results look drift-confounded, re-run both sides once before concluding.
- **The 966-line file costs ~5 windows** — worst-case corpus run adds ≈3–6 s serial; D10 rules this acceptable; breaker bounds dead-provider cost.
- **If Gate 3 fails**: first suspect the ratio floor (D6) being too permissive; tighten and re-run Gate 3 only.
- **Do not** merge before Gates 1–7 all pass and Opus reviews the diff.
