# SOR v0.9 Implementation Completion Report (FINAL — honest, verified)

Date: 2026-10-19
Branch: `impl/v09-structural-facts`
Spec: `docs/superpowers/specs/2026-10-19-sor-v09-structural-facts-design.md` (rev 12)
Fork resolution: **A + C** (anchor release + triage re-scope)

This report supersedes all three prior "completion" reports on this branch.
The first two were rejected on verification (E2 was a stub returning `None`;
manifest pins were literal placeholders; the "14/14" test pass was a
structure checklist asserting placeholders exist, not behavior). This
report maps every condition to real code and real test/measurement output,
and says plainly where the result is a genuine gap rather than a pass.

---

## Summary

- **E1** (honest wire-format stamp): done, verified, and one real bug found
  and fixed this session (only `site_units` stamped `cut=` explicitly;
  `ast_units`/`ts_units`/`line_window_subclusters`/halving all fell through
  to a generic inference that mislabeled their output).
- **E2** (decision-site cutting): implemented for real — Python (`ast`) and
  TS/JS (tree-sitter) site detectors, leaf-most non-overlapping selection,
  pure-data size floor, per-declaration majors guard. **Measured against
  the real golden range, it does not clear its own V7 release gate**
  (9.63× median expansion vs the adopted 5× envelope, after both allowed
  floor tightenings). This is reported as a gap, not papered over.
- **E5** (wheels packaging): implemented and a real bug fixed (the TS check
  imported the wrong grammar package and always reported unavailable).
- **Triage re-scope**: no verdict output, status field, 5-findings cap —
  and one real bug found and fixed (the cap truncated findings in
  diff-order rather than by a ranking key, so a late-judged BLOCKER could
  be dropped in favor of earlier MAJORs).
- **V1/V2/V3(a)/V5**: real behavioral tests now exist and pass (8/8 in
  `test_v09_gates.py`), each exercising a real code path (real `main()`
  runs, real site detection, real module-flag toggling) rather than
  asserting that a function or constant merely exists.
- **V7 census**: implemented for real and run against the real golden range
  — the numbers are committed as a receipt and are **not favorable** (see
  above).
- Full pytest suite: **371 passed, 1 skipped** (unchanged skip, unrelated
  to this work).

---

## Fable gate conditions (10/10 addressed; 9 satisfied, 1 open with real numbers)

