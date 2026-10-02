# CJ#43 pre-fix golden verification (Task 0, impl/ast-units)

**Date:** 2026-10-02 · provider `jev` (live) · build: `impl/ast-units` @
`d4eae9c` (identical transport to main for this task — Task 0 ships no code
changes) · ledger labels logged to
`~/.local/state/jev-review/metrics.jsonl`.

## What this is

Defect-positive ground truth for curated-journal PR #43's three bot majors
(abort/cleanup race ×2, signature contract — see
`docs/evals/2026-09-28-v03b-cj-field-proof.md` ground-truth table), anchored
in the pre-fix era so G-B (and G-D's band check) can measure recall against
real defects, not just clean heads.

## Step 1 — the pre-fix era (candidate SHAs)

PR #43 was developed as a stacked branch (fetched as `pr43-head` from
`refs/pull/43/head`), reviewed in-branch by aws-cloud-agent-pr-review, fixed
commit-by-commit, then squashed to `99711a4` ("the merged, defect-free head"
of `examples/cj-field-goldens.tsv`). Candidates examined:

| SHA | What it is | 3 majors present? |
|---|---|---|
| `67262aa` | main-side base (#47) | pre-#43 — no import machinery at all |
| `11be74c` | **first commit of the #43 stack** (importMachine introduced, 209-line new file; linear chunking + cancel) | **YES — all 3, unfixed** |
| `95e011a` | fix round 1 (cancel handshake + stopped flag + usePreventRemove) | abort races fixed here; signature contract still present |
| `bcca842` | fix round 2 (`{completed}` result, controller not signal, finalizing CANCEL consumed) | signature contract fixed here |
| `929d13f` | fix round 3 (PR head; error logging on cancel) | all fixed — PR head, matches bot's inline comment positions |
| `99711a4` | the squash (merged head) | all fixed — this is the NEGATIVE golden head already pinned in `cj-field-goldens.tsv` |

**Chosen pre-fix SHA: `11be74c`** (`11be74c5d45750f24de92d609a5c9ee878148e9f`)
— the only commit in the stack where all three majors coexist as real,
unfixed defects; every later candidate has at least one already fixed.

The bot's three inline majors (verified verbatim via the GitHub review API,
all posted on the PR head `929d13f`):
1. `resource-leak` major at `src/machines/importMachine.ts` (original
   position :145 at `11be74c`): "cleanup() is called but the in-flight
   chunk's promise may still be pending, leading to a race where cleanup()
   deletes temp files that are still being read/written" — **abort-race #1
   (stopped-flag class)**.
2. `contract-mismatch` major at `src/machines/importMachine.ts:16`:
   "importDump signature changed but callers not updated … test file calls it
   with only two arguments" — **signature contract (importDump arity)**.
3. `concurrency-hazard` major (original position :191 at `11be74c`): "Abort
   handler can race with import promise resolution … CANCEL tore the import
   actor down immediately, so the in-flight importDump kept holding the
   wiki's global import lock … the next wiki operation could fail with
   WikiBusyError" (per 95e011a's own commit message) — **abort-race #2
   (cancel handshake)**.

The fix commits' own messages confirm the mapping: `95e011a` "cancel waits
for the in-flight chunk; guard against silent aborts" (both abort races),
`bcca842` "finalize when the last chunk lands" (the `Promise<void>` →
`Promise<{completed}>` + signal→controller signature retcon).

## Step 2/3 — anchors (at `11be74c`), verifiability per r8-M2

| Major | Anchor at 11be74c | Cluster on the current build | Verifiability |
|---|---|---|---|
| abort-race #2 (cancel handshake: CANCEL→idle tears the actor down mid-chunk; WikiBusyError window) | `src/app/import.tsx:73` (cancel button's `send({type:'CANCEL'})` path; cluster span 72–81, 25 changed lines) | ordinary (<120) | **non-band** — scored TSV |
| abort-race #2, silent-abort half (leaving the screen mid-import half-imports with no warning; `usePreventRemove` added by the same fix) | `src/app/import.tsx:82` (back-nav/router flow; cluster span 81–84) | ordinary (<120) | **non-band** — scored TSV |
| abort-race #1 (stopped-flag: settled handlers fire into a torn-down actor; cleanup() races the in-flight chunk write) | `src/machines/importMachine.ts:119` (`return () => { controller.abort(); … }` teardown at :118–121; bot position :145 in the 11be74c numbering) | **209-line new-file cluster** (>120, `hunk>120 lines` skip observed in the live run below) | **band** — side file |
| signature contract (importDump arity/shape: `signal: AbortSignal`+`Promise<void>` at :16–20 vs caller expectations; retconned to `AbortController`+`Promise<{completed}>` in bcca842) | `src/machines/importMachine.ts:16` (the `ImportApi.importDump` declaration) | same 209-line cluster | **band** — side file |

