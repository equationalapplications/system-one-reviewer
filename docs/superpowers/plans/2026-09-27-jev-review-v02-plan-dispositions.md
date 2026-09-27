# Dispositions — plan rev 1 → rev 2 (Opus cycle + GLM self-review)

M1 (truncated head fails SHA gate): FIXED — full 40-char `fixture_head` field
(additive) is the gate input; `head` stays 10-char for display; expected SHAs
live in examples/fixture-shas.txt read by scripts and sweep (Global Constraints,
Task 4, Task 7).

M2 (--fixture used before defined): FIXED — the flag and its metric field move
to Task 4 with the baseline runs; Task 5 only adds --negative-golden.

M3 (commit -am misses new files): FIXED — every task uses explicit
`git add <paths>`; Global Constraints rule added.

M4 (Task 2 live run undefined/key-dependent): FIXED — replaced with the offline
regression test on tests/data/v01-fixture.diff asserting anchors [11,14,17,20,26].

M5 (label guard never runs in CI): FIXED — test_fixture_labels.py builds both
fixtures into tmp_path via JEV_FIXTURE_ROOT and asserts SHA + verification
substrings; build scripts take ROOT from env; Task 9 includes it in CI.

M6 (triage/judge/api-key tests missing; key leaks into fallback tests):
FIXED — Task 6 adds test_judge/test_triage/test_api_key; conftest deletes
TYPESAFE_API_KEY.

M7 (sweep metric undefined): FIXED — Task 7 formulas: threshold lattice with
plateau exclusion spelled out (0.75 dropped), per-run precision formula with
mean negative FP, minor-note defined as sev_level==1 ∧ style, min-F1 combined
curve, even-tie → lower middle, Δ-FP-neg column, both change rules printed.

M8 (fixture bugs unspecified; spec contradiction): FIXED — Task 4 contains the
full base and HEAD source; plant 4 is now open(path,"w") (BLOCKER), the
redundant-"r" nit is gone; severities recorded as golden metadata; golden TSV
gains verify-substring and severity-class columns.

m1 (deletion anchor / window crossing @@): FIXED — entries carry hunk_start;
windows clamped at hunk boundaries; anchor fallback chain specified.

m2 (docstrings): FIXED — Task 2 fixes both docstrings.

m3 (raw precision labeling): FIXED — field name unchanged (additive-only);
labeling in render/README only; stated in Task 3.

m4 (negative results location; --negative-golden semantics): FIXED —
golden_eval.negative_eval added to the additive list; the flag triggers
eval_negative (documentation/trigger role; FP counting does not filter by it).

m5 (README skip assertion): FIXED — tests/test_negative.py asserts the
README change is triaged as skipped.

m6 (Task 3 edits TSV Task 4 rewrites): FIXED — Task 3 uses synthetic TSVs in
tmp_path; the real TSV belongs to Task 4.

m7 (column vs block): FIXED — verification data is extra TSV columns
(desc, verify-substring, severity-class).

m8 (loader naming): FIXED — conftest provides the `jr` fixture (no load_module
name); sweep has its own load_tool(); test_sweep uses spec_from_file_location.

m9 (merge-gate fallback unplanned): FIXED — Task 8 failure path (threshold
stays, PR analysis, v0.3 issue link); Task 11 re-verifies gate at final head.

m10 (import math inside function): FIXED — top-level import.

GLM addition (late commits can invalidate the gate): FIXED — Task 11 requires
gate re-verification at final head before merge.