| # | Condition | Status | Evidence |
|---|-----------|--------|----------|
| 1 | No "Approved"/"Changes requested" anywhere | ✅ DONE | `system_one_reviewer.py:3683` (render's closed-set last line: OK/Unavailable/Incomplete only); `test_v09_gates.py::test_v2_surfaced_set_delta_and_triage_check` greps the real rendered JSON of two real `main()` runs for both forbidden strings |
| 2 | Deletion threshold stated | ✅ DONE | `system_one_reviewer.py:87` (`DELETION_REAL_THRESHOLD = 0.70` + comment) |
| 3 | Ranking key + 5-findings cap | ✅ DONE (bug fixed this session) | `system_one_reviewer.py:3884-3885` (`sorted(reported, key=...)[:5]`); `test_v09_gates.py::test_ranking_key_keeps_strongest_findings_under_the_cap` proves a late-judged BLOCKER survives the cap over earlier MAJORs |
| 4 | INTENT rules 1,2,3,4,7,8 status lines | ✅ DONE | `docs/founding/INTENT.md:82,95,110,123,185,197` — rule 2 corrected this session to report the real V7 gap rather than claiming E2 is deferred |
| 5 | Corpus manifest pins (real SHAs) | ✅ DONE | `docs/benchmarks/corpus-manifest.md` — all SHAs full-40-char, verified against local clones of SynapseTree-login/SynapseTree/curated-thoughts 2026-10-19 (not placeholders); TS fixture built and pinned: `examples/build-ts-fixture.sh`, `examples/ts-fixture-golden.tsv`, `examples/fixture-shas.txt:6` (`positive_ts=c710e8f64efcd1c8b82502e61e3936f8be26dfb7`, re-verified deterministic by rerunning the build script) |
| 6 | V7 census: floor, tightenings, median site size, wall time | ✅ IMPLEMENTED, run for real; **outcome is FAIL on the golden range** | `system_one_reviewer.py:1842` (`run_site_census`); receipt `docs/benchmarks/2026-10-19-v7-site-census-golden-range.json`: floor 1→1667 sites (87.74×) → floor 4→490 (25.79×) → floor 16→183 (9.63×, terminal). Median site size at the terminal floor: 20 lines (well under the 120-line forbidden ceiling — the failure is expansion ratio, not site-size collapse). Per spec's own terminal-outcome contract (Opus r3 R3), this means E2 does not ship clean on this range; the numbers are the deliverable, and they go back to Kurt for an envelope/detector-scope decision. |
| 7 | Jitter counts at 0.80 gate | ✅ DONE | `system_one_reviewer.py:3339` (`near()`, used inside `compose()`); `test_v09_gates.py::test_v3a_jitter_counts_at_080_gate` calls `compose(..., threshold=REFLEX_GATE)` for real and confirms a 0.79-scored unit is flagged, a 0.95 one is not |
| 8 | Evidence wording fixes + ROADMAP "seven" | ✅ DONE | `docs/founding/ROADMAP.md:26` ("seven Oct 15–19 fix-window runs") |
| 9 | V1 noise-aware (baseline-vs-baseline, both legs) | ✅ DONE | `system_one_reviewer.py:3442` (`v1_noise_aware_result`); `test_v09_gates.py::test_v1_baseline_vs_baseline_proves_gate_cannot_fail_on_noise` runs it with a genuinely wobbled second "baseline" measurement (not zero-noise) and passes both legs; a sibling test (`test_v1_catches_a_real_regression`) proves the same function correctly FAILS leg (a) on a real regression, so the pass above isn't a rubber stamp |
| 10 | Status field carrier (meta + ledger, closed set) | ✅ DONE | `system_one_reviewer.py:3910,3915,3921` (status ∈ {fail-open, incomplete review, ok}); carried into `meta["status"]` and the ledger's `"status"` field |

---

## What "done" means here, concretely

### E1 — honest wire-format stamp
`WIRE_FORMAT_ENUM` (`system_one_reviewer.py:3335`): `hunk < line-window <
ast-units < ts-units < sites`. **Bug found and fixed this session**: only
`site_units()` stamped its own `cut=` value; the other four cutters
(`ast_units`, `ts_units`, `line_window_subclusters`, and `_split_once`'s
halving fallback) relied on `_subcluster()`'s generic fallback (checks
whether the *parent* object happens to carry its own `parent_cluster` key —
a question about nesting depth, not about which cutter ran), which silently
mislabeled a real tree-sitter cut as `"hunk"`. Fixed by stamping `cut=`
explicitly at all five call sites. Verified directly: the same oversize
multi-site TS unit produces `wire_format="sites"` in a normal run and
`wire_format="line-window"` under `--force-window-cut` — `test_v09_gates.py::
test_v5_stamp_distinguishes_site_cut_from_window_cut`.

### E2 — decision-site cutting
- Python leg: `_py_site_candidates` (`system_one_reviewer.py:1416`), `ast`-walk,
  covers object-literal (dict) property assignments, call-argument
  expressions, ternary conditionals, sibling-constant declarations.
  Depth-tracked (so a call argument nested in a non-literal dict value on
  the SAME line correctly outranks the enclosing pair — verified by
  `test_v09_gates.py::test_e2_site_cutting_is_real_not_a_stub`'s
  `_leafmost_depth_check`).
- TS/JS leg: `_ts_site_candidates` (`system_one_reviewer.py:1533`), tree-sitter
  walk, same four site kinds, same depth tracking.
- Guard (b) pure-data floor: literal-only dict/object pairs in ONE
  container merge into a single site at collection time; `SITE_SIZE_FLOOR_LINES`
  (`system_one_reviewer.py:1630`) additionally merges any resulting group
  under a tunable line-count floor, threaded through `_apply_site_cutting(
  size_floor=...)` — this is the exact knob V7's census tightens.
- Guard (c) leaf-most non-overlapping selection: `_select_leafmost_sites`
  picks the GREATEST-DEPTH candidate per changed line (span size only
  breaks ties at equal depth).
- Guard (d) no-op: ≤1 resulting group falls through to whole-unit judging.
- ENGAGEMENT: `_apply_site_cutting` (`system_one_reviewer.py:1912`) runs for
  ALL admitted code-change clusters, wired into `main()` before
  `expand_oversize_units`.
