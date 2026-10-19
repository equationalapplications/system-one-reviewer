I checked each r2 disposition against the current file (`2026-10-19-sor-v09-structural-facts-design.md`). Items 1 and 4 are fixed. Item 2(b) and the Item 3 behavior-change wording are also fixed. Item 2(a) is claimed fixed but isn't, and the other fixes introduced three new problems.

### Prior findings

- **Item 1 (spec/specs dirs): FIXED.** The routing directory set is now {`tests`, `test`, `__tests__`}, and `src/spec/openapi-builder.ts` no longer routes to the test rubric.
- **Item 2(a): CLAIMED FIXED, NOT FIXED.** The 789/791 site-state probe appears only in THE FORK's Option A (line 104), which calls it "the V2 pre-flight's site-state probe." V2's actual pre-flight text has no such probe. It also says pre-flight runs **MODEL OFF**, and a probe that judges units 3× is model-on by definition.
  - *Failure:* someone implementing V2 follows V2's text, runs only the model-off anchor census, and never measures whether 789/791 site units cross 0.80. Option A then has no exit measurement at all.
  - *Fix:* add an explicit model-on sub-step to V2, scoped to the 789/791 site units at 3× each, and say it runs after the model-off census passes.
- **Item 2(b): FIXED.** Option A's exit is restated honestly.
- **Item 3: FIXED in its main claim.** The "truncation moves ahead of expansion" behavior change is stated correctly. The fix introduced a regression, covered in R2 below.
- **Item 4: FIXED.** The stale E5 sentence is gone. V3(c) is now the new-build flat vs per-declaration comparison, OQ1 carries its superseded note, and V7 has a concrete envelope, a cap of two tightenings, and the 120-line prohibition.

### Regressions in the changed text

- **R1 — Option A's exit contradicts V2's exit contract.** V2 is titled "exit contract" and requires **≥ 4/8** recall, counting recognition-class recoveries "via E4 facts." The rewritten Option A says its honest exit may be **0/8**, and E3/E4 don't ship under A.
  - *Failure:* Kurt picks A. V2 still says the release fails below 4/8 using a mechanism the release doesn't contain. Either the release is permanently blocked, or someone overrides V2 informally, which AGENTS.md forbids ("every gate measured, none argued").
  - *Fix:* give V2 a per-option exit: A means the anchor-placement measurement only; B means ≥ 4/8 with the attainable ceiling. Also replace "P1+P2 build" with the build for the option picked.
- **R2 — the coverage banner denominator now hides drops.** E2 says the incomplete-review banner uses "denominator = admitted top-level clusters."
  - *Failure:* 50 clusters, ceiling 40. The banner reads 40/40 and coverage looks complete, which violates INTENT rule 7 and the AGENTS.md rule that coverage-incomplete runs can never read as Approved.
  - *Fix:* the denominator must be **total** top-level clusters, with admitted clusters as the numerator. While there, also say that `skipped[].reason = max-hunks>ceiling` entries are now one per dropped cluster, not one per unit, so ledger audits still detect incomplete runs.
- **R3 — V7 has no exit when the census still fails.** "The floor may tighten at most TWICE" contradicts "Rerun until the census passes," and the spec doesn't say what happens if both tightenings still leave the median above 5×.
  - *Failure:* after two tightenings the median is 6×. The spec forbids a third tightening but also forbids spending until the census passes. That deadlock invites an unrecorded third tweak.
  - *Fix:* add the terminal outcome. For example: "after two tightenings without passing, E2 does not ship in v0.9 and the envelope goes back to Kurt with the census numbers."

### Nits

- **N1:** The header still says "rev 5" and "DRAFT rev 5 — in Opus delta cycle," but the commit and dispositions describe rev 6. Audits citing the rev number can't tell whether the r2 fixes are included.
- **N2:** Option A now names the 0.80 gate, but V2 and V3(b) never say which gate "reported" means. If the baseline counts reported findings at 0.50 and the new build at 0.80, the comparison passes trivially. Pin 0.80 for both arms, per INTENT rule 4 and ROADMAP S1.

**REQUEST CHANGES**