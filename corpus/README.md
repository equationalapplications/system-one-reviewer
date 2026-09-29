# Real-PR corpus

Pointer-only ground truth for evaluating system-one-reviewer on real PRs
(spec: `docs/superpowers/specs/2026-09-28-corpus-eval-design.md`).

- `prs.tsv`, `issues.tsv`, `dismissed.tsv` are **generated** by
  `scripts/mine_corpus.py build` from `corpus/work/` inputs. Don't hand-edit
  them; change the inputs (adjudications, spot-check, promotions) and rebuild.
- Every issue/dismissed row's `verify_substring` is checked against the
  pinned SHA at build time.
- Private repos live in gitignored `corpus/local/` (same schema).
- Session transcripts are never committed.

## Provenance and counts

Filled in when the corpus is built (PR 2).