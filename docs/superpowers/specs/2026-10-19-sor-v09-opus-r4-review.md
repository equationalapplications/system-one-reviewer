**Delta review of the v0.9 structural-facts spec, rev 7: one regression blocks approval; every prior finding is fixed.**

### Prior findings

- **2(a): FIXED.** V2 now has its own model-on pre-flight step. It judges the 789/791 site units 3× each at 0.80, without domain facts, and runs only after the model-off census passes. Option A's "the V2 pre-flight's site-state probe" now points at real V2 text.
- **R1: FIXED (but see R4).** V2 has a per-option exit contract. It is measured on "the build for the OPTION PICKED", and the "via E4 facts" mechanism is gone. Option A's 0/8 fallback no longer contradicts V2.
- **R2: FIXED.** The banner's denominator is the total number of top-level clusters, with admitted clusters as the numerator. Skipped entries are written one per dropped cluster, so the 40/40 case can't happen and ledger audits still catch incomplete runs.
- **R3: FIXED.** V7 now has a terminal outcome: if two tightenings still fail, E2 does not ship in v0.9 and the census numbers go back to Kurt. The old "rerun until it passes" wording is gone, so the deadlock is closed.
- **N1: FIXED.** The header and Status line both say rev 7.
- **N2: FIXED.** V2 sets 0.80 for both arms in all options. V3(a) defines "findings" as ≥ 0.80 in both arms, and (b) and (d) inherit that definition.

### Regressions in the changed text

- **R4: V2's Option B bar is 4/8, but Option B in THE FORK and ROADMAP S6 both say 5/8.**
  - THE FORK's Option B says "Recall exit: ≥5/8 per the prose-probe upper bound".
  - The new V2 contract says "Option B: **≥ 4/8**".
  - ROADMAP S6, which this work feeds, sets the recall gate at "golden 5/8 at the bar, three repeats".
  - *Failure:* Kurt picks B and the build measures 4/8. V2 says it passes; THE FORK and S6 say it fails. That is the same "gate settled by argument" problem R1 was raised to remove, now inside the per-option contract that was supposed to fix it.
  - *Fix:* make V2 say ≥ 5/8 with three repeats to match S6. If 4/8 is the intended bar, state that and amend THE FORK and S6 through review, with the reason.

### Nits

- **N3: Option C has no V2 exit.** The per-option contract defines A and B only. If Kurt picks C (triage re-scope), V2 is undefined for the chosen build. Add a line, for example "Option C: same anchor-placement exit as A; plus a test that verdict demotion leaves no Changes-requested output".
- **N4: Option A's pass condition is implicit, and S5 may require more.** Under Option A, V2 can fail only through the model-off census (no anchor within ±1). The model-on probe is a measurement with no fail condition. ROADMAP S5's gate is "B2/M2 anchor-class recovered". If that means "anchored within ±1", say so in Option A. If it means "crosses 0.80", Option A's 0/8 fallback conflicts with S5. Pin which one.

**REQUEST CHANGES** (R4 only, a one-line change to V2; the rest are nits.)