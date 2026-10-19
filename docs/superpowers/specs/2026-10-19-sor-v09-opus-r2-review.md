I checked each rev-5 disposition against the spec and the receipts. Two dispositions are marked fixed but aren't, one fix contradicts text it left untouched, and one claim about the code is wrong. B1, B2, M1, M3, M5, M6, m1, m4, m6 and m7 are fixed as described.

**1. m3 is marked fixed but isn't.** The disposition says the `spec`/`specs` directory components were dropped from E6 routing. Line 220 still routes on `tests`, `test`, `__tests__`, `spec`, `specs`.
- **Failure:** production TS under a `spec/` directory (say `src/spec/openapi-builder.ts`) goes to the test-file question variant. Production code then gets judged by the wrong rubric and the wrong threshold. V6 would catch this only if the hand-curated list happens to include such a path.
- **Fix:** delete `spec`, `specs` from the directory set.

**2. M2 is only partly fixed.** Two problems:
- **The promised extension is missing.** The disposition says the V0 extension adds site-level states for lines 789/791. Neither the spec nor the corpus manifest mentions this.
- **The rewrite contradicts THE FORK.** §2(a) now says B2+M2 needs both the anchor fix (E2) and P3 recognition. But THE FORK (lines 88–90) still says "site anchors fix it with zero facts", and Option A (lines 101–104) still sets its recall exit at "anchor-class 2/8" with no P3.
- **Failure:** Kurt picks Option A because the spec promises 2/8 from E2 alone. By the spec's own §2(a), Option A can't reach that. So V2 either fails, or the exit bar gets argued down after the fact.
- **Fix:** restate Option A's exit as anchor-placement only, and say whether golden ±1 matching can credit B2/M2 without recognition. Then add the 789/791 site-state probe or drop it from the disposition.

**3. E2's `--max-hunks` claim is false against the current code (interacts with the M4 change).** E2 says `--max-hunks` "continues to cap TOP-LEVEL CLUSTERS pre-expansion". In `system_one_reviewer.py:2997–3009` the ceiling is applied to `kept`, which is the list *after* expansion. The receipts agree: the default run's `n_dropped: 6` comes out of 46 expanded units, not 46 clusters. §1 still calls those 46 "clusters", so the m2 wording fix only reached §3.
- **Failure:** someone implementing E2 reads "continues" as "no change needed". With roughly 168+ site units against the default ceiling of 40, sites get cut after expansion. That is exactly the cap OQ1 forbids, and the rewritten banner denominator then counts the wrong things. V2 runs with an explicit high `--max-hunks`, so it won't catch this.
- **Fix:** state it as a behavior change (move truncation ahead of expansion and count by parent cluster), and correct §1 to say 46 units from 19 clusters.

**4. Smaller issues:**
- **M7 contradiction:** E5 lines 204–206 still say `--version` "reports per-cutter availability INTO THE LEDGER". The new note directly below says `--version` writes nothing. Delete the old sentence.
- **M6 contradiction:** V3(c) still opens with "baseline findings replayed through the new compose()", which the new PREREQUISITE sentence says can't be done. Reword (c) to describe the new build's findings run twice, flat vs per-declaration compose.
- **M4 loose ends:**
  - The OQ1 entry (line 306) still says "accept the 3–6× call envelope" with no note that it's superseded.
  - V7's "re-ruled envelope" has no value and no named owner.
  - "Rerun until the census passes" lets the size floor be tightened until sites collapse back to top-level units, which quietly undoes the anchor fix. Pin the envelope with Kurt, and put a cap on how far the floor can tighten.
- **m5:** V3 cites "the three `reproof:` ranges", but `corpus-manifest.md` lists five labels across four or five ranges. Say which three.

REQUEST CHANGES