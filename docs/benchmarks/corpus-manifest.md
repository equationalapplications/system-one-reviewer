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
- TS fixture (v0.9, planted defects) — TBD: created during v0.9 measurement phase
  before V1 TS runs

## Negative heads (V3 precision arm)

- Fixture negative golden: `examples/fixture-negative-golden.tsv` (v0.2 evaluation)
- Five defect-free SHAs (v0.9 baseline for noise band, V3(a) measurement):
  TBD from run-1 memo's Oct 15–19 ledger (doc-only and deps-only ranges).
  Placeholder SHAs (to be confirmed):
  - (SHA1) — doc-only range
  - (SHA2) — deps-only range  
  - (SHA3) — clean head 3
  - (SHA4) — clean head 4
  - (SHA5) — clean head 5

## Reproof ranges (V3)

Pinned for v0.9 (per spec V3(a) noise-band measurement):
- `reproof:wf59-fixdelta`: SynapseTree `2577539..cb98858` (3 repeats)
- `reproof:byok-task-A1`: SynapseTree-login `fb51dd6..342f04f`
- `reproof:byok-task-A4`: SynapseTree-login `b533637..9c7918c`
- `reproof:byok-task-A5`: SynapseTree-login `3764689..effa0c0`
- `reproof:ct-61cluster`: curated-thoughts `9806333f..d40d300` (V3 noise band)
- `reproof:A6fix`: SynapseTree-login `d70d225..9e70ec0` (per-declaration majorscounting V3(c))

## 47-PR corpus

- Lives in the SOR repo under `corpus/` with replay scripts (see `corpus/README`);
  the V4/V6/V7 gates pin exact SHAs from that manifest at run time
- TODO-PIN (m5): export the corpus issue table (55 issues + 29 dismissals) into
  `docs/benchmarks/corpus-manifest.json` during S0 ledger work

## Adjudication sources

- SynapseTree-login plan doc L223–245 (A6 gate sequence; all 21 sor findings
  NON-SUSTAINED) — commit `bfe5d65`
- Oct 15–19 window runs: labels `wf:SynapseTree:59:fix-delta-nits{,2,3}`,
  `byok-task-A{1,4,5,6fix}` in `~/.local/state/jev-review/metrics.jsonl`