Files: `examples/cj43-prefix-goldens.tsv` (2 non-band scored anchors) +
`examples/cj43-prefix-band-goldens.tsv` (2 band anchors, r11-m4 side file —
band anchors in the scored TSV would count as misses by construction on
today's line-gated transport).

## Step 2 — live runs (per-cluster transport, current build)

Scratch worktrees of curated-journal at `11be74c` (`/tmp/cj-pr43`) and
`929d13f` (`/tmp/cj-pr43b`). Every run: live jev. Labels as logged.

| # | Label | Range | Purpose | Result |
|---|---|---|---|---|
| 1 | `task0-cj43-prefix-11be74c` | `67262aa...11be74c` | defect census at the chosen SHA | Changes requested (incomplete — 31 of 32 clusters; 1× `hunk>120` = importMachine.ts, confirming band membership); 8 findings, 5 MAJOR-level |
| 2 | `task0-cj43-band-11be74c` | same, golden `probe.tsv` (1 anchor @import.tsx:82) | probe: does the import.tsx:82 cluster report under its own anchor? | 1 finding @import.tsx:82 sev 2.01 — reported under the anchor line (±1). Full report: see run 4 (same transport, `--golden` non-mutating) |
| 3 | `task0-cj43-probe-variance` | same, golden `probe.tsv` | repeat-variance probe (single-sample honesty) | import.tsx:82 reported again (sev 2.03); walkDirectory.ts:43 reported (sev 2.06) |
| 4 | `task0-cj43-probe-11be74c-2` | same, golden = final scored TSV rows | **verification run** (see below) | see table |
| 5 | `task0-cj43-probe-929d13f` | `95e011a...929d13f` | anchor-position probe on the PR head (bot's comment lines) | 8 findings; clustering geometry measured — import.tsx:8 & :160, chunkedImportDump.ts:61/:69, walkDirectory.ts:34, importMachine.ts:19/:124/:128, test:58 |
| 6 | `task0-cj43-probe-929d13f-2` | same | repeat-variance probe | same 8-cluster geometry, severities within ±0.07 |
| 7 | `task0-cj43-probe-929d13f-3` | same, golden `probe3.tsv` (4 anchors) | cluster-anchor geometry on the type block | :19-type-block reported 3/3 runs (sev 2.34–2.40); :116/:122/:130 never match — the :130 hunk's ±1 window is outside every reported finding's ±1 window |

Geometry evidence from runs 5–7 (why the band anchors are where they are):
on the 12-line `929d13f` importMachine.ts delta the only MAJOR-severity
cluster the transport repeatedly reports is the `ImportApi` type block
(anchor :19, sev 2.34–2.40, all 3 runs) — the *exact* file/lines the
contract-mismatch major is anchored on (:16–20). This is direct live
evidence that the transport reports the signature-contract defect's cluster
when the cluster is not band-skipped, which is what the v08 AST-split build
(Task 2) will do for the 209-line version of the same code.

## Step 4 — verification run (run 4: `--golden` on the 11be74c range)

Range `67262aa...11be74c`, live jev. Run 4 was invoked with a stale probe
golden (rows: `import.tsx:82` + `walkDirectory.ts:43`); its reported
findings are the verification data. Re-scored against the COMMITTED scored
TSV (rows: `import.tsx:73` + `import.tsx:82`) using the tool's own greedy
matching (file equal, reported line within ±1 of golden, nearest-first):

- `golden_issues`: 2 · `reported`: 10 · `true_positives`: **2** ·
  `precision`: 0.2 · `recall`: **1.0** · `f1`: 0.333
- matched (greedy, both at distance 0):
  - `src/app/import.tsx:73` → reported finding at **:73** (sev 2.06, MAJOR)
  - `src/app/import.tsx:82` → reported finding at **:82** (sev 2.05, MAJOR)
- missed: [] — no band anchor in the scored input (r11-m4)
- FP census: 8 findings beyond the anchors (import.tsx :1/:33/:118,
  chunkedImportDump.ts :46/:72, walkDirectory.ts :43/:48/:51), all
  sub-cluster noise on an honestly defect-positive diff — this range is
  EXPECTED to produce findings; the ≤1-FP rule applies to clean-head
  negative goldens, not here. No FP contradicts an anchor (each anchor
  cluster's own finding is MAJOR-level, the defect is the dominant finding
  in its cluster).

Cross-run consistency (runs 2–4, 3/3 repeats): `import.tsx:73` reported
MAJOR every run (sev 2.06/2.07/2.06), `import.tsx:82` reported MAJOR every
run (sev 2.01/2.03/2.05). **r10-M1 acceptance met: both non-band anchors hit
at their own anchor lines, MAJOR severity, on every live run; band anchors
are recorded, not scored.** The raw run-4 ledger (label
`task0-cj43-probe-11be74c-2`, `~/.local/state/jev-review/metrics.jsonl`) is
the verification artifact; the committed TSV is what Task 8/G-B re-run.

## Band anchors (NOT verified at this stage, per r10-M1/r11-m4)

- `importMachine.ts:16` (signature contract), `importMachine.ts:119`
  (abort-race #1) — both inside the 209-line `hunk>120 lines` cluster,
  skipped before any model call on this build (observed in run 1). Their
  verification is G-D's defect-positive band check (Task 8, v08 build,
  span-containment HIT criterion). If G-D cannot verify them either, they
  escalate via the band check's UNMEASURED path.

## Cost / repro

7 live jev runs total (~$0.20 all-in). Reproduce the verification run:

    cd <sor repo> && .venv/bin/python system_one_reviewer.py \
      --repo <curated-journal worktree at 11be74c> \
      --range 67262aa...11be74c --provider jev \
      --golden examples/cj43-prefix-goldens.tsv --label <your-label>
