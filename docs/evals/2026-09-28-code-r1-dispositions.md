# v0.3 code review r1 dispositions (commit e763080)

- M1 (deletion check only catches whole-file deletions): **FIXED** —
  `change_type` computed in `package_hunks` from the cluster's own run
  (`run_kinds`, no '+' entries ⇒ deletion-only); `hunk_state` reads the
  packaged field. New pin: `test_infile_deletion_with_context_is_deletion_only`
  (in-file removal + context lines ⇒ deletion-only, state keeps context).
- M2 (inputs changed, no re-run, no version bump): **FIXED** —
  `PACKAGING_VERSION = "v03"` with comment; positive fixture re-run ×3 on
  the branch: F1 0.91 / 0.91 / 1.00, recall 1.0 ×3 (ledger labels
  `v03-r1-baseline-1..3`); negative fixture ×3: zero FPs
  (`v03-r1-neg-1..3`). All six runs complete (no parse failures).
- M3 (README overclaims "addressed"; error undercount): **FIXED** — README
  now says "targets", explicitly states the #45 fix is unproven until a
  live re-run, and counts all three wrong verdicts of the five clear cases.
- minor 1 (docstring anchor claim): **FIXED** — now states in-file deletion
  clusters never collapse to line 1 while whole-file deletions do.
- minor 2 (open-ended ranges): **FIXED** — `triple_dot` fills empty sides
  with HEAD; pin `test_triple_dot_fills_open_sides_with_head`.
- minor 3 (mode string): **FIXED** — `--range` mode records the diffed
  `A...B` spec; pins updated (`test_mode_records_diffed_spec`,
  `test_label_default_and_repo_metadata` asserts label `range:main...feature`).
- minor 4 (abspath → realpath): **FIXED** — `os.path.realpath` at the
  meta["repo"] site; test asserts realpath basename.
- minor 5 (weak tests): **FIXED** — if/else collapsed; `_unused` imports
  removed; end-to-end metadata test asserts label, repo basename, and
  packaging_version through real `main()` wiring.
- minor 6 (stale r1 disposition M6): **FIXED** — post-review note added to
  `2026-09-28-field-evals-r1-dispositions.md` marking the stale-base
  hypothesis as checked and ruled out, superseded by the final brief.
- minor 7 (F5 describes old code): **FIXED** — F5 retitled "(FIXED in
  v0.3)", past tense, points at branch re-run.

Out of scope, noted: F2 (verdict rule), F3 (confidence semantics), F4
(needs_human_review gate/cut) remain open v0.3 questions per the brief —
each requires either a threshold sweep over new ledgers or a Jev-docs /
Kurt decision. Not claimed as fixed here.
