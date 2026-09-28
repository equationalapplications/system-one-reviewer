# r1 dispositions — field-evals brief

- B1 (verdict mechanism for #45 misdescribed): **FIXED** — ledger data shows
  the single reported finding scored severity 2.80 (sev_level 3, BLOCKER),
  which is how one finding flipped the verdict; F1 now states this mechanism
  explicitly with the sev 2.73–2.82 cluster scores and the is_real 0.37–0.65
  gate data. Verdict string in ledger was plain "Changes requested" (no
  incomplete suffix), so case (b) is excluded.
- B2 (proposed is_real≥0.75 cutoff wouldn't catch pr46's 0.64): **FIXED** —
  F2 no longer proposes a fixed cutoff; it states is_real alone cannot
  separate pr46-FN (0.64) from pr45-FP (0.65) and defers to the sweep.
- M1 (wrong knob named; "pipeline lost it" false; middle tier already exists):
  **FIXED** — F2 names the verdict rule (:773 lone-MAJOR limit) as the gap;
  "the pipeline lost it" replaced with "the verdict policy ignored it";
  middle-tier proposal dropped.
- M2 (headline numbers contradicted table; #43/#46-fix-delta wrongly counted
  TP): **FIXED** — tally recomputed: TP 0, FP 1 strong + 1 moderate, FN 1,
  TN 2, #43 pending; intro no longer claims universal ground truth; table
  now labels ground-truth strength per run.
- M3 (inventory incomplete; mockLlmProvider line 1 vs :11 blurred):
  **FIXED** — all 9 runs listed with modes; tool's anchor (11) and
  ground-truth line (11, they coincide) stated; ledger appendix added.
- M4 (confidence semantics misdescribed): **FIXED** — F3 restated: missing
  key ⇒ None already; literal 0.0 comes from the provider; it is the
  severity score's confidence; never rendered; gating question posed as open
  + Jev semantics flagged as needed research.
- M5 (proposed needs_human_review gate breaks closed-set contract; base rate
  unknown): **FIXED** — F4 now reports the base rate across all ledger runs
  incl. benign fixtures (0.69–0.98, gate at 0.9 would fire on benign), and
  the proposal keeps the closed-set last line intact.
- M6 (--range two-dot vs merge-base confound): **FIXED** — new finding F5;
  pr45 confirmed genuine deletions (pr: mode uses merge-base); docstring
  contradiction cited (:9 vs :329); pr46-fix-delta flagged as possible
  stale-base instance.
- m1 (after-empty doesn't cover partial deletion-only clusters): **FIXED** —
  F1 detection is now "no `+` entries in the run", with whole-file deletion
  distinguished via `deleted file mode`/`+++ /dev/null` headers.
- m2 (docstring claims deletion-only never collapses to line 1; whole-file
  deletions do): **FIXED** — docstring bug noted in F1 with proposed fix.
- m3 (#43 "9 × sev≥2" wrong; jitter note): **FIXED** — table now says
  7 MAJOR, 2 MINOR (sev 1.39–2.10); F1/F3 cross-ref removed from #43 row.
- m4 (repo "." fix is basename(realpath)): **FIXED** — F7 states it.
- m5 (ledger claims unverified): **FIXED** — appendix now reproduces the
  ledger fields verbatim.
- m6 (README rebrand, keep path-continuity): **FIXED** — F6 states it.

## Post-review note (2026-09-28, cycle 3)

The F5 stale-base example (pr46-fix-delta) was later CHECKED and RULED OUT
(`git merge-base --is-ancestor 8e6f440 f8c6594` → ancestor; both reported
findings sit in files the fix touched) — the final brief's F5 records this.
Earlier text in this file flagging pr46-fix-delta as a possible stale-base
instance predates that check and is superseded by it.
