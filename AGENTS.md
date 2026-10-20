# system-one-reviewer — agent notes

## Read INTENT.md first

`INTENT.md` (repo root) is this repo's charter. **Every spec must align with
it**: the INTENT file wins on *intent* (what SOR is for, what it must never
try to cover), specs win on *detail*. If a spec's goal contradicts an INTENT
rule, the spec is wrong until the INTENT is amended through PR review — do not
design around the rule silently. Judgment-affecting changes need before/after
numbers (fixture golden + Stage A golden + negative heads) in the PR.

## The interpreter gotcha (read before any tree-sitter work)

The installed binary (`~/.local/bin/system-one-reviewer`, shebang
`#!/usr/bin/env python3`) runs under a **different python3** than other tools
on this box (a hermes venv, not the kernel python). tree-sitter wheels must be
installed into THAT interpreter (`$(which python3) -m pip` from a login shell)
or the TS cutter silently falls back to line windows — same commit, different
results. Verify before any measurement run:
`python3 -c "import tree_sitter; print('ok')"` from the same shell that will
run the binary. The E5 per-cutter self-check (spec rev 4) makes measurement
runs abort on this; do not bypass it.

## Metrics ledger etiquette

`~/.local/state/jev-review/metrics.jsonl` is append-only and every run
appends. Use stable, greppable `--label`s: production runs `<scope>`, evidence
re-runs `reproof:<name>`, experiments `exp:<name>` — so audits can exclude
non-production runs from period counts. Finding TEXT is not persisted unless
you pass `--out <file>.json`; for anything you will later adjudicate or cite,
always pass `--out`.

## Measurement discipline

- Recall claims need `--golden`; precision claims need adjudicated outcomes
  (REAL/FP in writing, per the dual-review-cycle skill).
- SOR is NON-BINDING input: findings get adjudicated, never auto-fixed; a
  clean run is never merge evidence.
- SOR posts nothing anywhere. It prints reports; delivery is the caller's job.
- Coverage-incomplete runs (any `skipped[].reason` = `max-hunks>ceiling`, or
  verdict containing `status == "incomplete review"`) can never be read as Approved.

## Where decisions live

- Spec work: `docs/superpowers/specs/` (house format: problem → design →
  validation), on a branch, with measured receipts committed under
  `docs/benchmarks/` and `examples/`.
- Decision history + Fable memos: equational-wiki vault,
  `records/investigations/2026-10-19-sor-quality-fable-step0-guidance/`.
- Review ladder and label conventions: the `dual-review-cycle` skill.
