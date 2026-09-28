# v03b r4 dispositions (Opus delta review of 70b6fcc, fixes in follow-up commit)

- M1 (rewrap's v03b rubric gate could never fire — packaging_version lives
  on the run record, not judged entries): **FIXED** — `rewrap(j,
  run_version=None)`; `replay()` passes the run's packaging_version; a
  v03b run with rubric-less entries dies. Pinned by
  `test_rewrap_dies_on_broken_v03b_record` (v03b + no rubric ⇒ SystemExit;
  v02 + no rubric ⇒ replays as code-change).
- M2 (replay test never exercised the deletion rubric — code_mod.py was
  new on feature, not deleted): **FIXED** — code_mod.py is committed on
  MAIN, feature merges main then removes lines, so the merge-base diff
  has a genuine deletion-only cluster; test asserts
  `any(j["rubric"] == "deletion")`, all deletion entries carry a bool
  references_remaining, and replays through sw.rewrap with the run's
  version. (The git commit now goes through the fixture's check=True
  helper.)
- M3 (dispositions claimed tests that didn't exist): **FIXED** —
  `test_references_remaining_relative_imports` added covering
  `from .utils import helper`, `from . import helper`, `from ..pkg import
  helper` — all assert references_remaining False; m4's test now takes
  the `jr` fixture and passes run_version to rewrap. This r4 dispositions
  file supersedes the r3 rows that overclaimed.
- m1 (corroboration comment overstated): **FIXED** — comment states the
  exact rule: cross-file requires sev>=2 regardless of category (a
  sev>=2 style flag is a serious claim); same-file requires sev>=2 or
  non-style; category None counts as style-like.
- m2 (benchmark -1/-2/-3 records from different builds under one tag):
  **NOTED, not silent** — the PACKAGING_VERSION comment and the benchmark
  doc state which build produced which records and that the input shape
  is identical (both post-B1, fields verified). A version bump was
  considered and rejected: the input shape did not change between the
  two builds, only the ledger fields did (which the B1 fix added).
- m3 (left side of `...B`): no change needed — confirmed as the review
  stated.
