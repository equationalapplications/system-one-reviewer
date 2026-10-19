# Opus r2 dispositions — SOR v0.9 spec rev 5 (delta review; REQUEST CHANGES)

Adjudication by Tessera (controller), 2026-10-19. All four r2 items REAL; all
fixed in rev 6.

- **Item 1 (m3 not actually fixed) REAL.** The `spec`/`specs` directory
  components were still in the E6 routing set. Fixed: directory set is now
  {`tests`, `test`, `__tests__`} + basename rules.
- **Item 2 (M2 partly fixed) REAL.** (a) The promised 789/791 site-state probe
  was missing — now written into V2 pre-flight (site units judged 3× each,
  measuring whether site anchors land within ±1 AND cross the 0.80 gate
  without domain facts). (b) THE FORK's Option A exit restated: anchor-
  placement verification only; honest fallback exit is 0/8 recall with the
  anchor mechanism in place (per §2(a), B2/M2 need anchor AND recognition).
- **Item 3 (E2 `--max-hunks` claim false) REAL.** The ceiling today applies
  POST-expansion to `kept` (default run's 6 drops came from 46 expanded
  units). E2 now states this as a BEHAVIOR CHANGE: truncation moves ahead of
  expansion, counted by parent cluster; admitted clusters' sites are never
  truncated. §1 wording corrected to units-from-clusters.
- **Item 4 REAL (all sub-items).** E5's stale "INTO THE LEDGER via --version"
  sentence deleted (the per-run check stamps the ledger). V3(c) reworded to
  the new-build flat-vs-per-declaration comparison. OQ1 carries its
  superseded-in-part note. V7 pinned to a concrete proposed envelope (median
  ≤ 5×, pending Kurt confirm), floor tightening capped at TWO iterations, and
  a tightening that drives median site size above 120 lines is forbidden
  (would silently undo the anchor fix).
