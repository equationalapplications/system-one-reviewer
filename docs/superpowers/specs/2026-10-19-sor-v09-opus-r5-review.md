**Delta review of the v0.9 spec, rev 8.** All three prior findings are fixed. Fixing N4 left one leftover in THE FORK, and there is one small gap against ROADMAP S6. Neither one blocks the spec.

I didn't get a diff: the `git diff` call was declined. This review checks rev 8 as pasted, without a line-by-line diff against rev 7.

### Prior findings

- **R4: FIXED.** V2 now says "Option B: **≥ 5/8** with three repeats". That matches THE FORK's "≥5/8" and S6's "golden 5/8 at the bar, three repeats". The 4/8 bar is gone, so the 4/8-passes-V2-but-fails-S6 case can't happen. One small point: the header says "three repeats" matches THE FORK, but THE FORK's Option B never mentions repeats. That's harmless, because V2 is the detail authority.
- **N3: FIXED.** Option C now has a V2 exit: the same anchor-placement exit as A, plus a check that no Changes-requested output appears anywhere.
- **N4: FIXED in V2.** V2 now says plainly that Option A passes on anchor placement within ±1 of a site unit, not on crossing 0.80. It also says this is what S5's "B2/M2 anchor-class recovered" means, so the conflict with S5 is settled in V2. THE FORK still has the old wording (see D1 below).

### Regressions and leftovers in the changed text

- **D1 (nit, leftover from N4): THE FORK's Option A still mixes up the pass condition and the fallback.**
  - THE FORK says the probe measures whether site anchors "land within ±1 AND cross the 0.80 gate … if they do not, Option A's honest exit is 0/8". Read literally, failing to anchor within ±1 still leads to the honest, shippable 0/8 exit.
  - V2 (and S5) now say the opposite: an un-anchored defect fails Option A's gate.
  - *Failure scenario:* Option A is picked, and the B2/M2 site anchors land 5 lines from the golden lines. THE FORK reads as "0/8, honest, ship". V2 and S5 read as "gate failed". Two parts of the same spec give different answers on the same receipt.
  - *Fix:* change THE FORK's Option A to split the two conditions. Gate: anchored within ±1, per V2. Fallback: if anchored but not crossing 0.80, the exit is 0/8 with the anchor mechanism in place.
- **D2 (nit): the claim that Option B is "aligned with S6" leaves out half of S6's recall gate.**
  - S6's gate also requires "negative heads clean, **detector-alone arm reported**". V2's Option B contract doesn't mention the detector-alone arm. The negative heads are covered indirectly through V3.
  - "Three repeats" is also not pinned. It could mean each repeat reaches ≥5/8, or that a majority or median does.
  - *Failure scenario:* Option B measures 6/8, 5/8 and 4/8 over the three repeats, with no lexicon-only arm. One reader says V2 passes; an S6 auditor says it fails on both counts.
  - *Fix:* add "each of three repeats ≥ 5/8; lexicon/detector-alone arm reported" to Option B, or drop the word "aligned".

**APPROVE WITH NITS**