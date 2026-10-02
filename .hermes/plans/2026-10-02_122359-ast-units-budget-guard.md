# AST Units + Budget Guard — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
>
> **Rev 14 — FINAL (pre-implementation).** Revised per Opus doc-review round
> 12: **VERDICT: APPROVE WITH NITS** (no BLOCKER, no MAJOR; verdicts
> r1→r12: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M → 2M → 1M → 1M → 1M →
> APPROVE-WITH-NITS; r12 verified the r13 counter fix correct in all
> three fixture scenarios — 5+1 leaf ⇒ "5 of 6", 45+2/ceiling-40 ⇒
> "40 of 47" — and confirmed `compose()` never reads `skipped`, so
> ceiling entries cannot change verdicts). Nits/minors folded: **m1**
> the r13-m1 render/bucket change now has an OWNER (Task 4 Files lists
> `render()` :1274–1285 + `scripts/score_corpus.py`; Tests add
> `tests/test_score_corpus.py` with the :101–103 dict-gain note and the
> :97-only fossil clarification) + two new tests (render line pin;
> span-covered truncated miss lands in `truncated`). **m2** ceiling-dropped
> units now REACH the PR-level digest (`judge_pr_level` gets
> `size_skipped_code(skipped)` + the `max-hunks>ceiling` entries — today's
> :1352 filter would make them invisible on jev/v08; explicit decision,
> tested). Nits: Task 6 step (3) reworded "DROP `ast_context`" (r14-n1,
> matching Task 4); render header counts ceiling drops separately from
> triage skips (r14-n2, folded into the r7-m3 label rework).
>
> **Rev 13** — revised per Opus doc-review round 11 (REQUEST CHANGES: 1 MAJOR /
> 1 MINOR / 1 nit; verdicts r1→r11: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M → 2M
> → 1M → 1M → 1M; r11 CONFIRMED the r12-M1 reasoning is sound and the
> rewritten tests can now pass, and verified all r12 citations).
> **M1 the r12-m2 `n_units_pre` placement EXCLUDED leaves** — step (4)
> removes leaves from the list before the pre-truncation count, but the
> formula `n_dropped = n_units_pre − n_leaf_unjudged − len(kept)`
> assumes `n_units_pre` CONTAINS them: literal reading gives
> `n_dropped = 5 − 1 − 5 = −1` on a 5-unit+1-leaf run — sweep :116–123
> rejects the ledger as MALFORMED (the r1-B1 class) and the verdict would
> read "5 of 5" while a leaf went unjudged; the r12 property check had no
> leaf in it and could not catch this, while
> `test_single_oversize_line_marks_incomplete` would fail — two
> contradictory instructions. FOLDED: `n_units_pre = len(pre-truncation
> unit list) + n_leaf_unjudged`; leaf-INCLUSIVE property check (45 units
> + 2 leaves, ceiling 40 ⇒ `n_dropped == 5`, denominator 47,
> `n_dropped ≥ 0`). Minors: **m1** `max-hunks>ceiling` entries were
> mislabelled by two consumers — `render()` :1274–1285 would print them
> under "Skipped (deterministic triage)" and `score_corpus.classify_miss`
> :71–73 would bucket ceiling-truncation misses as `skipped-triage`
> file-wide: FOLDED — own render line "Not judged (run ceiling)",
> `**_span(unit)` on every entry, a new `truncated` MISS_BUCKETS bucket,
> and LAYA NEVER EMITS these entries (legacy render test covers laya's
> unchanged Skipped line). Nits: **n1** step 0's "TRIM to the 40/20
> bounds" does nothing (`test_enrichment_size_bounded` caps at
> attachment) — reworded: step 0 is in practice DROP `ast_context`; the
> trim is only a defensive clamp, and no implementer should build a
> partial-trim loop (r12-M1 rules it out).
>
> **Rev 12** — revised per Opus doc-review round 10 (REQUEST CHANGES: 1 MAJOR /
> 2 MINOR / 1 nit; verdicts r1→r10: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M → 2M
> → 1M → 1M; r10 verified the r11 fixes (leaf reason marker vs :1051–1054,
> the corrected :98/:116–123/:124 citations, leaf safety in compose()
> :1101–1102, laya counter collapse, :1398/:1433 sites) as CORRECT).
> **M1 (a logic flaw introduced by r11-m5 itself): trim-first makes
> re-expansion unable to ever split, so `test_enrichment_reexpansion_before_freeze`
> ("re-expansion splits it") and `test_budget_interaction` ("trips the
> soft cap → splits") could never pass** — every non-leaf unit leaving
> step (1) is already ≤ SOFT_CAP unenriched, and `test_enrichment_size_bounded`
> caps `ast_context` at 40/20 on attachment, so an over-cap step-3 unit is
> over cap ONLY because of its context; dropping it (step 0) restores the
> ≤cap state and splitting is never reached — and the per-unit
> `enrichment` flag for a dropped unit was undefined. FOLDED (reviewer
> option a): the re-expansion order on the jev path ALWAYS TERMINATES AT
> STEP 0 (context dropped, unit whole, `enrichment: none` logged — the
> flag records presence in the judged state, never attempt); enrichment
> can NEVER cause a split; the freeze-ordering rule stands as a guard;
> both tests rewritten to end in context-dropped; partial-trim-while-
> splitting is flagged as a potential FUTURE Kurt ruling, not implemented.
> Minors: **m1** truncated units' "explicit unjudged records" now have a
> defined format — `skipped` entries with non-`hunk>` reason
> `max-hunks>ceiling` (NOT parse_error findings: that would double-count
> via `n_unjudged` :1361 on top of `n_dropped` and mislabel them
> "provider call failed"); `test_max_hunks_is_run_level` asserts the
> exclusion. **m2** the pipeline list computed `n_units_pre` AFTER
> truncation (would give `n_dropped == 0` always — the r12 hole) — fixed:
> recorded BEFORE the ceiling cut (after leaves aside), `n_dropped`
> computed at :1340 after truncation; property check 45 units/ceiling 40
> ⇒ `n_dropped == 5`. Nit: **n1** Task 4's initial expansion does not
> list step 0 (no `ast_context` exists yet there); step 0 applies only
> during post-enrichment re-expansion.
>
> **Rev 11** — revised per Opus doc-review round 9 (REQUEST CHANGES: 1 MAJOR /
> 5 MINOR / 2 nits; verdicts r1→r9: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M → 2M
> → 1M; r9 CONFIRMED all rev-10 fixes check out against the code and the
> two-phase counter algebra is correct for laya — collapses to today's
> formulas). **M1 (the last structural gap) the plan never said where Task
> 6's enrichment/re-expansion runs relative to truncation and the
> `n_dropped` freeze** — the natural task-by-task reading lands it after
> the :1340 freeze, so enrichment pushing a unit over cap + re-expansion
> growing `len(kept)` gives `n_dropped = −1` (sweep :116–123 rejects as
> malformed — the r1-B1 failure again), can breach `--max-hunks` 40, and
> loses re-expansion leaves from the frozen `n_leaf_unjudged`. FOLDED: the
> pre-judge pipeline order is PINNED (Task 6 objective + Architecture +
> Task 4's recursion): route/expand → attach `ast_context` → re-estimate/
> re-expand (TRIM first, r11-m5) → set leaves aside → truncate → compute
> `n_units_pre` + freeze `n_dropped` → `judge()`; test
> `test_enrichment_reexpansion_before_freeze`. Minors: **m1** leaf records
> carry `"reason": "unsplittable>cap"` and `judge_pr_level` :1052 prints
> `unjudged (skipped: <reason>)` for reason-marked rows — leaves must not
> appear in the PR-level digest as "provider call failed". **m2** the
> r10 "gate impact" sentence cited :98 for the unjudged rejection (wrong
> check) — corrected: :98 = completeness mismatch, :124 = unjudged.
> **m3** the stale r9-m2 TSV fragment in Task 0 (unclosed bold, duplicate
> of the r10 merged form) deleted. **m4** band anchors' file home is now
> DEFINED: the side file (scored TSV would count them as misses by
> construction and gift G-B a free advantage); G-B reports band recall as
> a separate line. **m5** the lost `ast_context` trim step restored as
> step 0 of the re-expansion order (each child inherits the file symbol
> table; halving never shrinks it — an enriched unit needing only a trim
> could otherwise recurse to an unjudged single-line leaf). Nits: the
> Gate→Task map row now says "non-band anchors verified at Task 0; band
> anchors verified in G-D"; the rev-4 m4 wording now says "excluded from
> `n_units_pre`" (nothing in the jev formulas reads `n_triaged`).
>
> **Rev 10** — revised per Opus doc-review round 8 (REQUEST CHANGES: 2 MAJOR /
> 3 MINOR / 2 nits; verdicts r1→r8: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M → 2M;
> r8 CONFIRMED the two-phase counter algebra (r9-M1) as CORRECT — for laya,
> `n_units_pre = len(hunks) − n_triaged`, so numerator and denominator
> collapse exactly to today's :1372–1373 formulas). **M1 r9-M2 changed the
> header only — Task 0's body still contained the plan the header declared
> unimplementable** (step 4 still demanded "all 3 anchors hit" + the
> nonexistent Task-2 one-flag variant; step 5 still committed "(3 anchors,
> verified)"; the same header-only failure mode as r3/rev 5 — the
> addendum made it worse by excluding band anchors from the scored TSV,
> which by construction empties the band check's input). FOLDED: step 4
> rewritten — non-band anchors hit, band anchors recorded `band` and
> verified LATER by G-D (Task 8); option-2-flag text RETIRED; step 5
> commit message no longer claims full verification; G-D's band check
> reads BOTH the scored TSV and the unverifiable side file (band anchors
> are its INPUT). **M2 the r9-m3 test asserted acceptance of something
> `gate_run` rejects TWICE** (parse_error findings are excluded from
> `judged` :1394 ⇒ the :98–102 completeness check fires first;
> `n_unjudged == 1` hits :124 regardless) — implementing it as written
> would have forced loosening the gate, the exact Step 0′ hole. FOLDED:
> inverted to `test_gate_run_rejects_parse_error_ledger` (asserts the :98
> message + non-admission); Task 8's r8-m3 note corrected (:98 fires
> before :124). Minors: **m1** leaf-record insertion PINNED to the
> :1348–:1350 window (inside `elif hunks:`, before `judge_pr_level` —
> later appends would hide leaves from the PR-level digest and
> `compose()`); digest test added. **m2** the meta/ledger sites are now
> NAMED: :1398 (`meta["n_analyzed"] = len(kept)`) and :1433 (`log_run`)
> must carry the post-judge formula; `test_runtime_split_counts_consistent`
> asserts on the LOGGED record. **m3** G-D's sample set EXPLICITLY
> includes the Task 0 CJ#43 pre-fix run on BOTH arms, 3 repeats. Nits:
> Task 5's `test_judge_return_contract` base text now states `leaves − 1`
> directly; the two overlapping 3-field-parser sentences merged.
>
> **Rev 9** — revised per Opus doc-review round 7 (REQUEST CHANGES: 2 MAJOR /
> 3 MINOR / 1 nit; verdicts r1→r7: 1B5M → 4M → 6M → 2M → 3M → 2M → 2M; r7
> CONFIRMED the r8 fixes as correct as described). **M1 the r8-M1 leaf
> formula collided with `added_units` on RUNTIME splits** — `n_units_total`
> counting pre-judge units PLUS leaves would double-count `added_units`
> when a unit 400-splits (5 units, one → 2 leaves ⇒ `n_units_total` 6
> but `n_analyzed` 5 — `len(judged) == n_analyzed` fails on the very
> runtime-split run the plan's own
> `test_runtime_split_counts_consistent` demanded consistency on); the
> carried rev-4 header still said "`judge()` reports
> leaf counts back into `n_units_total`". FOLDED: counters are TWO-PHASE
> (pinned in Task 4 + the Architecture paragraph + Task 5's objective) —
> PRE-`judge()`: `n_units_pre` = whole parents + sub-clusters + leaves;
> `n_dropped = n_units_pre − n_leaf_unjudged − len(kept)` computed at
> today's :1340 position, NEVER recomputed; POST-`judge()`:
> `n_units_total = n_units_pre + added_units`; `n_analyzed = len(kept) +
> added_units + n_leaf_unjudged`; Incomplete denominator =
> `n_units_total + n_size_skipped_code` (laya-only term; formulas
> collapse to today's legacy ones for laya). **M2 r8-M2's Task 0 fix was
> UNIMPLEMENTABLE** — Task 2 does not exist when Task 0 runs (git
> dependency, not task numbering), so "the v08 branch with option 2's
> threshold" cannot verify band anchors at fixture time. FOLDED: Task 0
> records band anchors as `verifiability: band`/`unverifiable` with
> defined handling; the BAND CHECK itself (G-D, defect-positive,
> span-containment HIT, MISS ⇒ STOP trigger) remains the recall evidence
> — verifying the anchors early was never the load-bearing part. Minors:
> **m1** `test_runtime_split_counts_consistent` additionally asserts
> `n_dropped == 0` + no Incomplete suffix (two-phase protection made
> testable). **m2** Task 0 TSV rows are 3-field (`file<TAB>line<TAB>desc`)
> — the parser :1185–1187 reads at most three tab-separated fields, so a
> TAB inside a description truncates it; keep descriptions tab-free.
> **m3** `judged` rows exclude `parse_error` findings (:1394), so a
> leaf-record run's `judged` is shorter than `n_analyzed` BY DESIGN —
> `test_gate_run_accepts_v08_split_ledger` gains a parse_error variant
> asserting `gate_run` :97–102 accepts it. Nit: `test_max_hunks_is_run_level`'s
> "first-40" assertion now notes leaves never compete for ceiling slots
> (set aside before truncation). **Addendum (same round, from the
> review-tail delivery): band check credits AT MOST ONE golden per
> reported cluster (greedy :1197–1202 pattern; >1 golden in one cluster =
> PARTIALLY unmeasured → same escalation as zero); `verifiability` lives
> in the eval doc + a `#` comment header in the TSV, and `unverifiable`
> anchors stay OUT of the scored TSV (a 4th column is silently dropped
> and an unverifiable row in-TSV counts as a miss); `render()` :1243's
> "analyzed=N hunks" label is reworded + pinned by test (leaves are
> accounted units, never sent).**
>
> **Rev 8** — revised per Opus doc-review round 6 (REQUEST CHANGES: 2 MAJOR /
> 3 MINOR; verdicts r1→r6: 1B5M → 4M → 6M → 2M → 3M → 2M; r6 also CONFIRMED
> r7-m2's stub-signature fix and r7-m3's double-exclusion analysis as correct).
> **M1 the r7-M2 unjudged-leaf record broke Task 4's counter formula** — the
> leaf can't enter `kept` (`judge()` sends every element it receives,
> :942), so `n_units_total − len(kept)` counted it as `n_dropped == 1`,
> contradicting the plan's own test and resurrecting the exact
> mislabelling r7-M2 removed; three things were also undefined (ceiling
> slot? `n_analyzed` membership? insertion point — before `judge()` would
> SEND the leaf; after a fail-open, :1348 discards it). FOLDED: explicit
> `n_leaf_unjudged` count; leaves EXEMPT from the `--max-hunks` ceiling
> and set aside BEFORE truncation; `n_dropped = n_units_total −
> n_leaf_unjudged − len(kept)`; `n_analyzed = len(kept) + added_units +
> n_leaf_unjudged`; suffix numerator = `n_analyzed − n_unjudged`;
> `main()` appends leaf records to `findings` only AFTER a non-None
> `judge()` result; three-counter test added. **M2 the r7-M3 band check
> contradicted Task 0 and its STOP trigger measured matcher GEOMETRY, not
> recall** — (a) if a golden sits in importMachine.ts's 273-line cluster,
> today's `triage()` :722–725 skips it and Task 0's "all 3 anchors hit"
> fails by construction (the brief never actually places a defect in a
> band cluster); (b) `eval_against_golden` :1193 matches ±1 on the single
> whole-cluster anchor, so any defect >1 line below the anchor is a
> guaranteed MISS regardless of the model; (c) if no golden lands in
> band, the check passes empty. FOLDED: Task 0 records per-anchor
> `verifiability` (band anchors verified on the v08 build with option 2's
> threshold applied for that run ONLY; else `unverifiable`, never
> silently hit); the band check's HIT criterion is now span-containment
> (`line_start ≤ g ≤ line_end` from `_span`, AND the cluster reported) —
> the ±1-anchor result is information-only and NEVER triggers; zero band
> goldens ⇒ UNMEASURED, not passed, escalated to Kurt. Minors: **m1**
> `_OverBudget` mechanics pinned — `jev_ask` :181 raises `_NoRetry` for
> every <500 BEFORE body inspection and :189's `except Exception`
> retries, so the `max_tokens_exceeded` check must run BEFORE :181 and
> `_OverBudget` becomes a `_NoRetry` SUBCLASS (judge()'s r6-m3 catch
> order still applies); test asserts ONE request only. **m2** Task 7
> "five"→"four" default sites (:41 `RUBRIC_VERSIONS` holds versions, not
> a default). **m3** `gate_run` :124 rejects any `n_unjudged > 0` run, so
> over-cap leaves honestly shrink gate populations — Task 8 reports
> excluded runs per arm and compares control vs v08 on the SAME
> surviving samples.)
>
> **Rev 7** — revised per Opus doc-review round 5 (REQUEST CHANGES: 3 MAJOR /
> 3 MINOR / 2 nits; verdicts r1→r5: 1B5M → 4M → 6M → 2M → 3M; every finding
> verified against the code before folding). **M1 Task 3 still carried the
> 200-line fixtures r4-M1 removed elsewhere** (`test_treesitter_units_when_present`,
> `test_line_window_fallback` — a 200-line .ts ≈ 3k tokens can never trip the
> token gate; the conflict is invisible in CI because the tree-sitter test is
> skipif-gated and only bites on a local run). FOLDED: both fixtures resized
> to >84k serialized chars. **M2 an over-cap unit that cannot be split
> pre-judge had NO defined outcome** (the "mark unjudged" rule existed only
> on `judge()`'s runtime path; `n_unjudged` counts only `parse_error`
> findings :1361, so a unit set aside before `judge()` either lands in
> `n_dropped` — mislabelled as `--max-hunks` truncation — or vanishes
> silently, the exact coverage hole G-A exists to catch). FOLDED: pre-judge
> expansion is RECURSIVE with a fixed order — top-level AST → nested AST →
> line windows → halving down to a single line — and an unsplittable leaf
> (e.g. one 90k-char line: inline base64, embedded JSON) emits a
> `{"hunk": <unit>, "parse_error": True, "raw": None}`-style unjudged record
> so `n_unjudged` + the Incomplete suffix fire; test
> `test_single_oversize_line_marks_incomplete`. **M3 the r6-M1 band
> sub-measure could not detect the recall loss it guards against** (it ran
> only in G-C, whose 5 CJ heads are defect-free — FP evidence only; G-D had
> none; band clusters are skipped by the control transport, so there is no
> control verdict to differ from). FOLDED: band sub-measure added to G-D as
> a mandatory arm; defect-positive band check added (report which Task 0
> golden anchors fall inside band clusters — importMachine.ts at 273 lines
> is one — and whether each is hit within ±1 line by the single
> whole-cluster anchor); **ANY band golden missed = STOP and take option 2
> (separate ~120-line AST engagement threshold) back to Kurt** — that is
> the trigger the pending-ruling resolves on. Minors: **m1** `added_units`
> is the NET count `leaves − 1` (the over-budget parent is REPLACED, not
> kept, so `judged = len(kept) − 1 + leaves`; the old "leaf count"
> definition made `len(judged) != n_analyzed` and `gate_run` :97–102 would
> have rejected every legal runtime-split run while
> `test_runtime_split_counts_consistent` demanded it pass); **m2** the
> r6-m2 stub list now includes SIGNATURE changes: `judge()` takes
> `split_unit` keyword-only with default `None`, and the
> `fake_judge(kept, ask, errors=None)` stubs at tests/test_line_span.py:42
> and tests/test_triage_and_failreason.py:176 gain the parameter — a bare
> return-value update would `TypeError` on the new kwarg from `main()`;
> **m3** r6-m4's regression test PINS the reason string, it does not add
> behaviour — whole-file deletions are already excluded from
> `n_size_skipped_code` TWICE (the `"hunk>"` prefix match :1231 AND the
> `change_type` filter :1232–1233). Nits: Risks "revisit **ruled** option
> 2" → "revisit option 2" (nothing is ruled yet — it is the pending
> option); estimator formula note added: dividing the longest question's
> chars by 3.0 (vs the brief :263–264, which sums the question map EXACTLY
> and estimates only the state) is a DELIBERATE conservative deviation.
>
> **Rev 6** — revised per Opus doc-review round 4 (REQUEST CHANGES: 2 MAJOR /
> 4 MINOR / 3 nits; verdicts now r1→r4: 1B5M → 4M → 6M → 2M). **M1
> fixture-vs-definition conflict (folded as option (a), ruling flagged to
> Kurt):** the plan's own oversize definition (>28k tokens ⇒ >84k serialized
> chars) made three test fixtures (200/273/200-line files ≈ 3k–8k tokens)
> incapable of tripping it — both test sets could never be green at once.
> FOLDED: all oversize fixtures resized to >84k serialized chars (~2,400
> changed lines); NO new engagement threshold added (that would be a design
> change vs the ruled brief). **STATED CONSEQUENCE (flagged for Kurt,
> pending-ruling — numbered options per house convention):** clusters from
> ~121 lines to ~84k chars, skipped today, are now judged as ONE whole call
> with a single anchor — wisdom.ts (7.3k tokens whole-file) never splits;
> the brief's own evidence (importMachine.ts 273 lines → 9 units) sits
> below the token gate, golden ±1-line matching degrades for findings deep
> in a single-anchor cluster, and G-A can pass while recall on those
> clusters silently drops. Options: **1. (recommended — implemented in this
> rev) token-only engagement + the new G-C/G-D sub-measure tracking
> verdict changes on previously-skipped 121-line…84k-char clusters, and a
> revisit after gate data lands; 2. add a separate AST engagement
> threshold (~120 lines, the old number under a new name) so AST/window
> splitting engages there while the token cap stays the send-gate
> guarantee — rewords r1-M4's "defined exactly once"; 3. accept as-is with
> the stated recall risk only.** (a) and (b) were the reviewer's two
> options; (b) = option 2 here. **M2 unmatched-symbol rule (folded):**
> pre-image symbols with no qualified-name counterpart in the post-image
> (deleted/renamed/moved) form their OWN sub-clusters — cut on pre-image
> boundaries, anchored via `e[4]`, parent `change_type`, union == original
> always; deletion-only parents cut on the pre-image AST directly; tests
> `test_deleted_symbol_forms_own_subcluster` +
> `test_renamed_function_old_code_not_lost`. Minors: **m1** laya keeps the
> size sort + truncate (:1338–1339) — order tested both ways (laya
> size-descending, jev first-come); **m2** `judge()` fail-open paths return
> `(None, latencies, meta)` too (:959/:1025/:1035; all six 2-tuple stub
> sites updated; fail-open unpacks 3-tuples, never ValueErrors); **m3**
> `split_unit` callable injected by `main()` (judge has no images); None ⇒
> unjudged; `_OverBudget` caught BEFORE the generic `except Exception`
> (:954); **m4** `whole-file-deleted>cap` feeds `n_triaged` only (r11-nit:
> reworded: it is EXCLUDED from `n_units_pre`; nothing in the jev formulas
> reads `n_triaged` anymore) — excluded
> from `size_skipped_code()` by its reason prefix (:1231 startsWith
> "hunk>"); regression test: no "(incomplete" suffix. Nits: Task 5 commit
> message de-proactive'd; `jev_ask` range :157–193; rev blocks now ordered
> newest-first.
>
> **Rev 5** — revised per Opus doc-review round 3 (REQUEST CHANGES: 6 MAJOR /
> 7 MINOR / 2 nits; all verified — rev 4's fixes had landed in headers only,
> several task bodies still described rev-3 behaviour). **M1** Task 2's body
> still mapped `-` lines by `e[4]` — rewritten: `+` lines map by `e[1]` into
> the POST-image AST; `-` lines map by `e[1]` into the PRE-image AST (matched
> by qualified name); `e[4]` is anchor-fallback only. **M2** Task 2 dropped
> deletion-only clusters entirely, contradicting r2-m4 AND brief req 1 —
> plan now overrides req 1 with a logged brief erratum #2 (in-file
> deletion-only clusters HAVE a post-image); only `whole-file-deleted`
> returns `None`. **M3** oversize whole-file deletions had no defined path
> (would trip "never send over cap" or mark every such PR Incomplete) —
> they keep today's deliberate-triage skip under a NEW reason string
> `whole-file-deleted>cap` (deliberate, feeds `n_triaged` like today's
> size-skips; no regression; alternative rejected: line-window split of a
> deleted file judges dead context). **M4** the jev gate is now MECHANICAL:
> `triage()` takes a `provider`/`size_policy` param; `test_no_hunk_skip_*`
> scoped to jev; `test_laya_keeps_size_skip` added; "MAX_HUNK_LINES
> retired" reworded to "retired for jev — it remains LAYA's skip gate";
> Risks laya bullet corrected (laya runs through `judge()` :1343; laya
> safety = provider gate + `_OverBudget` impossible on laya's transport).
> **M5** Task 5 no longer does proactive splitting — it owns ONLY the send
> gate (defense-in-depth assert) and the runtime-400 path; proactive
> trimming/splitting lives in the pre-judge expansion pass (Task 4, re-run
> in Task 6). **M6** G-D's live arm gains a CONTEMPORANEOUS CONTROL arm —
> current main build (v03b transport), live, 3 repeats, same samples; v08
> gates against the control (same-day model), v06 ledgers demoted to sanity
> reference (model drift no longer confounds). Minors: **m1** `old_file`
> field added to clusters in `package_hunks` (rename-from is currently
> DROPPED at :502 and the old path overwritten by `+++` :486–498); **m2**
> `--no-enrichment` knob added to Task 6 (logged `enrichment: none`) so the
> mandatory G-D arm can actually run; **m3** enrichment mechanism stated:
> `main()` attaches `ast_context` only when provider==jev; `hunk_state`
> reads it if present; laya states never carry the key (tested); **m4**
> Task 8 objective + gate table aligned with the two-mandatory-arm step 4;
> **m5** `RUBRIC_VERSIONS` is EXTENDED to `{"v03b", "v08-ast"}` (it feeds
> the `rewrap()` guard — overwriting would stop rejecting malformed v03b
> entries); only the DEFAULT-carrying sites (:72/:158/:418/:570) flip to
> v08-ast; **m6** `judge()` return contract specified: `(findings,
> latencies, meta)` with `meta = {"added_units": N, "avg_input_tokens":
> float|None}`; every caller + test stub updated; laya ⇒ `None` (no
> `usage`); **m7** `test_render_collapses_duplicate_skips` stays VALID (laya
> still emits `hunk>`) — Risks no longer says to touch it. Nits: round tags
> are generation-local (legend added); Task 4's mode-aware cache tag and
> Task 8's baseline tag re-pointed to their true sources; `--range`
> merge-base ambiguity noted (first `git merge-base` result, matching
> `git diff A...B`).
>
> **Rev 4** — revised per Opus doc-review round 2 (REQUEST CHANGES: 4 MAJOR /
> 6 MINOR / 2 nits; every finding verified against the code before folding):
> **M1** "laya path untouched" was FALSE — `judge()` (:927, wired at :1343)
> and `main()`'s routing (:1334–1340) are provider-agnostic, so Tasks 4/5/6
> as written would reach laya and change its input shape against a 28k cap
> that has nothing to do with laya's unmeasured context. Fix (D6-compliant,
> no new ruling needed): ALL of AST splitting, enrichment, and the budget
> guard are gated on `provider == "jev"`; laya keeps TODAY'S behavior —
> oversize clusters skipped with a `hunk>` record via the retained
> `size_skipped_code()` path. Tests assert laya receives whole oversize
> clusters + skip records, and jev receives sub-clusters; **M2** judge-time
> proactive splitting reopened the r3-B1 counter problem (extra judged
> entries vs `n_analyzed` ⇒ `gate_run` :97–102 rejects; verdict numerator
> counts wrong) and leaf-answer aggregation was undefined (a merged finding
> would contradict no-merged-unit-judging). Fix: ALL proactive expansion
> happens BEFORE `judge()` — Task 4 expands on unenriched states, Task 6
> RE-expands after enrichment (enrichment can push a unit over the cap —
> the plan's own `test_budget_interaction` proves the ordering matters;
> **r11-M1: the FULL pre-judge pipeline order is PINNED in Task 6 —
> expand → attach `ast_context` → re-estimate/re-expand (trim first) →
> set leaves aside → truncate → compute `n_units_pre` + freeze
> `n_dropped` → `judge()` — enrichment and re-expansion ALWAYS precede
> the freeze**, never after it) —
> and `judge()` keeps ONLY the runtime-400 path, where a split leaf returns
> as its OWN judged entry; `judge()` reports the added-unit count back so
> `n_units_total`/`n_analyzed` stay consistent; a `gate_run` test covers a
> runtime-split run; **M3** assigning `-` lines by `e[4]` was wrong —
> `new_line` never advances on `-` entries (:569–572), so a whole deletion
> run shares ONE e[4] and would collapse all old code into the first
> sub-cluster (itself possibly oversize) while later sub-clusters read as
> pure additions. Fix: `-` lines are ASSIGNED by OLD-FILE symbol — look up
> `e[1]` (old_line, which does advance) in the PRE-image AST and match the
> qualified name to the post-image unit — giving the pre-image a second job
> beside enrichment; `e[4]` remains only the ANCHOR fallback; test: 3-function
> rewrite emitted as one `-` block + one `+` block ⇒ each sub-cluster gets
> its own before-text; **M4** G-D's replay arm proved nothing (replaying
> unchanged inputs agrees 100% by construction, and Python is ALWAYS
> enriched, so the clusters that actually changed got no comparison). Fix:
> G-D now REQUIRES a live re-call arm on the enriched set, measured against
> the v06-postmerge 3-repeat baseline, and the enrichment-off arm is
> mandatory; runs affected by the truncation-order change (r1-m8) are
> reported separately. Minors: **m1** Task 4's `gate_run` test passes
> `packaging_version` explicitly (default is `v03b` at :72/:158/:418 until
> Task 7 flips them) and Task 7 now lists ALL default sites (:41 RUBRIC_VERSIONS,
> :72 gate_run, :158 select_runs, :418 select_field_runs, :570 argparse;
> **superseded by r8-m2: :41 holds VERSIONS, not a default — the default
> sites are the four :72/:158/:418/:570**);
> **m2** the hard-cap send-gate test uses SYNTHETIC oversized questions
> (real questions can't exceed 56k once state+longest ≤28k) and is labeled
> **m3** split-trim order is `ast_context` FIRST (up to 40 symbols + 20 lines — the only part with real mass; diff context is capped at CTX=4 lines/side, :456) — NOTE r5: the trim itself moved to Task 4/6's pre-judge pass in rev 5 (r5-M5); **m4** deletion-only clusters DO have
> a post-image (only whole-file deletions don't) and are enriched from the
> PRE-image symbol map — the clusters that benefit most (mechanism lives in
> Task 2/4 since rev 5; r5-M2); **m5** Task 6 is
> Arch **2**'s enclosing-symbol enrichment; Arch **3** (call-graph) is
> UNPROVEN AND DEFERRED (brief :124–127, :233–236) — the rev 7 changelog's
> ":505 says Arch 3" line is an erratum, noted in the brief in this PR;
> **m6** merge-base inputs named: `--pr` base = `origin/main` (:412);
> `--range` base = the left side of the spec (triple-dot parsed; may be
> implicit HEAD) — `A..`/`..B` forms tested. Nits: inner cut points of
> sub-clusters cut from one changed run get NO neighbour changed lines as
> context (the context rule :613–627 never shows them) — documented +
> tested; the impl branch cuts from main AT IMPLEMENTATION TIME (main =
> d4eae9c as of rev 4; 394ea0a was the brief's merge commit, now history).
>
> **Rev 3** — revised per Opus doc-review round 1 (REQUEST CHANGES:
> 1 BLOCKER / 5 MAJOR / 8 MINOR / 2 nits; every finding verified against
> the code before folding): **B1** unit expansion breaks the run counters —
> `n_dropped = len(hunks) - n_triaged - len(kept)` counts PARENT clusters on
> one side and UNITS on the other, so one oversize cluster splitting into N
> sub-clusters drives `n_dropped` negative; `gate_run` (sweep :116–124)
> requires non-negative ints, so every v08 ledger with a split would die as
> malformed and no v08 run could enter a sweep. Task 4 now RECOMPUTES the
> counters in units after expansion (`n_units_total`; `n_dropped =
> n_units_total - len(kept)`; the Incomplete verdict denominator becomes
> `n_units_total`), with tests: clean split ⇒ `n_dropped == 0` and no
> "(incomplete" verdict suffix; `n_dropped >= 0` always; `gate_run` accepts
> a v08 ledger that contains splits; **M1** Task 6's on-by-default
> enrichment contradicted the "byte-identical ordinary clusters" risk claim
> and would have invalidated G-D's replay set (replay assumes unchanged
> input shape; enriched states are a new shape, and the 0.50/0.70
> thresholds were calibrated on unenriched v03b states) — Risks corrected
> (anchors unchanged, STATES are not), `enrichment` recorded PER-UNIT in
> `judged` (run-level D7 stamp stays), G-D's replay set defined as
> UNENRICHED clusters only, and Task 8 adds a v08 threshold re-sweep before
> landing; **M2** missing `git show` images (added file: no merge-base
> pre-image; rename: cluster carries the new path; binary/gitlink) hit
> `run_git`'s `sys.exit` (:346) and killed the whole run — new non-exiting
> `git_show_or_none` helper, rename-from path used for the pre-image,
> per-mode tests for added/rename/binary, and the pre-image's PURPOSE now
> stated (mapping `-` lines to their old-file enclosing symbols for
> enrichment); **M3** sub-cluster anchors were wrong for deletion-only runs
> cut from a code-change parent (no `+` entry ⇒ anchor undefined) and
> deletion lines must map by the tracked HEAD line `e[4]`, not `e[1]` —
> Task 2 factors `package_hunks`' full anchor chain (`+` → `e[4]` of `-` →
> context → `hunk_start`, :633–647) into a shared helper and adds a
> deletion-only sub-cluster test; **M4** "oversize" is now DEFINED once:
> engagement criterion = `estimate_call_size(cluster state) >
> SOFT_CAP_TOKENS` (token-based, the brief's units; `FALLBACK_WINDOW_LINES`
> is a window SIZE, not the gate); **M5** Task 1b could not run where
> placed (its "units per call" census needs Tasks 2/3) and Task 0 preceded
> it despite the "before fixtures" claim — the census now measures
> per-cluster serialized `hunk_state` (the SHIPPED transport) using only
> the Task 1 estimator, with the units-level split counts recomputed
> post-implementation in Task 8; minors: **m1** only `v03b` was ever
> stamped (`v06-postmerge` is a corpus run LABEL, not a packaging version)
> — Task 7 tests v03b + v08-ast only; **m2** `HARD_CAP_TOKENS` is now
> enforced by a send-gate test (state + ALL questions ≤ HARD_CAP_TOKENS);
> **m3** `CHARS_PER_TOKEN = 3.0` (the brief's code-dense-JSON prior; 3.24
> was measured on raw TS source at request level — JSON escaping lowers
> chars/token, and the smaller divisor errs conservative), recalibrated
> from logged `avg_input_tokens`; **m4** `_OverBudget` is raised INSIDE
> `jev_ask` (where the 400 body is inspected; re-raised untouched like
> `_NoRetry`, never given the 5xx retry; wrapping `ask()` is wrong — it
> serves both providers, so a wrapper there is not JEV-only per D6); the
> split loop lives in `judge()`; laya never sees `_OverBudget`; **m5**
> tree-sitter lazy import goes through an injectable loader (`__import__`,
> the `get_laya_router` pattern) — no static `import tree_sitter` (no
> stubs ⇒ CI mypy fails) and no `# type: ignore` (`warn_unused_ignores`
> ⇒ local mypy fails when tree-sitter IS installed); ruff + mypy added to
> the green-suite gates; **m6** a fake-loader test exercises the TS
> boundary logic offline (CI never installs tree-sitter, and the corpus's
> worst offenders are .ts); **m7** G-B harness wording fixed (it DOES
> import working-tree functions, read-only; what it never does is ship or
> land); **m8** run-ceiling truncation order specified: first-come-
> across-files (brief :282), not size sort — tested; nits: Task 0 step 4
> names the real `--golden <tsv>` CLI path, and the
> `tests/test_score_corpus.py:97` fossil string is noted as intentional
> old-ledger fixture data.

**Goal:** Replace the 120-line skip with AST-aware review units, a 32k payload budget guard, and AST context enrichment — closing the hunk>120 coverage hole per the approved architecture brief (rev 7, D1–D8 ruled).

**Architecture:** Clusters stay the unit of judgment and per-cluster calls stay the transport (D5). What changes — ALL gated on `provider == "jev"` (r2-M1: `judge()` :927 and `main()`'s routing :1334–1340 are provider-agnostic, so without an explicit gate everything below would reach laya; D6 keeps laya per-cluster until measured): (1) oversize change regions are cut on AST boundaries first (stdlib `ast` for Python, lazy tree-sitter import for TS/JS/etc., line-window fallback), producing AST sub-clusters that inherit the parent cluster's identity; (2) every outgoing call is budget-checked against Jev's real 32k state+longest-question limit, with a guaranteed-terminating split on `_OverBudget`; (3) each unit's state gains read-only AST context (enclosing symbol, file symbol table) — enrichment, not merged units; (4) the ledger stamps transport/wire_format/enrichment/record-version (D7). **Laya (r2-M1): none of the above applies — laya keeps TODAY'S behavior: oversize clusters skipped with a `hunk>` record via the retained `size_skipped_code()` path (it is back-compat for old ledgers AND live for laya).** Honesty machinery (Step 0′, `base_verdict`, gate_run, Incomplete) is untouched EXCEPT the counter recomputation B1 requires (Task 4) — the Incomplete denominator moves from parent-cluster counts to unit counts, and `judge()` reports runtime-400-split leaf counts back into `n_units_total`/`n_analyzed` (r2-M2: only the runtime path may add units during judging; all PROACTIVE splitting happens before `judge()`, re-checked after enrichment in Task 6). **r9-M1 — counters are TWO-PHASE and pinned in Task 4: pre-`judge()` phase computes `n_units_pre` (whole parents + sub-clusters + leaves) and FREEZES `n_dropped = n_units_pre − n_leaf_unjudged − len(kept)` (never recomputed); post-`judge()` phase sets `n_units_total = n_units_pre + added_units` and `n_analyzed = len(kept) + added_units + n_leaf_unjudged`; Incomplete denominator = `n_units_total + n_size_skipped_code` (last term non-zero for laya only, where the formulas collapse to today's legacy ones).**

**Spec:** `docs/superpowers/investigations/2026-10-01-architecture-ast-batching-brief.md` (rev 7) on this branch — authoritative for every number and rule cited below. D1–D8 all ruled as recommended (2026-10-02). Erratum noted in this PR (r2-m5): the brief's rev 7 changelog line says "D3 Arch 3 enrichment on the default path" while its body (:233–236) correctly rules Arch 2's enclosing-symbol enrichment as the default-path item and keeps Arch 3 (call-graph) deferred — the changelog wording is the error; this plan follows the body.

**Tech Stack:** Python stdlib at core (ast, json, math) — CI runs 3.10/3.12/3.14, so nothing may require >3.10 (`ast` `end_lineno` is 3.8+, fine); optional lazy `tree_sitter` + per-language grammar packages (D1 — import failure = silent fallback to line windows); pytest. No new required dependencies.

**Branch:** `impl/ast-units` off `main` at implementation time (main = d4eae9c as of rev 4; r2-nit: 394ea0a was the brief's own merge commit, now superseded). Baseline: full suite green on main; 254+ tests.

**Hard constraints from the brief (do not deviate):**
- Cluster = unit of judgment; NO merged-unit judging. Every cluster/sub-cluster keeps its own anchor + full question triple (u triples, D8). Sub-clusters inherit parent `change_type`.
- The 32k budget = state + longest question, in **TOKENS** (the brief's units), estimated SERIALIZATION→tokens via the chars-per-token factor (**3.0** initial prior — the brief's code-dense-JSON factor; 3.24 was measured on raw TS source at request level and JSON escaping lowers chars/token, so 3.0 errs conservative), recalibrated from logged `usage.input_tokens`, computed on every call; constants `SOFT_CAP_TOKENS = 28_000`, `HARD_CAP_TOKENS = 56_000` (32k request / 64k total doc budgets); never send an estimated-over-soft-cap call. Soft cap (split proactively), hard behavior on runtime 400+`max_tokens_exceeded`: typed `_OverBudget` raised INSIDE `jev_ask` (the site that inspects the 400 body; re-raised untouched by the handler exactly like `_NoRetry`, and never given the 5xx retry — `ask()` serves both providers, so a wrapper around `ask()` would leak JEV machinery into laya's path, violating D6), split in half (AST sub-clusters first, then ±1-line windows at the leaf) with the split loop living in `judge()`; laya never sees `_OverBudget`; bounded termination (depth-capped recursion, at ONE unit mark that cluster unjudged — feeds Incomplete — and stop), over-budget chain = ONE attempt for the consecutive-failure counter; any other 4xx = existing `_NoRetry`.
- **"Oversize" is defined exactly once (r1-M4):** a cluster is oversize iff `estimate_call_size(hunk_state(cluster)) > SOFT_CAP_TOKENS`. This token criterion REPLACES the retired line-count gate everywhere (triage routing in Task 4, AST engagement in Task 2). `FALLBACK_WINDOW_LINES` sizes fallback windows only — it is never an engagement or skip test.
- `MAX_HUNK_LINES` RETIRED as a skip mechanism (no more `hunk>120 lines` skips); `--max-hunks` redefined as units-per-run (run-level ceiling 40, no file-level drops). When the ceiling truncates, units are kept in FIRST-COME-ACROSS-FILES order (brief :282 — file order, then cluster order within the file; NOT size-sorted, r1-m8), and dropped units get explicit unjudged records (**r12-m1: truncated units become `skipped` entries with a NON-`hunk>` reason `max-hunks>ceiling` — NOT parse_error-style findings, which would double-count via `n_unjudged` :1361 on top of `n_dropped` and falsely label them "provider call failed" in the digest; `size_skipped_code()` :1231 only matches the `hunk>` prefix so these stay out of `n_size_skipped_code`; `test_max_hunks_is_run_level` asserts `n_unjudged` does NOT include them; **r13-m1: `render()` prints `max-hunks>ceiling` entries on their OWN line ("Not judged (run ceiling)"), NOT under "Skipped (deterministic triage)" :1274–1285 — a ceiling drop is not triage; the entries carry `**_span(unit)` so `score_corpus.classify_miss` :71–73 coverage is span-scoped, not file-wide; the corpus replay counts them in a `truncated` MISS_BUCKETS bucket (distinct from `skipped-triage`); LAYA NEVER EMITS these entries (laya keeps its `hunk>` size-skips; the laya legacy render test covers its unchanged Skipped line)**).
- Per-mode file sources for AST parsing: `--range/--pr` = `git show <head>:<path>` post + `git show <merge_base>:<path>` pre (plan computes merge base — `resolve_diff` doesn't return it; r2-m6 names the base inputs: `origin/main` for `--pr`, the range spec's left side for `--range`); `--staged` = `git show :<path>` post vs `git show HEAD:<path>` pre; `--uncommitted` = worktree post vs `git show :<path>` pre (documented diff-only exception, D4). The PRE-image exists for TWO reasons (r1-M2 + r2-M3): mapping `-` (deleted) lines to their OLD-file enclosing symbols — assignment via `e[1]`, NOT `e[4]`, which never advances on `-` entries — AND enrichment for deletion-only units (r2-m4). Image fetches NEVER go through bare `run_git` for these paths — a missing image is a normal case (added file ⇒ no merge-base pre-image; rename ⇒ pre-image lives under the old path; binary/gitlink ⇒ no text image), so a dedicated non-exiting `git_show_or_none` helper returns None and the caller degrades (no pre-image ⇒ `-` lines get symbol-free enrichment; no post-image ⇒ cluster stays whole, r1-M2).
- Whole-file-DELETED clusters stay cluster-based (no post-image at all; no AST parsing). r2-m4: an in-file DELETION-ONLY oversize cluster is different — it has a post-image and is sub-clustered/enriched from the PRE-image symbol map like any oversize cluster.
- Sub-cluster context rule (r2-nit): when sub-clusters are cut from inside ONE run of changed lines, the inner cut points get NO neighbour changed lines as context — the context rule (:613–627) never shows a neighbour's changed lines. Documented and tested as intentional behaviour.
- Failure semantics: per-unit KEY misses mark only that cluster `parse_error` (never touch `failures`/`parse_failures`); only CALL-level shape failures (`answers` missing/not-dict, zero parseable units) count toward consecutive limits; nothing-judged → fail-open unchanged.
- Thresholds stay per-rubric (code 0.50, deletion 0.70) — untouched as VALUES; Task 8 re-sweeps them on v08 fixtures before landing because enrichment changes the state distribution they were calibrated on (r1-M1).
- Laya: per-cluster transport unchanged; batching/AST path is JEV-only (D6). Old shape-only laya contract stays. `_OverBudget` is jev_ask-internal; laya never observes it.
- Ledger contract (D7): every run stamps `transport` (`per-cluster`), `wire_format` (`hunk_state-v1` / `ast-units-v1`), `enrichment` (`none`/`ast`), AND each `judged` entry carries its own `enrichment` value (r1-M1 — enrichment availability is per-language/per-machine, so a run-level flag alone cannot tell a replay which states changed shape); `PACKAGING_VERSION` bumps (new value `v08-ast`) so replays compare like-for-like.
- Tree-sitter = lazy opportunistic import via an INJECTABLE LOADER (`(loader or __import__)("tree_sitter")` — the `get_laya_router` pattern, :270–296); never a module-level or function-body static `import tree_sitter` (mypy has no stubs for it and CI runs mypy with `warn_unused_ignores`, so both a bare import and a `# type: ignore` fail one side each — r1-m5). ImportError → stdlib/fallback silently (D1). README documents it.
- Retired Step 0′ size-skip machinery (`size_skipped_code()` :1225–1233, `n_size_skipped_code`, skip-record `change_type`, sweep's size-skip-admitting branch :79–127) stays in place as LEDGER BACK-COMPAT for old v03b-era records; new runs simply never produce `hunk>` records. A comment at each site says "retired by v08-ast, kept for old-ledger gating." (`tests/test_score_corpus.py:97` hardcodes `"hunk>120 lines"` as OLD-LEDGER FIXTURE DATA — intentional, do not update, r1-nit.)
- `usage.input_tokens` is logged per call (transport → judge → ledger `avg_input_tokens`) — recalibration data for the chars-per-token factor (M4).

---

> **Rev 2** — revised per adversarial review (/tmp/ast-plan-review.md,
> NOT READY verdict, 1 BLOCKER / 6 MAJOR / 6 MINOR / 3 nits, all verified
> against code): **B1** G-B's batched treatment arm needs batching transport
> code before the gate can run — Task 9 now uses an OUT-OF-TREE harness
> (`/tmp/gb_harness.py`, experiment scaffolding like the S1′ probe, never
> shipped), with the per-file wire format specified in the task itself;
> **M1** budget constants are TOKENS (28k/56k), not chars — estimator
> returns estimated tokens via a calibrated chars-per-token factor
> (3.24 prior), recalibrated from `usage.input_tokens` (M4: now logged
> per call into the ledger); **M2** req-1 both-sides file sources +
> merge-base computation now owned by Task 4 with per-mode tests;
> **M3** G-C (5 clean CJ heads stay ≤1 FP major) added to Task 8;
> **M5** estimator test asserts against state+longest-question (the 32k
> quantity) and a separate lower-bound check against the full payload;
> **M6** serialized census recompute moved to Task 1b (before fixtures/
> implementation, per brief ordering); minors: code cites corrected
> (ask loop :950–965, routing site :1336–1343, sweep default :570),
> depth-cap test restated as bounded-termination + recursion-helper
> test on synthetic multi-unit input, G-D baseline named
> (v06-postmerge 3-repeat runs), cache key made mode-aware
> `(mode, rev, path)`, fallback window size gets its own constant
> `FALLBACK_WINDOW_LINES`, Step 0′ machinery disposition stated (kept
> as ledger back-compat), CI interpreter (3.10/3.12/3.14) replaces the
> 3.14-only pin, fixture-stability criterion tied to G-D repeats.
>
## Task 0: Defect-positive fixture (plan prerequisite, brief req 8)

**Objective:** Anchor the 3 real pre-fix majors of curated-journal PR #43 (two abort races, one signature contract) as golden anchor rows, and verify per-cluster transport reports them at the pre-fix SHAs. G-B (later task) needs defect-positive ground truth.

**Files:**
- Create: `examples/cj43-prefix-goldens.tsv` (anchor rows: `file<TAB>line<TAB>desc`)
- Create: `docs/evals/2026-10-02-cj43-prefix-verification.md` (results only)

**Steps:**
1. In a scratch clone of curated-journal, locate the pre-fix commits (before 99711a4): the importDump abort-race and 3-arg signature eras. Record candidate SHAs.
2. Run current sor per-cluster (`--range <base>...<prefix_sha>`, JEV provider, live) on each candidate; identify the commit where the 3 majors are present as real defects.
3. Record anchors (file + line at that SHA) for: abort-race #1 (stopped-flag), abort-race #2 (cancel handshake), signature contract (importDump arity). Format matches `eval_against_golden` expectations (mirror `examples/cj-field-goldens.tsv` header comments style; **r10 merged form (r9-m2 + addendum, one sentence): rows are exactly `file<TAB>line<TAB>desc` — the parser :1185–1187 skips `#` lines and reads at most three tab-separated fields (a TAB inside a description truncates it; a 4th column would be silently dropped); `verifiability` metadata lives in the eval DOC plus a `#` comment header line in the TSV; anchors marked `unverifiable` stay OUT of the scored TSV (side file — which the G-D band check READS as its input, see step 4) so they never count as misses in later `--golden` runs in Task 8/G-B**). **r8-M2: record each anchor's cluster membership on the CURRENT build too — if any anchor falls inside a >120-line cluster (importMachine.ts-scale), it CANNOT be verified on today's transport (`triage()` :722–725 skips it before any model call); mark it `verifiability: band` and apply step 4's band-verification rule instead of treating it as verified.** The brief (:138, :196, :359) locates the #43 MAJORS but never places a defect in a band cluster — do NOT assert band membership until step 2/3 evidence shows it.
4. Verify: run the CLI golden eval (`--golden examples/cj43-prefix-goldens.tsv`, :1417–1419) against the fixture; **r10-M1: NON-BAND anchors hit (≤1 FP beyond them); BAND anchors are NOT expected to hit on this run — they are recorded `verifiability: band` and verified LATER (G-D's band check, Task 8, on the v08 build). The rev-9 text about "the v08 branch with option 2's ~120-line engagement threshold applied for that verification run ONLY (implementation lands in Task 2 as a one-flag variant)" is RETIRED — Task 2 ships no such flag and Task 0 cannot wait for it; a band anchor that cannot be verified by G-D either (e.g. its cluster never reported) is escalated to Kurt via the band check's UNMEASURED path, never silently treated as hit.** Task 8's G-D band check reads BOTH the scored TSV and the unverifiable side file — `band`-marked anchors are exactly the band check's INPUT (the side file is in-scope, not out of scope). **r11-m4 — BAND anchors live in the SIDE FILE, not the scored TSV: if they sat in the scored TSV, Task 0's own `--golden` recall AND the G-D control arm would count them as misses BY CONSTRUCTION (today's line gate skips their clusters), handing G-B's "defect-positive recall ≥ per-cluster" a free advantage; G-B reports band recall as a SEPARATE line from per-cluster recall.**
5. Commit: `test(fixture): defect-positive CJ#43 pre-fix goldens (anchors recorded; non-band verified)` — the commit message does NOT claim "(3 anchors, verified)" (r10-M1: only non-band anchors are verified at Task 0 time).

**Verification:** eval doc states SHAs, anchors, live-run result; fixture committed.

---

## Task 1: Serialized-size estimator (TOKENS) + Task 1b: serialized census recompute

**Objective:** The shared measurement everything else uses: `estimate_call_size(state, questions)` → estimated TOKENS (state + longest question — the 32k-rule quantity), via `chars / CHARS_PER_TOKEN` (**3.0** — the brief's code-dense-JSON prior; conservative direction, r1-m3; **r7-nit deviation note: the brief :263–264 sums the QUESTION map exactly and estimates only the state — this estimator instead divides the longest question's chars by 3.0 too; that is a DELIBERATE conservative deviation (it over-estimates, never under) — noted here so the brief and code agree on which one is the estimator's contract**) on serialized JSON. Cheap and deterministic.

**Files:**
- Modify: `system_one_reviewer.py` (new function near `jev_ask` ~:157; constants `SOFT_CAP_TOKENS = 28_000`, `HARD_CAP_TOKENS = 56_000`, `CHARS_PER_TOKEN = 3.0` near `MAX_HUNK_LINES` :50 — MAX_HUNK_LINES itself is RETIRED in Task 4)

**Steps:**
1. Failing test (`tests/test_budget.py`, new):
   - `test_estimate_matches_32k_quantity`: build a state + the real 3-question triple; `estimate_call_size` == (len(state_json) + max(len(q_json))) / CHARS_PER_TOKEN (± rounding). The 32k quantity is state+longest-question, NOT the all-questions total (r2-M5).
   - `test_estimate_lower_bounds_full_payload`: estimate(state + longest q) ≤ full payload tokens (state + ALL questions) — documents that the per-call estimate is a lower bound of the wire total (r2-M5); the wire total itself is capped by the HARD_CAP send-gate test in Task 5 (r1-m2).
   - `test_estimate_monotonic`: doubling a state's text roughly doubles the estimate.
   - `test_soft_cap_units`: a state of 100k chars estimates to ~33.3k tokens at CHARS_PER_TOKEN=3.0 > SOFT_CAP_TOKENS (proves the unit is tokens, not chars — the r2-M1 regression guard).
2. Run: `.venv/bin/python -m pytest tests/test_budget.py -q` → FAIL.
3. Implement: serialize state once with `json.dumps`; questions likewise; return (len(state_json) + max(len(q_json) for q in questions.values())) / CHARS_PER_TOKEN. No caching games (YAGNI).
4. Tests → PASS; full suite green (pytest + ruff + mypy — the standard gate from Task 3 onward, r1-m5).
5. Commit: `feat(budget): token-based call-size estimator + 28k/56k token constants`.

### Task 1b: Serialized census recompute (per-cluster wire format — runs where it is placed)

**Objective:** The brief requires a census on ACTUAL SERIALIZED state before implementation. This census measures the SHIPPED per-cluster transport: each oversize file's per-cluster serialized `hunk_state` (`hunk_state-v1` wire format), split-projected with the Task 1 estimator alone (r1-M5 — the units-level census needs Tasks 2/3 and is recomputed for real in Task 8's corpus step).

**Files:**
- Create: `docs/evals/2026-10-02-serialized-census.md`

**Steps:**
1. Read-only script (in /tmp): for every corpus oversize file (incl. `write.rs` 114k chars, `wisdom.ts`), serialize its per-cluster state per `hunk_state-v1` and report: estimated tokens, and the PROJECTED number of soft-cap splits / units per call if the token guard split it (pure arithmetic from the estimator — no product code).
2. Record in the eval doc, labeled `hunk_state-v1 (pre-implementation)`; Task 8 recomputes the same table on the real `ast-units-v1` transport and the two tables are compared.
3. Commit: `docs(eval): serialized-state census — per-cluster split projections (pre-implementation)`.

---

## Task 2: AST unit extraction — Python (stdlib)

**Objective:** `ast_units(path, before_text, after_text, entries)` → for an oversize code-change cluster (r1-M4 criterion: `estimate_call_size > SOFT_CAP_TOKENS`), return sub-clusters whose boundaries land on top-level def/class ends in the post-image; fallback `None` when AST can't help (parse error, non-Python, units don't cover the span).

**Files:**
- Modify: `system_one_reviewer.py` (new function after `package_hunks` ~:697; ALSO factor the anchor chain :633–647 into a shared helper `_cluster_anchor(entries, seg_start, seg_end, hunk_start)` used by BOTH `package_hunks` and sub-cluster assembly — r1-M3)
- Test: `tests/test_ast_units.py` (new)

**Steps:**
1. Failing tests:
   - `test_oversize_python_splits_on_defs`: synthetic .py post-image with 3 top-level functions whose serialized state exceeds `SOFT_CAP_TOKENS` (**r6-M1: ~2,400 changed lines totalling >84k serialized chars at 3.0 chars/token — a 200-line fixture estimates ~3k tokens and is NOT oversize; the old size would contradict `test_oversize_engagement_is_token_based`**) → 3 sub-clusters, each boundary = a function's end line, none mid-function; union of changed lines == original; no line in two sub-clusters.
   - `test_subcluster_inherits_identity`: every sub-cluster carries parent's `file`, `change_type`, and a `parent_cluster` reference; own anchor via the SHARED anchor chain helper (first `+` entry's tracked line → first `-` entry's `e[4]` → context → `hunk_start`); own `line_start/line_end`.
   - `test_deletion_only_subcluster_from_code_change_parent` (r1-M3): a sub-cluster cut from a code-change parent that contains ONLY `-` entries (a removed block between two edited functions) still gets a defined anchor (`e[4]`, the tracked HEAD line — anchor-fallback only, r5-M1) and a correct span; the `-` entries' SYMBOL assignment comes from the PRE-image AST via their `e[1]` old-file lines (r5-M1), matched to the sub-cluster's post-image unit by qualified name.
   - `test_deleted_symbol_forms_own_subcluster` (r6-M2): a removed top-level function (no post-image counterpart) → its `-` lines form their OWN sub-cluster, cut on PRE-image boundaries, anchored via `e[4]`, keeping the parent `change_type`; NOT dropped, NOT dumped into another unit; union == original.
   - `test_renamed_function_old_code_not_lost` (r6-M2): old `foo` renamed to `bar` → the pre-image `foo` code lands in its own pre-boundary sub-cluster (no qualified-name match to `bar`'s unit); union == original.
   - `test_parse_error_returns_none`: post-image that doesn't parse → `None` (caller falls back to line windows).
   - `test_deletion_only_cluster_splits` (r5-M2, brief erratum #2): an OVERSIZE in-file deletion-only cluster HAS a post-image and IS split into sub-clusters — `-` lines assigned via `e[1]` → PRE-image AST. Only `change_type == "whole-file-deleted"` returns `None` immediately (that cluster has no post-image at all; brief req 1's "deletion-only … no post-image" parenthetical is wrong and is logged as erratum #2 alongside the r2-m5 changelog erratum).
   - `test_wholefile_deleted_returns_none`: `whole-file-deleted` → `None` immediately.
   - `test_oversize_engagement_is_token_based` (r1-M4): a cluster under `SOFT_CAP_TOKENS` → `None`; a cluster over it → units. (`FALLBACK_WINDOW_LINES` never appears in the engagement decision.)
   - `test_small_cluster_skipped`: cluster under the size threshold → `None` (AST path only engages for oversize regions).
   - `test_determinism`: same input twice → identical output.
2. Run → FAIL; implement with stdlib `ast.parse` on BOTH images: the `before_text` parameter is PARSED as the pre-image AST (r5-M1: `+` entries map by `e[1]` into the POST-image AST; `-` entries map by `e[1]` into the PRE-image AST — the old-file line advances correctly on deletions — and are matched to the sub-cluster's post-image unit by qualified symbol name; `e[4]` is used ONLY as the anchor fallback, exactly as in main's deletion-anchor rule). **r6-M2 assignment rule for UNMATCHED symbols: a pre-image symbol with no qualified-name counterpart in the post-image AST (deleted, renamed, or moved function) forms its OWN sub-cluster — cut on the PRE-image AST's boundaries, anchored via `e[4]`, keeping the parent `change_type` — never dropped and never dumped into an arbitrary unit (the union == original invariant holds in every case). For a deletion-only parent, cut on the PRE-image AST DIRECTLY (there is no post-image unit worth matching).** Walk top-level nodes with `end_lineno` (3.8+); group.
3. Tests → PASS; full suite green (pytest + ruff + mypy).
4. Commit: `feat(ast): stdlib ast unit extraction for oversize Python clusters`.

---

## Task 3: Tree-sitter lazy import + TS/JS units + line-window fallback

**Objective:** Same contract for TS/JS (the corpus's biggest offenders are .ts) via tree-sitter with a lazy INJECTABLE-LOADER import; and `line_window_subclusters()` — the always-works fallback cutting at blank lines nearest the target, never mid-line.

**Files:**
- Modify: `system_one_reviewer.py` (tree-sitter helper near Task 2's function)
- Test: `tests/test_ast_units.py` (extend)

**Steps:**
1. Failing tests:
   - `test_treesitter_lazy_import_missing`: monkeypatch `sys.modules` to hide tree_sitter → TS file returns `None` (fallback), no exception, no hard dependency at import time of the module itself.
   - `test_treesitter_units_fake_loader` (r1-m6): inject a FAKE loader (the `loader` parameter — same injectable seam `get_laya_router` uses) returning a stub tree-sitter object with canned trees → the TS boundary logic (unit cutting, span mapping, fallback-on-uncovered-span) runs FULLY OFFLINE. CI never installs tree-sitter, so this test — not the skipif one — is what keeps the TS path honest in CI.
   - `test_treesitter_units_when_present`: with tree_sitter installed (skipif-marked — local-only confidence), an oversize .ts fixture (**r7-M1: >84k serialized chars, the token gate — a 200-line file estimates ~3k tokens, can never engage, and the skipif gate hides the conflict from CI**) with 3 top-level functions → 3 boundary-true sub-clusters.
   - `test_line_window_fallback`: an oversize fixture (**r7-M1: >84k serialized changed lines** — same engagement contract as Task 2), no AST at all → sub-clusters ≤ `FALLBACK_WINDOW_LINES` (new constant, default 120 — same number as the retired limit but a NEW name with its own rationale: it is a window SIZE choice, not a skip gate; rationale comment cites that the arbitrary-ness concern was about skipping, not windowing) each, cuts at blank lines where possible, union == original, no overlap, deterministic.
2. Run → FAIL; implement: `tree_sitter = (loader or __import__)("tree_sitter")` inside the function via the injectable loader — NO static `import tree_sitter` anywhere and NO `# type: ignore` (mypy runs in CI on 3.10 with `warn_unused_ignores=true`; a bare import fails CI for missing stubs while a `# type: ignore` fails locally when tree-sitter is installed — r1-m5); grammar loading also lazy per language; fallback cutter shares Task 2's sub-cluster assembly.
3. Tests → PASS (fake-loader tests run in CI; tree-sitter tests skipif); full suite green = pytest + ruff + mypy (r1-m5).
4. Commit: `feat(ast): lazy tree-sitter units (D1) + deterministic line-window fallback`.

---

## Task 4: Triage rewiring — MAX_HUNK_LINES retired, oversize → AST sub-clusters

**Objective:** `package_hunks` stops marking `too_large` for skipping **on the jev path only**; `main()` routes oversize code-change clusters through the Task 2/3 extractor and judges sub-clusters as first-class units. `--max-hunks` becomes units-per-run (ceiling 40, run-level, jev). **Run counters are recomputed in UNITS after expansion (r1-B1)** — the honesty machinery keeps working. **r2-M1/r5-M4: this entire task is gated on `provider == "jev"` — `triage()` gains a `provider` (or `size_policy`) parameter so the gate is MECHANICAL, and LAYA KEEPS TODAY'S EXACT BEHAVIOR: `h[\"too_large\"]` (:696) and the `hunk>` skip append (:722–724) stay live for laya — "MAX_HUNK_LINES retired" means retired FOR JEV; it remains laya's skip gate. Whole-file-deleted clusters that are themselves over-cap keep a deliberate-triage skip under a NEW reason string `whole-file-deleted>cap` (r5-M3: they have no post-image to parse and no lines to window — the alternative, line-window splitting, judges dead context; the skip is deliberate triage feeding `n_triaged` ONLY — r6-m4: `size_skipped_code()` matches `reason.startswith("hunk>")` (:1231), so the new reason is correctly EXCLUDED from the size-skip counter and `n_size_skipped_code`; `gate_run` already admits deliberate skips).**

**Files:**
- Modify: `system_one_reviewer.py` (`MAX_HUNK_LINES` :50 comment→"retired for jev; laya's skip gate" note; `package_hunks` gains an `old_file` field on clusters (r5-m1: rename-from is currently DROPPED at :502 and the old path is overwritten by `+++` at :486–498 — capture it while `---` is parsed; anchors unaffected); `triage()` gains a `provider`/`size_policy` param (r5-M4): the `hunk>` skip append :722–724 runs for laya only, replaced by token-based routing for jev; oversize routing in `main()` — post-triage pre-judge, jev only; `kept.sort`/`kept[: args.max_hunks]` at :1338–1339 replaced; counter block :1337–1340 and Incomplete-verdict block :1370–1374 recomputed in units (**r10-m2: ALSO the meta site :1398 `meta["n_analyzed"] = len(kept)` and its `log_run` write at :1433 — both must carry the r9-M1 post-judge value**); whole-file-deleted over-cap ⇒ deliberate skip `whole-file-deleted>cap` (r5-M3); new `git_show_or_none` helper next to `run_git` :333; argparse `--max-hunks` help text; **r14-m1: ALSO the `render()` Skipped block :1274–1285 — `max-hunks>ceiling` entries get their own "Not judged (run ceiling)" line — AND `scripts/score_corpus.py` (`MISS_BUCKETS` gains `truncated`; `classify_miss` checks the entry reason BEFORE the :71–73 skipped-triage return so ceiling-covered misses land in `truncated`, not `skipped-triage`)**)
- Test: `tests/test_triage_and_failreason.py` (extend), `tests/test_package.py` (extend), `tests/test_sweep.py` (extend) (**r14-m1: ALSO `tests/test_score_corpus.py` — the new `truncated` MISS_BUCKETS bucket changes `test_miss_decomposition`'s exact-dict comparison at :101–103 (gains `"truncated": 0`); the :97 fossil note is about line 97 ONLY, the file is otherwise editable**)

**Steps:**
1. Failing tests:
   - `test_no_hunk_skip_reason_ever_jev` (r5-M4: scoped to jev): any cluster, any size, provider jev → no skip record with reason starting `hunk>` (except the deliberate `whole-file-deleted>cap`, r5-M3).
   - **`test_laya_keeps_size_skip` (r5-M4):** the same oversize cluster under provider laya → whole cluster judged (no AST, no split), a `hunk>` skip record IS appended, `n_size_skipped_code > 0`, and laya's state carries no `ast_context` key. **r6-m1: laya ALSO keeps the size sort and truncate at :1338–1339 (`sort(key=-size)` + `[:max_hunks]`) — order affects what laya drops at the ceiling and the consecutive-failure sequence; the test asserts the kept order is size-descending for laya, while jev's is first-come (r1-m8).**
   - `test_oversize_python_becomes_subclusters`: a >84k-serialized-char Python file (r6-M1 sizing — multiple thousands of changed lines; NOT 273 lines, which estimates ~7–8k tokens and is not oversize) → N judged units, each with own anchor/triple, `parent_cluster` set.
   - `test_oversize_fallback_judged_as_windows`: unparseable oversize (>84k serialized chars, r6-M1) → line-window sub-clusters, all judged.
   - **`test_unit_counters_stay_consistent` (r1-B1 — the BLOCKER regression guard):** 5 clusters, one splitting into 4 units ⇒ `n_dropped == 0`, `n_unjudged == 0`, verdict carries NO "(incomplete" suffix, and the denominator in the verdict/ledger equals the UNIT count (8 of 8), not the parent count. Plus a property assertion: `n_dropped >= 0` for every fixture combination (split, truncate, skip).
   - **`test_gate_run_accepts_v08_split_ledger` (r1-B1):** a v08-ast ledger whose run contains splits passes `gate_run` (non-negative counters, completeness check passes) — the sweep must never again reject a legal split run as malformed. **r10-M2 (SUPERSEDES the r9-m3 variant, which asserted the opposite of the code): `test_gate_run_rejects_parse_error_ledger` — a ledger run with ONE `parse_error` finding is REJECTED by `gate_run` TWICE (`judged` rows exclude parse_error findings :1394 ⇒ `len(judged) == n_analyzed − 1`, so the :98–102 completeness check fires first with the "incomplete — judged has N entries but n_analyzed=N+1" message, and `n_unjudged == 1` would hit the :124 rejection regardless). The test asserts the :98 rejection message and that the run is NOT admitted to sweeps — loosening either gate would readmit incomplete runs (the exact hole the Step 0′ gate closes). The "exclusion from `judged` is BY DESIGN" note stands.**
   - `test_max_hunks_is_run_level`: 3 oversize files × windows with `--max-hunks 40` → nothing dropped file-wise; dropping happens only at the run ceiling, in FIRST-COME-ACROSS-FILES order (r1-m8: file order, then cluster order — NOT `sort(key=-size)`, which can drop arbitrary sub-clusters of one parent), and dropped units produce explicit unjudged records (feeding Incomplete), never a silent file skip. Test asserts the KEPT set equals the first-40 in traversal order (**r9-nit: leaves never compete for these slots — they were set aside BEFORE truncation per r8-M1**).
   - `test_deletion_wholefile_stay_cluster_based`: whole-file deletion (no post-image) → judged as a single cluster (no AST), deletion rubric — **unless it is itself over-cap (r5-M3): then it takes the deliberate `whole-file-deleted>cap` skip instead of a judged call; r6-m4 regression test: the run carries NO "(incomplete" verdict suffix from this deliberate skip and `n_size_skipped_code` does NOT count it. r7-m3 honesty fix: this test PINS the reason string — it adds no behaviour, because a whole-file deletion that gets size-skipped is ALREADY excluded from `n_size_skipped_code` TWICE today (the `"hunk>"` prefix match at :1231 AND the `change_type` filter at :1232–1233).** r2-m4: an in-file deletion-only oversize cluster is NOT this case — it HAS a post-image and is sub-clustered like any oversize cluster, with `-` lines assigned by OLD-FILE symbol (see below).
   - **`test_deletion_run_assigned_by_old_symbol` (r2-M3):** a 3-function rewrite emitted as one `-` block + one `+` block (the `new_line` never advances on `-` entries — :569–572 — so all `-` lines share ONE `e[4]`). Each sub-cluster's before-text must contain the OLD code of its own function (assigned via `e[1]` → PRE-image AST, qualified-name match to the post-image unit), and no sub-cluster may receive another function's old code. `e[4]` remains only the anchor fallback.
   - **Per-mode file sources (r2-M2 — req 1 is binding; r2-m6):** `test_mode_sources_range`: `--range`/`--pr` reads post from `git show <head>:<path>` and PRE from `git show <merge_base>:<path>` — merge base computed here; r2-m6 names the inputs: `--pr` base = `origin/main` (what :412 diffs against), `--range` base = the LEFT side of the range spec (triple-dot parsed; `A..`/`..B` forms tested; implicit HEAD allowed). `test_mode_sources_staged`: post = `git show :<path>`, pre = `git show HEAD:<path>`. `test_mode_sources_uncommitted`: post = worktree read, pre = `git show :<path>`. Each asserts the correct refs are fetched (monkeypatch capture).
   - **`test_missing_images_degrade_not_die` (r1-M2):** for EACH mode: an ADDED file (no pre-image exists), a RENAMED file (pre-image exists only under the old path — the cluster's NEW `old_file` field (r5-m1) carries the rename-from path `package_hunks` now captures; it does NOT come from the diff's carried data alone, which :502 drops), and a BINARY file (no text image) all complete the run — `git_show_or_none` returns None, no `sys.exit`, `-` lines get symbol-free enrichment, and a missing POST-image leaves the cluster whole. (Regression guard for `run_git`'s `sys.exit` at :346.)
   - **Mode-aware content cache (r2-m2 — mode-awareness; NOTE r5-nit: this was mislabeled "r2-m4" before rev 5 — r2-m4 is deletion enrichment):** cache key = `(mode, rev, path)` where rev is the resolved SHA, `:path`-stage, or the worktree sentinel — never bare `(sha, path)`; test that an `--uncommitted` post-image never serves a `--staged` request in one process.
   - Existing tests updated BY DESIGN: `test_triage_size_skip_carries_change_type` (or successors) now assert sub-cluster routing instead of a skip record.
2. Run → FAIL; implement. Per-mode file sources: BOTH images fetched per mode via `git_show_or_none` (hard constraint list above; missing image = degrade, never exit); merge base = `git merge-base <named base> <head>` with the base named per r2-m6 (`origin/main` for `--pr`; left side of the range spec for `--range`; r5-nit: criss-cross histories can yield several merge bases — use the FIRST `git merge-base` result, which matches what `git diff A...B` diffs against). Cache per `(mode, rev, path)` — shared `contexts` table per brief. Counter recomputation: after routing/expansion, `n_units_pre` = number of judgeable units (parents that stayed whole + all sub-clusters + leaves); `n_dropped` and the Incomplete denominator are defined by the r8-M1/r9-M1 formulas below (leaf-aware, two-phase). **r7-M2: the pre-judge expansion is RECURSIVE (fixed order: **step 0 — during POST-ENRICHMENT re-expansion only (r12-n1/r13-n1: units at the initial Task 4 expansion have no `ast_context` yet; and since `test_enrichment_size_bounded` caps context at 40/20 on ATTACHMENT, step 0 is in practice just DROP `ast_context` — the trim wording is kept only as a defensive clamp, no implementer should build a partial-trim loop, which r12-M1 deliberately rules out)** → top-level AST → nested AST → line windows → halving to a single line); an UNSPLITTABLE leaf (a single line whose own estimate still exceeds SOFT_CAP — inline base64, embedded JSON) is never sent and never silently dropped: the expansion sets the leaf aside as an unjudged-leaf record and `main()` appends `{"hunk": <unit>, "parse_error": True, "raw": None}` to `findings` only AFTER `judge()` returns a non-None result (inserting before judge() would send the leaf; a fail-open run's `findings = []` at :1348 correctly discards them). Counters (r8-M1 — `n_leaf_unjudged` is its own count; leaves are EXEMPT from the `--max-hunks` ceiling and set aside BEFORE truncation; r9-M1 — TWO-PHASE, and the phase boundary matters because today `n_dropped` is computed pre-`judge()` at :1340 and must STAY pre-judge): **PRE-`judge()`: `n_units_pre` = whole parents + sub-clusters + leaves; `n_dropped = n_units_pre − n_leaf_unjudged − len(kept)` — computed HERE, never recomputed after judge(). POST-`judge()`: `n_units_total = n_units_pre + added_units`; `n_analyzed = len(kept) + added_units + n_leaf_unjudged`; the Incomplete suffix numerator is `n_analyzed − n_unjudged` (parse-error findings at :1361 plus leaf records — both feed the downgrade trigger); the Incomplete DENOMINATOR is `n_units_total + n_size_skipped_code` — for LAYA the whole scheme collapses to today's legacy formulas (`+ n_size_skipped_code` is the laya-only term; a test reproduces laya's legacy suffix string byte-for-byte). Without the two-phase split, `added_units` would inflate `n_dropped` (5 units, one 400-split into 2 leaves ⇒ `n_dropped == 1`, `gate_run` :124 rejects a legal split, and :1370 adds a false Incomplete suffix). `main()` appends leaf records to `findings` ONLY in the window between :1348 and :1350 (r10-m1: inside `elif hunks:`, AFTER `judge()` returns non-None and BEFORE `judge_pr_level` at :1350 — appending later would hide leaves from `judge_pr_level` (which labels parse_error rows at :1052–1054) and from `compose()` at :1359, gutting the Step 0′ guarantee; a fail-open run's `findings = []` at :1348 correctly discards them). **r14-m2: CEILING-DROPPED units also reach the PR-level digest — `main()` passes `judge_pr_level(findings, ask, size_skipped_code=size_skipped_code(skipped) + [s for s in skipped if s.get("reason") == "max-hunks>ceiling"])` (today's :1352 passes only the `hunk>`-filtered list, and on jev/v08 NO `hunk>` records exist, so a 5-unit ceiling drop would be invisible to the PR-level model — the exact gap the r10-m1 insertion pinning exists to close; NOT a regression vs today, but now it is an EXPLICIT decision); test: a ceiling-dropped run shows those files in the digest with the `unjudged (skipped: max-hunks>ceiling)` label.** Test: a leaf record appears in the PR-level digest (**r11-m1: leaf records carry `"reason": "unsplittable>cap"` and `judge_pr_level`'s :1052 label becomes `unjudged (skipped: <reason>)` when a reason marker is present — the digest must NOT show leaves as "provider call failed", which would be false; the test asserts the skipped-reason string**). **Rendered label (r7-m3, from the r7 review tail; r14-n2 extends it): `render()` :1243 prints `analyzed={meta['n_analyzed']} hunks` and :1244 `skipped={len(skipped)}` — with leaves included "analyzed hunks" overstates what was SENT, and ceiling entries would count as "skipped" triage; the header line is reworded to `analyzed=<n> units (<n_sent> judged calls), skipped=<n> + not-judged-ceiling=<m>` (or equivalent split), and a test PINS the rendered string so the semantics are explicit ("analyzed" = accounted units, not model calls; ceiling drops never count as triage).** Gate impact: none — `gate_run` :98 already rejects leaf-carrying runs (judged is short by the number of leaves) and :124 would reject regardless via `n_unjudged` (leaf records are `parse_error`, excluded from `judged` :1394; r11-m2: the r10 text here said ":98 … via `n_unjudged`" — wrong check; :98 is the completeness mismatch, :124 the unjudged rejection). **r10-m2: the meta/ledger sites are named — `meta["n_analyzed"] = len(kept)` at :1398 (which `log_run` writes at :1433) MUST use the r9-M1 post-judge formula `len(kept) + added_units + n_leaf_unjudged`; if either keeps `len(kept)`, every runtime-split run logs `n_analyzed` short by `added_units` and sweep :98 rejects it. `test_runtime_split_counts_consistent` asserts on the LOGGED record (post-`log_run`), not just the in-memory counters.** Tests: `test_unit_counters_stay_consistent` extends to assert all three counters on a leaf run (`n_dropped == 0`, `n_unjudged == 1` (leaf), `n_analyzed == len(kept) + n_leaf_unjudged`) AND `test_runtime_split_counts_consistent` gains `n_dropped == 0` + NO "(incomplete" suffix assertions on the runtime-split run.** `-`-line assignment uses the PRE-image AST (r2-M3 rule above). The new `gate_run` test passes `packaging_version` EXPLICITLY (r2-m1: sweep defaults stay `v03b` until Task 7).
3. Tests → PASS; full suite green (pytest + ruff + mypy).
4. Commit: `feat(units): oversize clusters → AST sub-clusters; MAX_HUNK_LINES retired; unit-consistent counters (r1-B1); --max-hunks = units-per-run`.

---

## Task 5: Budget guard — send gate + _OverBudget runtime handling

**Objective:** The SEND gate + runtime-400 handling only — **r5-M5: Task 5 does NO proactive splitting** (all proactive trimming/splitting already happened pre-`judge()` in Task 4, re-run after enrichment in Task 6; Task 5 owns the defense-in-depth assert that nothing over-cap is ever sent, and the typed `_OverBudget` runtime-400 path: raised INSIDE `jev_ask`, halve-and-retry driven by `judge()`, depth-capped, one-attempt accounting, unjudged at the leaf). **r5-m6 — `judge()`'s return contract is now `(findings, latencies, meta)` where `meta = {"added_units": N, "avg_input_tokens": float|None}`: `added_units` feeds the POST-`judge()` quantities `n_units_total`/`n_analyzed` in `main()` (runtime-split counter consistency — r9-M1: `n_dropped` is computed BEFORE `judge()` and is never touched by `added_units`; `n_units_total = n_units_pre + added_units`), `avg_input_tokens` comes from the payload's `usage.input_tokens` (jev only — laya payloads carry no `usage`, so it is `None` for laya); EVERY caller and every test stub updated.** **r6-m3 runtime-split mechanics: `judge()` has no pre/post images and no extractor (those live in `main()`), so `main()` INJECTS a `split_unit` callable (closing over the fetched images + Tasks 2/3 extractors + trim helpers); when the callable is `None` (or the unit cannot be split further), the unit is marked unjudged — never a crash. And `judge()` must catch `_OverBudget` BEFORE its generic `except Exception` (:954) — otherwise the over-budget error counts as an ordinary call failure and inflates the consecutive-failure counter.**

**Files:**
- Modify: `system_one_reviewer.py` (`jev_ask` :157–193 — `_OverBudget` raised at the `resp.status >= 400` branch next to `_NoRetry` :179–183; `judge()` ask loop :950–965 — `payload, ms = ask(...)` at :951, split loop lives here, `_OverBudget` caught BEFORE the generic `except Exception` :954 (r6-m3), `split_unit` injected parameter; `_NoRetry` neighborhood :148 for the `_OverBudget` class)
- Test: `tests/test_budget.py` (extend)

**Steps:**
1. Failing tests:
   - `test_over_softcap_never_reaches_judge` (r5-M5 rewrite of the old proactive-split test): the pre-judge expansion (Task 4/6) already guarantees every unit's estimate ≤ SOFT_CAP; this test asserts the pre-judge pass output contains no over-cap SENT unit, and that `judge()` itself receives only legal payloads (stub-transport capture). **r7-M2: the expansion is RECURSIVE with a FIXED order per over-cap unit — top-level AST → nested AST re-split → line windows (`FALLBACK_WINDOW_LINES`) → halving down to a single line — because no single cut guarantees the cap (`FALLBACK_WINDOW_LINES = 120` alone does not: 120 lines × 800 chars ≈ 32k tokens). The test asserts no over-cap unit reaches the transport EXCEPT via the unsplittable-leaf unjudged record below.**
   - **`test_single_oversize_line_marks_incomplete` (r7-M2):** a diff whose oversize cluster reduces to ONE unsplittable line (an inline base64 data URL / embedded JSON blob >84k chars on a single line — the brief :121 explicitly expects oversized single statements) → the run completes, NO crash, NO over-cap send; the leaf appears as an unjudged record `{"hunk": <unit>, "parse_error": True, "raw": None}` in the findings stream so `n_unjudged` (:1361) counts it and the verdict carries the "(incomplete" suffix; assert `n_dropped == 0` (this is NOT `--max-hunks` truncation — a silent `n_dropped` hit would mislabel the coverage loss) and `n_unjudged == 1`.
   - `test_runtime_400_max_tokens_splits`: stub transport returns 400 `max_tokens_exceeded` once, then 200 → retry happens with halved payload; attempt counter sees ONE attempt; `_OverBudget` never escapes.
   - `test_overbudget_raised_in_jev_ask_not_wrapper` (r1-m4): the 400+`max_tokens_exceeded` body surfaces as `_OverBudget` from `jev_ask` itself (not a wrapper around module-level `ask()` — `ask()` serves both providers, so a wrapper there is not JEV-only per D6); `_OverBudget` is re-raised untouched by `jev_ask`'s handler exactly like `_NoRetry` and is never given the 5xx retry; a laya-path call can never observe `_OverBudget`. **r8-m1 mechanics: `jev_ask` :181 raises `_NoRetry` for EVERY status < 500 BEFORE any body inspection, and :189's `except Exception` retries — so a plain-Exception `_OverBudget` would be retried once (a wasted over-budget resend) and its check would never fire unless ordered before :181. Fix: the `max_tokens_exceeded` body check runs BEFORE the :181 `_NoRetry` raise (inspect `raw` on the >=400 path), and `_OverBudget` is made a SUBCLASS of `_NoRetry` (the r6-m3 catch order in `judge()` — `_OverBudget` BEFORE generic `Exception` — still applies, and subclassing preserves `_NoRetry`'s no-retry semantics mechanically); `test_overbudget_raised_in_jev_ask_not_wrapper` extended to assert only ONE request is sent (no retry on the over-budget 400).**
   - `test_budget_termination_bounded`: transport always 400s → the split recursion terminates in bounded attempts (test the recursion helper DIRECTLY on synthetic multi-unit input — r2-m2: the ⌈log2(24)⌉+1 depth bound belongs to multi-unit batched calls, not this plan's 1-unit-per-call transport; the property tested here is "terminates, unit marked unjudged, run continues, no infinite loop, no fail-open").
   - `test_other_400_still_NoRetry`: 401 → `_NoRetry` immediately (existing behavior intact).
   - `test_send_payload_under_hard_cap` (r1-m2): the SEND gate asserts state + ALL questions ≤ `HARD_CAP_TOKENS` (the wire-total rule the brief :273–274 requires) — a payload over the hard cap is never sent; over-hard-cap ⇒ split, same machinery as soft cap. **r2-m2: the test uses SYNTHETIC oversized questions (once state + longest ≤28k, real questions cannot exceed 56k — the check is defense-in-depth and is labeled as such).**
   - **`test_judge_return_contract` (r5-m6):** `judge()` returns `(findings, latencies, meta)`; `meta["added_units"] == 0` on a clean run and `leaves − 1` (NET) after a runtime split **(r7-m1: the over-budget parent is REPLACED, not kept — `judged = len(kept) − 1 + leaves`, so only `leaves − 1` is "added"; the raw leaf count makes `len(judged) != n_analyzed` and `gate_run` :97–102 would reject every legal runtime-split run while `test_runtime_split_counts_consistent` demands consistency on; r10-nit: the base text now states the corrected definition directly)**; `meta["avg_input_tokens"]` is a float for jev (stub payload carrying `usage.input_tokens`) and `None` for laya (payload without `usage`); every existing caller/stub updated to the 3-tuple. **r6-m2: EVERY early-return path too — `judge()`'s three fail-open returns (today `(None, latencies)` at :959/:1025/:1035) become `(None, latencies, meta)`; the existing 2-tuple unpacking stubs (tests/test_triage_and_failreason.py :24/:34/:42/:176, test_package.py :341, test_line_span.py :42) are all updated in the same commit; a test asserts a fail-open run unpacks 3-tuples at every call site and reports Unavailable (never a ValueError crash). r7-m2: the stub updates are SIGNATURE changes, not just return-value changes — `main()` passes `split_unit=…`, so a bare `fake_judge(kept, ask, errors=None)` (test_line_span.py:42, test_triage_and_failreason.py:176) raises TypeError on the new keyword; `judge()` takes `split_unit` KEYWORD-ONLY with default `None` and the stubs gain the parameter.**
   - **`test_runtime_split_counts_consistent` (r2-M2):** a run where one unit 400s then splits at runtime ⇒ `judge()`'s `added_units` report makes `len(judged) == n_analyzed` (the completeness check :97–102 passes), each split leaf is its OWN judged entry (never merged), and the Incomplete verdict does not fire from a legal runtime split. **r9-m1: the test additionally asserts `n_dropped == 0` (the r9-M1 two-phase formula keeps `added_units` out of `n_dropped` — today's :1340 pre-judge computation, extended per Task 4, must not be recomputed post-judge) and NO "(incomplete" suffix (:1370 would otherwise add one when `n_dropped`/`n_analyzed` drift).**
   - `test_consecutive_accounting_single`: a full over-budget chain counts once toward consecutive failures (brief r3-M5).
   - **`test_input_tokens_logged` (r2-M4):** a successful call's `usage.input_tokens` from the payload reaches the ledger (`avg_input_tokens` in log_run via `judge()`'s meta); the chars-per-token recalibration story depends on it; laya runs log `None`.
2. Run → FAIL; implement.
3. Tests → PASS; full suite green (pytest + ruff + mypy).
4. Commit: `feat(budget): send gate + typed _OverBudget runtime split with injected splitter and depth-capped termination` (r6-nit: the old message said "proactive 28k split" — Task 5 no longer does that).

---

## Task 6: AST context enrichment (Arch 2 enclosing-symbol enrichment, default path per D3)

**Objective:** Each unit's `hunk_state()` gains read-only AST context: enclosing symbol chain (e.g. `Class.method`) and the file's top-level symbol table (name → signature line). Enrichment is text-only context — no merged units, no question changes. **Per-unit `enrichment` recorded in `judged` (r1-M1):** enrichment availability varies by language and machine, so each judged entry carries its own enrichment value; the run-level D7 stamp stays. **r2-m5 label fix: this is Arch 2's enclosing-symbol enrichment. Arch 3 (call-graph enrichment: callers/callees) is UNPROVEN AND DEFERRED per the brief (:124–127, :233–236) — no call-graph work belongs to this task.** **r2-M2: after enrichment, RE-run the soft-cap estimate on every unit and RE-expand (same Task 4 machinery) BEFORE `judge()` — the plan's own `test_budget_interaction` proves enrichment can push a unit over the cap, and the re-expansion must happen pre-judge, not inside it.** **r2-M1: jev-only — laya receives today's states, never enriched ones.** **r11-M1 — PIPELINE ORDER is FIXED and binding (the natural implementer reading — Task 6 code landing after Task 4's :1340 freeze — produces `n_dropped = −1` when enrichment pushes a unit over cap and re-expansion grows `len(kept)` past the frozen `n_units_pre`, which sweep :116–123 rejects as malformed and which can also breach `--max-hunks` 40; leaves appearing only during re-expansion would be missing from the frozen `n_leaf_unjudged`). The jev pipeline runs, in order: (1) route + expand (Task 4 machinery, unenriched); (2) attach `ast_context` (jev only, unless `--no-enrichment`); (3) re-estimate and RE-expand (same machinery; step 0 of the re-expansion order: DROP `ast_context` entirely (r14-n1: in practice just a drop — context is already clamped to 40/20 on attachment; the "trim" wording is only a defensive clamp, no partial-trim loop is built — r12-M1 rules that out) — r11-m5: each child inherits the file symbol table, so halving never shrinks that part and an enriched unit needing only a trim could otherwise recurse to an unjudged single-line leaf); (4) set leaves aside; (5) truncate to the `--max-hunks` ceiling (**r12-m2, CORRECTED by r13-M1: `n_units_pre = len(pre-truncation unit list) + n_leaf_unjudged` — recorded after step (4), BEFORE the ceiling cut, with leaves ADDED BACK because the formula `n_dropped = n_units_pre − n_leaf_unjudged − len(kept)` assumes `n_units_pre` CONTAINS them; the literal "len of the list" reading gives `n_dropped = 5 − 1 − 5 = −1` on a 5-unit+1-leaf run, which sweep :116–123 rejects as MALFORMED (the r1-B1 class) and whose verdict would read "5 of 5" while a leaf went unjudged. `n_dropped` itself is computed at the :1340 position AFTER truncation. Property check in `test_max_hunks_is_run_level`, leaf-INCLUSIVE: 45 units + 2 leaves, ceiling 40 ⇒ `n_dropped == 5`, denominator 47, `n_dropped ≥ 0`**); (6) freeze `n_dropped`; (7) `judge()`.** **r12-M1 CORRECTION to the r11-M1 step-3 logic (r10 review): since every non-leaf unit leaving step (1) is already ≤ SOFT_CAP unenriched, and `test_enrichment_size_bounded` caps `ast_context` at 40/20 on attachment, a step-3 over-cap unit is over cap ONLY because of its context — so the re-expansion order ALWAYS TERMINATES AT STEP 0: the context is dropped, the unit returns to its ≤cap step-(1) state, and NO split happens. Enrichment can never cause a split on the jev path — the freeze-ordering rule (steps 4–6 before judge()) stands as a GUARD, not as the path a real split takes; the r11-m5 leaf-recursion hazard is thereby prevented by construction. If a partial trim (e.g. symbol-table-only) that permits splitting while keeping some context is ever wanted, that is a NEW design decision requiring Kurt's ruling — NOT implemented here. Per-unit `enrichment` flag when context is dropped (r12-M1): the unit logs `enrichment: none` in its judged entry — the flag records whether context is PRESENT in the judged state, never whether it was attempted; a dropped unit must not log `ast` with no context in its state (that would corrupt the r1-M1 flag and G-D's enrichment-off comparison).** Tests rewritten per r12-M1: `test_enrichment_reexpansion_before_freeze` — enrichment pushes 1 of 5 units over cap → that unit's context is DROPPED → `len(kept)` unchanged, `n_dropped == 0`, the unit's judged entry says `enrichment: none`; `test_budget_interaction` — a state with huge enrichment trips the soft cap → CONTEXT DROPPED, NOT SPLIT.

**Files:**
- Modify: `system_one_reviewer.py` (`hunk_state` :884 — reads `ast_context` from the cluster/entry WHEN PRESENT; the enrichment MECHANISM (r5-m3): `main()` attaches `ast_context` to each unit after pre-judge expansion, ONLY when `provider == "jev"` (and not `--no-enrichment`), so `hunk_state` itself stays provider-agnostic and a laya state NEVER carries the key — tested; judged-entry builder — per-entry `enrichment` field)
- Test: `tests/test_enrichment.py` (new)

**Steps:**
1. Failing tests:
   - `test_enrichment_present_for_python`: unit inside a class method → `ast_context` contains enclosing chain + symbol table; keys absent (not None-valued) when unavailable.
   - **`test_no_enrichment_flag` (r5-m2):** `--no-enrichment` (new argparse flag) → `main()` never attaches `ast_context`, every judged entry logs `enrichment: none` — the flag exists so Task 8's MANDATORY enrichment-off arm can run; it is a measurement knob, not a user feature.
   - **`test_laya_states_never_carry_ast_context` (r5-m3):** a full laya run → no unit state contains the `ast_context` key (the mechanism-level guard behind the r3 finding).
   - `test_enrichment_absent_for_wholefile_deletion`: whole-file-deleted cluster (no post-image at all) → no `ast_context`. **r2-m4: in-file deletion-only clusters DO have a post-image and ARE enriched — from the PRE-image symbol map (`-` lines map to their old-file enclosing symbols; the PRE-image already fetched in Task 4 for `-`-line assignment serves double duty). Deletion clusters are the ones that benefit most — test that a deletion-only unit's `ast_context` names the old-file symbols whose code was removed.**
   - `test_judged_entry_carries_enrichment_flag` (r1-M1): a run mixing enriched (Python) and unenriched (e.g. binary) units produces judged entries whose per-entry `enrichment` values differ correctly; the run-level ledger stamp is `ast` when ANY unit enriched.
   - `test_enrichment_size_bounded`: symbol table truncated deterministically at 40 symbols / unit context ≤ 20 lines (keeps budget headroom).
   - `test_budget_interaction`: enrichment counts in `estimate_call_size` (a state with huge enrichment trips the soft cap → **r12-M1: CONTEXT DROPPED, NOT SPLIT — the over-cap cause is the context itself; dropping restores the ≤cap unenriched state**).
2. Run → FAIL; implement (stdlib ast for Python; tree-sitter when present via the injectable loader; omit otherwise).
3. Tests → PASS; full suite green (pytest + ruff + mypy).
4. Commit: `feat(enrichment): AST enclosing-symbol + file symbol table on unit states (D3, per-unit ledger flag)`.

---

## Task 7: Ledger contract (D7) + PACKAGING_VERSION bump

**Objective:** Every run stamps `transport` (`per-cluster`), `wire_format` (`hunk_state-v1` when no AST engaged, `ast-units-v1` when any unit came from AST), `enrichment` (`none`/`ast`); `PACKAGING_VERSION` → `v08-ast`; sweep-thresholds recognizes it.

**Files:**
- Modify: `system_one_reviewer.py` (`PACKAGING_VERSION` :71; result/log_run block ~:1399); `scripts/sweep-thresholds.py` — ALL v03b default sites (r2-m1): `RUBRIC_VERSIONS` :41, `gate_run` default :72, `select_runs` default :158, `select_field_runs` default :418, `--packaging-version` argparse default :570
- Test: `tests/test_package.py`, `tests/test_sweep.py` (extend)

**Steps:**
1. Failing tests: version string asserted in ledger from a `main()`-level run; sweep admits `v08-ast`; ALL four DEFAULT-carrying sites updated (:72 `gate_run`, :158 `select_runs`, :418 `select_field_runs`, :570 argparse — a test asserts each site's default reads `v08-ast`, so no straggler can silently gate v08 runs out; r8-m2: "five"→"four" — :41 `RUBRIC_VERSIONS` holds versions, not a default, and is extended not flipped); **`RUBRIC_VERSIONS` :41 is EXTENDED to `{"v03b", "v08-ast"}`, NOT overwritten (r5-m5: it feeds the `rewrap()` guard at :189–202 — replacing v03b would silently stop rejecting malformed v03b judged entries; test asserts the set EQUALS `{"v03b", "v08-ast"}`)**; old-version ledgers still gate under explicit `--packaging-version v03b` (the ONLY previously stamped value — `v06-postmerge` is a corpus run LABEL in the brief, not a packaging version; there are no v06/v07 records to test against, r1-m1).
2. Implement.
3. Full suite green (pytest + ruff + mypy).
4. Commit: `feat(ledger): D7 contract stamps + v08-ast packaging version`.

---

## Task 8: Fixture stability + corpus replay gates (G-A, G-D) + threshold re-sweep

**Objective:** Prove coverage and stability: (G-A, jev) zero `hunk>` skips on the corpus; `write.rs`-class files split and send within budget; (G-C, r2-M3) the 5 defect-free merged CJ heads stay at ≤1 reported FP major each — the over-report gate G-B's defect-positive arm does NOT cover; (G-D, r5-M4) new-transport vs old-transport agreement ≥ baseline, measured with THREE arms (control + live are MANDATORY; enrichment-off is required to run, via the flag) — a **contemporaneous CONTROL arm** (current main build, v03b transport, LIVE model, 3 repeats, same samples — same-day model state, so model drift cannot masquerade as a transport regression; the stored v06-postmerge ledgers are demoted to a sanity reference only, r5-M6) and a **live re-call arm on the v08 build** (r2-M4: the replay-only idea proved nothing — replaying unchanged inputs agrees 100% by construction, and Python clusters are ALWAYS enriched, so the clusters whose transport actually changed got no comparison); v08 gates against the CONTROL arm; and the **enrichment-off arm** (`--no-enrichment`, r5-m2; origin r2-m4) isolates enrichment's effect from the split's. Plus the **v08 threshold re-sweep (r1-M1)**: the 0.50/0.70 values were calibrated on unenriched v03b states; re-run the sweep on v08 fixtures before landing and record whether the calibrated values still hold. The baseline for all arms comes from repeats run IN THIS TASK (r5-nit: previously mislabeled as "r2-m3" — that tag is the ast_context trim order); the stored v06-postmerge 36×3 ledgers serve as the cross-era sanity reference. The units-level split census (r1-M5) is recomputed here on the real `ast-units-v1` transport and compared against Task 1b's pre-implementation projections.

**Files:**
- Modify: fixture/golden TSVs only if anchors shift (they shouldn't — cluster anchors unchanged for ordinary clusters)
- Create: `docs/evals/2026-10-02-ast-units-ga-gd.md`

**Steps:**
1. Fixture run (v08): all fixtures judged or deliberately triaged (r5-M3's `whole-file-deleted>cap` is a legitimate deliberate skip), no `too_large` skips, verdicts byte-comparable modulo documented differences; TP/FP stability tied to G-D's repeat protocol — the fixture set is run 3× (same repeats mechanism) and counts as stable if 2 of 3 repeats agree exactly (r2-n2).
2. Corpus replay: `run_corpus` on the v08 build; census recompute — 0 size-skips; write.rs/wisdom.ts-class files produce send-legal batches (units-level numbers cross-checked against Task 1b's projections).
3. **G-C:** run the 5 CJ heads (`examples/cj-field-goldens.tsv`) on the v08 transport — each stays ≤1 reported FP major (the AST-split machinery turns previously-skipped files into findings on CLEAN heads; this is where that would bite). **r6-M1 sub-measure (mandatory): for each CJ head, separately report verdict changes on clusters in the 121-line…84k-char band — previously SKIPPED by the line gate, now judged WHOLE under the token gate — so a recall drop on that band is visible and cannot hide. r7-M3 scope note: G-C's heads are DEFECT-FREE, so this sub-measure can only surface FALSE POSITIVES here — recall evidence comes from G-D's defect-positive band check (step 4).**
4. **G-D (r2-M4 + r5-M4/M6 — three arms, control + live are MANDATORY):** (a) **CONTROL arm:** current main build (v03b transport), LIVE model, 3 repeats, same samples — contemporaneous with the v08 runs, so same-day model state; the agreement BASELINE is computed from these repeats (v06-postmerge stored ledgers = cross-era sanity reference only). (b) **v08 live arm:** the v08 build, LIVE model, same samples — verdict-agreement + findings-Jaccard vs the control baseline. **r8-M2 — defect-positive BAND check (mandatory, runs in G-D on the v08 arm; REVISED definition per r8-M2): a golden is a HIT when its line falls INSIDE the cluster's span (`line_start ≤ g ≤ line_end` — `_span` already writes both to `judged`) AND the cluster is reported. The ±1-anchor result (eval_against_golden :1193 matches on the cluster's single anchor only, so any defect more than one line below the anchor is a geometric miss regardless of model output) is reported SEPARATELY, information-only — it measures matcher geometry, not recall, and NEVER triggers anything. TRIGGER: if ANY band golden is MISSED on the span-containment criterion, STOP — do not land — and take option 2 (a separate ~120-line AST engagement threshold) back to Kurt with the missed-anchor data; that data point is what the pending-ruling resolves on. If ZERO goldens fall in band clusters, band recall is UNMEASURED — do not count the check as passed; escalate to Kurt alongside the pending-ruling question with the no-evidence note. Multiple goldens in ONE band cluster: credit AT MOST ONE golden per reported cluster (greedy assignment, the eval_against_golden :1197–1202 pattern); a cluster containing >1 golden means band recall is only PARTIALLY unmeasured — report it and send it to the same escalation path as zero band goldens.** (c) **enrichment-off arm (mandatory; origin r2-m4, flag from r5-m2):** v08 with `--no-enrichment`, isolating enrichment's effect from the split's. Runs affected by the truncation-order change (r1-m8: size-sorted → first-come) are reported SEPARATELY from unchanged-order runs so the two effects never blend. Skipped-case improvements exempt. **r8-m3: per arm, report any runs EXCLUDED for `n_unjudged > 0` (minified/base64 over-cap leaves) — `gate_run` :124 rejects them, which honestly shrinks each arm's population; control vs v08 must be compared on the SAME surviving sample set, and an exclusion differential between arms is itself reported. **r10-m3: the G-D sample set EXPLICITLY includes the Task 0 CJ#43 pre-fix run (`--range <base>...<prefix_sha> --golden examples/cj43-prefix-goldens.tsv`) on BOTH control and v08 arms, 3 repeats — nothing else guarantees the band check's defect-positive input is in G-D's sample set at all.**
5. **Threshold re-sweep (r1-M1):** sweep on v08 fixtures; if the 0.50/0.70 values no longer hold, STOP and take the new numbers to Kurt before landing (threshold change = ruling-class decision).
6. Any gate failure → stop, diagnose, fix, re-run. No partial claims.
7. Commit: `docs(eval): G-A coverage + G-C FP regression + G-D replay + v08 re-sweep results (v08-ast)`.

---

## Task 9: G-B per-file batching gate (evidence task, may NEGATE the feature)

**Objective:** Run the G-B A/B exactly as the brief specifies (three arms: per-cluster baseline, per-cluster+enrichment, per-file-batched+enrichment; fixture-self calibration first; defect-positive arm must hold recall). Default outcome per D5: per-file batching stays OFF unless every pass criterion is met.

**Files:**
- Create: `docs/evals/2026-10-02-gb-batching-gate.md`
- **Out-of-tree harness (r2-B1): `/tmp/gb_harness.py`** — experiment scaffolding in the S1′-probe style (that is exactly how S1′ ran the per-file arm). NEVER ships and never lands in the PR. It DOES import the working tree's own functions — `hunk_state`/`ast_units` — read-only (r1-m7: it modifies nothing and commits nothing; "out-of-tree" refers to where it LIVES and whether it SHIPS, not to zero imports), and calls `jev_ask` directly. It builds the per-file wire format from the brief (`{"file", "units", "contexts"}` object state + `u<N>_*` triples per D8, 24-unit batch cap). Scaffolding is required because the gate needs the batched arm's numbers BEFORE any batching transport can be justified for the product.
- Create (only if G-B PASSES): batching transport code in a follow-up plan

**Steps:**
1. Calibration run: per-cluster vs per-cluster on the 20–40-cluster fixture (includes multi-cluster files AND split clusters) → measure the fixture's own |Δ| noise, flip rate, sign distribution.
2. Treatment arms: per-cluster+enrichment vs per-file-batched+enrichment (harness provides the batched arm).
3. Apply ALL pass criteria: gate-flip ≤5% and within calibration margin; verdict-level flip = 0 across fixture PRs; signed-bias |mean Δsev| ≤ 0.05 AND sign test p > 0.05 (must beat the S1′ −0.55 prior); Δis_real signed test near both rubric thresholds; defect-positive arm recall ≥ per-cluster.
4. Record verdict. If FAIL (expected given S1′): document; per-file batching remains retired; done — no code.
5. Commit: `docs(eval): G-B batching gate — <PASS|FAIL> with full criteria table` (harness stays out of the commit).

---

## Task 10: README + Opus review + land

**Objective:** Ship it.

**Files:**
- Modify: `README.md` (units + budget + enrichment section; tree-sitter optional note per D1; new `--max-hunks` semantics)

**Steps:**
1. README section + constraint checklist appended to the brief's verification section.
2. Push branch; PR to main; dispatch Opus review of the full diff (doc-mode loop until APPROVE / APPROVE WITH NITS).
3. Address findings; land per the dual-review-cycle.

---

## Gate → Task map

| Gate | Criterion | Where |
|---|---|---|
| G-A | Zero hunk>120 skips (jev); write.rs-class sends legal | Task 1b (pre-census) + Task 8 (final) |
| G-B | Per-file batching adoption (expected: stays retired) | Task 9 (out-of-tree harness) |
| G-C | 5 clean CJ heads ≤1 FP major each | Task 8 |
| G-D | Live v08 vs contemporaneous live v03b CONTROL (3 repeats each, same-day model); enrichment-off arm isolates enrichment; v06 stored ledgers = sanity reference only | Task 8 |
| Re-sweep | 0.50/0.70 thresholds hold on v08 state distribution | Task 8 |
| Fixture | Defect-positive golden — non-band anchors verified at Task 0; band anchors verified in G-D | Task 0 |

## Risks / notes

- **Anchor drift:** ordinary (non-oversize) clusters keep their ANCHORS, spans, and cluster identity byte-identical — asserted in Task 4 tests. Their STATES are NOT untouched: Task 6 adds `ast_context` to ordinary clusters too (D3 default path), so golden comparability for ordinary clusters is structural for anchors only; state-level comparison is G-D's job (control arm + enrichment-off arm, r5-M4).
- **Split inflation:** more units = more calls on oversize files. Accepted: time policy is none (Kurt ruling); cost logged via input_tokens.
- **write.rs (114k chars)**: exercises the depth cap for real. Task 8 includes it explicitly.
- **The 121-line…84k-char band (r6-M1, pending-ruling):** clusters in this band were skipped under the line gate and are now judged as ONE whole call with a single anchor (wisdom.ts never splits; importMachine.ts-scale evidence sits below the token gate). Mitigation implemented: fixture resize + the G-C sub-measure (FP-only evidence — r7-M3) + G-D's defect-positive band check with the MISS ⇒ STOP trigger (r7-M3); revisit option 2 (separate engagement threshold) if gate data shows recall drop. See the Rev 6 header for the full numbered options Kurt holds.
- **Laya regression risk (r5-M4 corrected):** near-zero, and now MECHANICAL — the AST/budget path is gated on `provider == "jev"` via `triage()`'s size_policy param and `main()`'s enrichment attachment; laya keeps `MAX_HUNK_LINES` skips + whole-cluster judging. One honest correction (r3-M4): the r1 claim "the split loop runs in `judge()`, which laya's transport never enters" was FALSE — laya runs through `judge()` too (:1343); the real laya safety is the provider gate (no sub-clusters/`ast_context` ever created) plus `_OverBudget` being raisable only inside `jev_ask`, which laya's transport never calls.
- **Tree-sitter wheel choice** (tree-sitter-languages vs per-language): verify maintained wheel at implementation time (brief req 6); either way the import stays lazy, loader-injected, and optional.
- **Fossil-string tests (r5-m7):** `test_render_collapses_duplicate_skips` (tests/test_triage_and_failreason.py :222–229) hardcodes `"hunk>120 lines"` — it STAYS VALID as-is (r5-m7: laya still emits that string, so it remains a live expectation, not a fossil); do NOT update it. `tests/test_score_corpus.py:97` also contains the string as OLD-LEDGER fixture data exercising the back-compat path — intentional, leave as-is with a comment.