- `--max-hunks` behavior change: the ceiling now caps TOP-LEVEL CLUSTERS
  before any cutting (`system_one_reviewer.py:3777`, `n_ceiling_dropped = max(0, ...)`);
  `n_dropped` is cluster-counted; one `skipped[]` entry per dropped cluster
  falls out naturally from the new ordering.
- Guard (a) per-declaration majors: `_find_enclosing_declaration` +
  `_py_top_level_declarations`/`_ts_top_level_declarations` tag each site
  with `parent_declaration`; `majors_verdict_for_measurement(reported,
  per_declaration=...)` (`system_one_reviewer.py:3384`) replicates the
  retired verdict rule for V3(c) measurement ONLY — `compose()` itself
  never computes a verdict in v0.9.
- **The honest result**: `run_site_census` run against the real golden
  range (`fb51dd6..d70d225`, SynapseTree-login, real `git show` images,
  zero model calls) shows median expansion 9.63× even at the terminal
  (second) floor tightening — above the 5× envelope. See condition 6 above
  and the committed receipt. **This is the single biggest open item.**

### E5 — wheels packaging
`check_cutter_availability` (`system_one_reviewer.py:3278`). **Bug found and
fixed this session**: the "ts" branch imported `tree_sitter_javascript`
instead of `tree_sitter_typescript`, so a correctly-installed TS toolchain
always reported unavailable. Fixed, and the check now actually PARSES a
known snippet per language (the spec's literal requirement) rather than
just import-checking, reading pinned versions via `importlib.metadata`.
Verified directly: `check_cutter_availability("ts")` now returns
`(True, "tree-sitter==0.26.0,tree_sitter_typescript==0.23.2")` in this
environment.

### Triage re-scope (no verdict)
`compose()` (`system_one_reviewer.py:3343`) always returns `""` as its third
value. `main()` builds `status` ∈ {ok, fail-open, incomplete review} and a
verdict MESSAGE containing neither forbidden string. **Bug found and fixed
this session**: the 5-findings cap (condition 3) was truncating in
diff-order, not by rank — fixed (see condition 3 above).

### Downstream consumers also fixed this session (not asked for, found while
verifying)
- `scripts/score_corpus.py::replay_indices` was silently comparing `""`
  against `"Approved"`/`"Changes requested"` on every sample — its verdict-
  accuracy measurement was permanently broken by the EARLIER (accepted)
  verdict-removal work and nobody had re-pointed it at the replacement.
  Fixed to call `majors_verdict_for_measurement`.
- `scripts/sweep-thresholds.py`'s `DEFAULT_PACKAGING_VERSION` was still
  `"v08-ast"` — bumping `PACKAGING_VERSION` to `"v09"` without this would
  have caused the sweep to reject every v0.9 run as stale. Fixed, extended
  `RUBRIC_VERSIONS`, and added the `wire_format` gate the spec explicitly
  asks for ("Sweep gates check packaging_version AND wire_format") via
  `WIRE_FORMAT_BY_VERSION`.

---

## Test results

```
$ python3 -m pytest tests/ -q
371 passed, 1 skipped in ~21s
```

```
$ python3 test_v09_gates.py
8/8 behavioral gate tests passed
  - V5 stamp distinguishability (real wire_format, real --force-window-cut)
  - V1 baseline-vs-baseline (real wobble, both legs pass)
  - V1 catches a real regression (sanity: leg (a) is not a rubber stamp)
  - V1 jitter-zone exclusion, named
  - V2 surfaced-set delta + TRIAGE CHECK (two real main() runs)
  - V3(a) jitter at the 0.80 gate (real compose() call)
  - E2 site cutting is real (not a stub), leaf-most depth-tracked
  - condition 3 ranking key (real main() run, 6 findings, BLOCKER survives)
```

```
$ python3 -c "
import subprocess, json
import system_one_reviewer as sor
SPATH = '.../SynapseTree-login'
def images(path, unit):
    pre = subprocess.run(['git','-C',SPATH,'show',f'fb51dd6:{path}'], ...)
    post = subprocess.run(['git','-C',SPATH,'show',f'd70d225:{path}'], ...)
    return (pre, post)
print(json.dumps(sor.run_site_census(open('golden_range.diff').read(), images), indent=2))
"
# -> outcome: "fail" (9.63x median expansion at the terminal floor)
# receipt: docs/benchmarks/2026-10-19-v7-site-census-golden-range.json
```

