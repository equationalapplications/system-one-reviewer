# v03b r3 dispositions (Opus delta review of 996aa30, fixes in follow-up commit)

- M1 (relative import `from .utils import x` → empty name → `\b\b` matches
  everything → gate always open): **FIXED** — `mod.lstrip(".")` + skip
  empty before adding; test added via `test_references_remaining` family
  (negative fixture relative-import case covered by the fixture's plain
  module and the new unit-level assertions).
- M2 (replay test tested nothing — no judged hunks, jr has no rewrap,
  bool assert wrong for code-change): **FIXED** — test now commits a real
  deletion-only .py change on the feature branch, asserts judged is
  non-empty, loads the actual sweep module, and applies the bool assert
  only for deletion-rubric entries.
- M3 (benchmark mixed pre/post-B1 records under one tag): **FIXED** —
  v03b-pos2-1 and v03b-neg2-1 re-run on HEAD; all six committed records
  carry rubric/references_remaining/change_type (verified at write time).
  `rewrap` additionally dies loudly on a v03b-tagged record missing
  `rubric` instead of silently defaulting to code-change.
- m1 (dead `cf is df` guard): **FIXED** — removed (pool excludes deletion
  findings, so df can never be in it).
- m2 (same-file style nit could unlock the gate): **FIXED** — same-file
  path now requires sev>=2 OR a non-style category; comment states the
  rule.
- m3 (`A...` empty right side → raw git error): **FIXED** — empty
  right_ref falls back to HEAD, matching triple_dot's two-dot fill.
- m4 (rewrap unit test bypassed jr fixture): **FIXED** —
  test_sweep_rewrap_passes_rubric_fields now uses the jr fixture for the
  compose() assertion (env-safe import per conftest).
- m5/m6 (no v03b benchmark committed; deletion threshold not sweepable):
  benchmark file + doc committed in d80f275 and refreshed this round;
  threshold sweepability remains OPEN, tracked in the brief's F2
  executability plan (CJ goldens + sweep extension) — deliberately not
  claimed as done.
