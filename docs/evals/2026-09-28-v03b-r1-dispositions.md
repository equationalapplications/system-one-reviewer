# v03b r1 dispositions (Opus review of 2b95c80, fixes in the follow-up commit)

- M1 (references_remaining wrong in both directions): **FIXED** — matches
  only DECLARED names (def/class/function/const/let/var + import targets)
  with `\b` word boundaries; substring keyword matches impossible.
  Whole-file deletions: corpus is empty by construction → returns False
  (vacuous), docstring states this honestly and drops the never-effective
  basename/stem logic. Tree-wide claims removed from the docstring.
- M2 (gate only covered BLOCKERs): **FIXED** — gate now applies to all
  sev≥2 deletion findings (the `lvl >= 2` branch); docstring states that
  deletion findings do not corroborate each other (#45 had six wrong
  together) and that corroboration = refs True OR a reported code-change
  finding. Test `test_two_uncorroborated_deletions_do_not_flip` pins the
  2-MAJOR path.
- M3 (sweep can't replay new logic): **FIXED** — `judged` entries now
  carry rubric/references_remaining/change_type; `rewrap()` passes them
  through (defaulting to code-change for pre-v03b records, which never
  sent deletion questions). Caveat kept: DELETION_REAL_THRESHOLD sweep
  support is future work; the sweep sweeps the code-change threshold.
- M4 (version tag): **FIXED** — PACKAGING_VERSION = "v03b"; the committed
  v03 negative benchmark is superseded (its fixture_head predates the
  deletion cluster); v03b negatives re-run live: 3× Approved, 0 FP, and
  the deletion cluster scored sev 0.03–0.04 / is_real 0.20–0.24 under the
  deletion rubric (confidence 0.96–0.97). Positive fixture re-verified:
  F1 0.91, recall 1.0.
- m1 (resolve_diff head): **FIXED** — dead else-branch and impossible
  fallback removed; `{right_ref}^{commit}` peel for annotated tags.
- m2 (prompt wording contradictions): **FIXED** — instruction now says
  cross-file usage "is measured separately and not your concern here"
  (accurate: it IS in the state); "risky on its face" replaces
  "self-contained"; Blocker criterion rewritten to a hunk-visible example
  (deletes the only test for a kept feature).
- m3 (stale brief line): **FIXED** — F7 paragraph notes the v0.3b
  auto:<mode> label and that bare-mode labels are historical.
- m4 (malformed test header): **FIXED** in the r2-fixes commit (d80f275):
  headers rewritten to match bodies exactly (`@@ -1,3 +1,2 @@` and
  `@@ -1,5 +1,4 @@`). The r3 round initially "corrected" this row with a
  wrong claim (r4 round) — that correction was itself wrong; this row is
  the accurate one (verified via `git log -S` pointing at d80f275).
- m5 (missing test cases): **FIXED** —
  test_two_uncorroborated_deletions_do_not_flip and
  test_deletion_major_verdict_eligible_when_corroborated added.