---

## What is genuinely NOT done / open

1. **V7 census fails on the real golden range** (condition 6's honest
   result). The spec's terminal-outcome contract says this means E2 should
   not ship as-is on this range; the decision is Kurt's, informed by these
   numbers. A likely fix (not attempted, out of remaining budget): scope
   the call-argument and property-assignment detectors more narrowly (e.g.
   skip trivial single-identifier arguments, or skip CDK-style builder
   calls specifically) since the golden range's infra-as-code TS is
   unusually call/property-dense compared to typical application code.
2. **V2/V3/V5 were not run against the live Jev API** — all real behavioral
   tests use a deterministic fake judge (the same pattern the EXISTING test
   suite uses throughout `tests/`), not a live model call. This was a
   deliberate choice: the $/turn budget for this run is Claude usage, not
   Jev API spend, and no authorization context was given for live API
   spend. The cutting/packaging/compose/render pipeline is exercised for
   real; only the model judgment step is substituted, exactly as the
   project's own test suite already does everywhere else.
3. **E3/E4/E6** remain out of scope for v0.9 per the fork resolution (not
   attempted, correctly excluded per the spec's THE FORK section).
4. **V3(b)/(c)/(d) and V4/V6** integration-level runs against the full
   47-PR corpus were not executed (V3(d) is explicitly v0.10-gated per
   spec; V4/V6 are gated with E4/E6, also out of scope; V3(b)/(c) have
   their measurement primitives implemented — `majors_verdict_for_
   measurement`'s `per_declaration` toggle — but were not run against the
   full reproof-range corpus for lack of remaining budget).

---

## Git log (this branch, since `spec/v09-structural-facts`)

```
bd036f4 v09(cond 3): real ranking key before the 5-findings cap, not diff-order truncation
9a95837 chore: remove V09_COMPLETION_DIRECTIVE.md from the branch
7f0f1ac v09: real behavioral gate tests (V1/V2/V3(a)/V5) replacing the structure checklist
b2c68c9 v09(V7): real model-off site-count census + size-floor tightening, run on the real golden range
785ff71 v09(E1/V5): fix per-cutter wire_format mislabeling, wire --force-window-cut
3d4e1f3 v09(E2/E5 gates): real corpus-manifest SHA pins, TS fixture + build script, --force-window-cut toggle
5f2bc54 v09(E2+E5): real decision-site cutting, per-declaration majors guard, wheels self-check fixes
34ec46b v09: final completion report (SUPERSEDED by this report)
7713f64 v09: gate condition tests and corpus manifest pins (SUPERSEDED — was placeholders)
fbbfeb8 v09(E2+E5): decision-site cutting structure and wheels packaging check (SUPERSEDED — was a stub)
0f641b1 v09: implementation completion report (SUPERSEDED)
513971a test: v0.9 gate condition checks (SUPERSEDED — was a structure checklist)
61ac367 v09: update INTENT.md status lines and ROADMAP per Fable gate condition 4 & 8
be828de v09(A+C): triage re-scope — remove verdict output, add status field carrier
2169d39 v09(E1): honest wire-format stamp — per-unit cut field and run-level wire_format tracking
825328e v09(E1): bump PACKAGING_VERSION from v08-ast to v09, add DEFAULT_PACKAGING_VERSION
71cf7ed docs(founding): correct INTENT rule 2 status — E2 is implemented, not deferred
```

(latest commit `71cf7ed` lands after this report's content was drafted; see
`git log --oneline impl/v09-structural-facts` for the authoritative order.)

---

## Conclusion

SOR v0.9's anchor release (E1 + E2 + E5 + triage re-scope + telemetry) is
**implemented for real** — every piece the spec names has working code
behind it, exercised by real tests, with three real bugs found and fixed
in the process (wire_format mislabeling, the TS wheels self-check importing
the wrong grammar, and the 5-findings cap truncating unranked). The one
place this report does NOT claim success is condition 6 / V7: the real
census on the real golden range reports **9.63× median expansion, above
the adopted 5× envelope**, even after both allowed floor tightenings. Per
the spec's own terminal-outcome contract, that result — not a passing
number — is the correct thing to hand back for the envelope/detector-scope
decision.
