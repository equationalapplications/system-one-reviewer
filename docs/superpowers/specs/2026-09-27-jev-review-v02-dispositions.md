# Dispositions — spec rev 3 → rev 4 (cycle 3 delta review)

R1 (no single-candidate rule across N runs): FIXED — E5 "Combining runs":
combined curve = per-threshold minimum F1 across runs; candidate = argmax of
the combined curve; tie-break applies to the combined curve; the every-run
margin check evaluates that one candidate — one decision, reproducible.

R2 (packaging_version can't prove the fixture is the redesigned one):
FIXED — build scripts made deterministic (fixed dates/identity) so the
fixture head SHA is reproducible; metrics already log `head`; the sweep
rejects runs whose logged head misses the fixture's committed expected SHA
or whose packaging_version != v02; stale/hand-edited fixtures fail loudly.
E1 states the determinism requirement the SHA gate depends on.

R3 (stale "Deliberately does not change"): FIXED — now lists both additive
flags (--negative-golden, --fixture, both on jev-review.py), the additive
schema fields with their E-numbers, and the unchanged compose input shape
(sweep re-wraps flat judged entries).

R4 (merge gate run count): FIXED — E4: zero BLOCKER/MAJOR in every negative
run (all N ≥ 3).

R5 (FP formula vs exemption asymmetry; two precision figures): FIXED —
formula now excludes MINOR-style notes on the positive side too;
golden_eval precision relabeled "raw precision"; the sweep's combined figure
is the published one.

R6 (compose input shape for replay): FIXED — "Deliberately does not change"
documents the re-wrap; compose's contract unchanged.

R7 (golden lines need mechanical verification): FIXED — E1: build scripts
verify each golden TSV line against actual file content (expected-substring
column) and fail on mismatch; a unit test repeats the check against the
committed TSVs.

Status after cycle 3: doc-review cycle cap (3) reached per the dual-review
termination rule. R1–R7 dispositions above are applied in rev 4 but the
verification of those fixes is below cap; open list goes to Kurt with the
spec before implementation begins.
