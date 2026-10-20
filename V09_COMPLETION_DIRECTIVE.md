# COMPLETION DIRECTIVE — SOR v0.9 (resume of this session; supersedes your final report)

Your previous turn's report claimed completion, but verification against the
spec shows the run is INCOMPLETE. Read this file fully, then finish the work.
Do NOT rewrite finished work (E1 stamp, verdict removal, status carrier,
INTENT/ROADMAP updates are accepted).

## Why the report was rejected

- **E2 (decision-site cutting) was deferred — but E2 IS the v0.9 anchor fix.**
  THE FORK (A+C) ships E1 + E2 + E5. An impl branch without E2 is the wrong
  scope; "production-ready" was false. You also skipped E5 entirely.
- Conditions 5, 6, 7, 9 of the Fable gate are OPEN. Deferred ≠ satisfied.
- `test_v09_gates.py` is a 135-line stub asserting structure, not the spec's
  V1/V2/V3/V5 exit contracts.
- `docs/superpowers/reports/2026-10-19-v09-impl-completion-report.md`
  contains claims that are not true — revise it at the end to match reality.

## Work remaining (in order; commit after each)

1. **E2 — decision-site cutting** (spec section E2; this is the core):
   cut at decision sites so unit anchors land at the site where the decision
   is made, replacing the line-window fallback where cutters engage. The spec
   names the mechanism — implement exactly what it says, nothing more.
2. **E5 — wheels packaging** (spec section E5): packaging/install docs so
   tree_sitter wheels are present in the tool's own runtime (root-cause
   receipt: `docs/benchmarks/2026-10-19-golden-run-rootcause.json`).
3. **Condition 5**: pin in `docs/benchmarks/corpus-manifest.md` the five
   negative-head SHAs, the `reproof:ct-61cluster` range, and the TS fixture.
4. **Condition 6**: V7 census reporting — initial size floor, each tightening,
   median site size, projected wall time next to the call multiple.
5. **Condition 7**: jitter counts at the 0.80 gate reported in V2/V3 report
   paths (the jitter helper already keys off the threshold argument —
   reporting only).
6. **Condition 9**: noise-aware V1 — use the V3(a) noise band (baseline run
   twice); leg (a) at-or-above baseline minus band; leg (b) surfaced-set
   comparison excluding units in the 0.80 jitter zone of either arm (excluded
   units reported by name). Include a baseline-vs-baseline rerun test passing
   both legs.
7. **Real gate tests** for V1 (per cond 9), V2 (surfaced-set delta + TRIAGE
   CHECK: no "Approved"/"Changes requested" anywhere, "Unavailable" + banner
   render), V3(a)–(c) ((d) is v0.10-gated — skip), V5. Use the fixtures in
   `examples/`. V4/V6/E3/E4/E6 stay excluded — do not implement.
8. **Revise the completion report** to state exactly what is and isn't done,
   per-condition, with file/line anchors. No inflated claims.

## Execution rules (unchanged and mandatory)

- Every command FOREGROUND, under ~8 minutes each; split suites per-file.
- Never launch background tasks; never end a turn awaiting a notification.
- Empty output = one retry, then record and move on.
- Local commits on `impl/v09-structural-facts` ONLY. NO push, NO PR, no
  remotes, no upstream comments.
- Don't modify `docs/benchmarks/` receipts except the corpus-manifest pins.
- Don't regress the accepted work listed above.

## End condition

All 10 Fable conditions satisfied with file/line anchors in a corrected final
report, tests green, clean `git log` on the branch. If a condition genuinely
cannot be satisfied, STOP that item, document the blocker precisely, and
report it — do not paper over it.
