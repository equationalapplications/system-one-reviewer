# Corpus manifest (m5) — pinned inputs for v0.9 validation gates

Created 2026-10-19. Every gate that says "the corpus", "the negative heads", or
"the reproof ranges" resolves here. Anything marked TODO-PIN is committed before
the corresponding gate runs.

## Golden (positive)

- Stage A 8-defect golden: `examples/golden-stageA-8defects.tsv`
- Range: `fb51dd6..d70d225` (SynapseTree-login); defects byte-verified at `d70d225`
- Receipts: `docs/benchmarks/2026-10-19-golden-run-{default,full,tsunits,rootcause}.json`

## Fixture (v0.2-era, saturated)

- `examples/fixture-golden.tsv` (Python, 5 plants) — the V1 Python leg
- `examples/ts-fixture-golden.tsv` (TypeScript, 3 plants, built by
  `examples/build-ts-fixture.sh`) — the V1 TS leg (spec m4). Head SHA pinned
  in `examples/fixture-shas.txt` as `positive_ts=`. Plants exercise E2 site
  kinds directly: a non-literal object-property assignment (plant 1), a
  call-argument swap (plant 2), and a ternary/conditional polarity flip
  (plant 3) — so the TS leg measures the SAME cutting path E2 ships.

## Negative heads (V3 precision arm)

- Fixture negative golden: `examples/negative-golden.tsv` (v0.2 evaluation;
  head `5ca6f0137d25da5180adcbc97bbcafbb4313bdc3`, `examples/fixture-shas.txt`)
- Five defect-free heads (v0.9 V1(a)/V3(a) noise-band baseline — the Oct
  15–19 window-run heads whose SOR findings were adjudicated 0/21
  NON-SUSTAINED per the A6 gate sequence; SynapseTree-login, full 40-char
  SHAs verified against the local clone 2026-10-19):
  - `byok-task-A1`: `fb51dd6f03ef93eff961d670646790d4ca421cb2`
    `..342f04faea426ab89c48b95d231d739e060cd171`
  - `byok-task-A2`: `342f04faea426ab89c48b95d231d739e060cd171`
    `..2aa4fbc7f0b580ec5d080650f375856c97a73550`
  - `byok-task-A3`: `2aa4fbc7f0b580ec5d080650f375856c97a73550`
    `..466cd5be4ec0cca8eb7ec06b410b21636778b74d`
  - `byok-task-A4`: `b5336372e691d74c0bbf3d5921972b265e9fb4d9`
    `..9c7918c57cf199630211dc6f14adaa0f05f689a2`
  - `byok-task-A5`: `3764689547e4e66e51e4a6a7ef727381006baf26`
    `..effa0c0422475dc5df7737919ab8fc97614a6367`

## Reproof ranges (V3)

Pinned for v0.9 (per spec V3(a) noise-band measurement; full 40-char SHAs
verified against local clones 2026-10-19):
- `reproof:A6fix`: SynapseTree-login
  `d70d225353776438b86b7c042e694f1ae90f9ee6`
  `..9e70ec0c4ca977eb00f29ed77806c1a152d00b19`
- `reproof:ct-61cluster`: curated-thoughts
  `9806333ff0e94057653976da446293f12b7a0c1e`
  `..d40d30014e986793290f7ab746e5e35fe91080b9` (1 commit in range; "61cluster"
  names the measured code-cluster count on this diff, not the commit count)
- `reproof:wf59-fixdelta`: SynapseTree
  `2577539d078f563b552d0942b1a38b4ce7ce48b6`
  `..cb98858f045503834495285db3abf0dc67f01cb0` (×3 repeats: labels
  `wf:SynapseTree:59:fix-delta-nits{,2,3}` in metrics.jsonl, all at this
  same head — the existing 3-repeat baseline this V3(a) noise band reuses)

## 47-PR corpus

- Lives in the SOR repo under `corpus/` with replay scripts (see `corpus/README`);
  the V4/V6/V7 gates pin exact SHAs from that manifest at run time
- TODO-PIN (m5): export the corpus issue table (55 issues + 29 dismissals) into
  `docs/benchmarks/corpus-manifest.json` during S0 ledger work

## Adjudication sources

- SynapseTree-login plan doc L223–245 (A6 gate sequence; all 21 sor findings
  NON-SUSTAINED) — commit `bfe5d65`
- Oct 15–19 fix-window runs (seven total, per ROADMAP S1): labels
  `wf:SynapseTree:59:fix-delta-nits{,2,3}` (3 repeats, one head: `cb98858`),
  `byok-task-A{1,4,5,6fix}` (4 more) in `~/.local/state/jev-review/metrics.jsonl`
  — A1/A2/A3/A4/A5 (five distinct SynapseTree-login heads) are the
  dedicated negative-head arm pinned above; A6fix is additionally
  promoted to a reproof RANGE per spec V3(a) (its head, `9e70ec0`, is the
  SAME commit the Stage A golden's defects were fixed at); the
  thrice-repeated `wf:...fix-delta` head (`cb98858`, a different repo:
  SynapseTree, not SynapseTree-login) is the dedicated
  `reproof:wf59-fixdelta` range.
