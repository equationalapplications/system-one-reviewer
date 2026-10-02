# Serialized-state census — per-cluster split projections (pre-implementation)

**Label: `hunk_state-v1 (pre-implementation)`** (AST-units plan Task 1b,
rev 14). Task 8 recomputes this table on the real `ast-units-v1`
transport; the two tables are compared there.

**Method (read-only, pure):** every `hunk>120` skip in the v06-postmerge
corpus ledgers (`corpus/work/runs/v06-postmerge`, r1 per sample) was
re-derived from the pinned SHAs (`git diff` on the ledger's
`range:` spec, same flags as `run_git`), re-packaged with the shipped
`package_hunks`, and each oversize cluster serialized with the shipped
`hunk_state` (`hunk_state-v1` wire format) + the real question triple
(`HUNK_QUESTIONS`, or `DELETION_QUESTIONS` for deletion-shaped states).
Token figures are `estimate_call_size` (Task 1 estimator: serialized
`state` + longest question, chars / `CHARS_PER_TOKEN=3.0`). Split
projection is pure arithmetic: `ceil(tokens / SOFT_CAP_TOKENS)`, min 1.
No model calls; no product code changed.

## Corpus census (max-estimating sample per file)

| repo | file | sample | change_type | est tokens | src chars | soft-cap splits |
|---|---|---|---|---:|---:|---:|
| axon-runtime | .github/workflows/release.yml | equationalapplications__axon-runtime_1_pre | code-change | 12,196 | 33,706 | 1 |
| curated-thoughts | src-tauri/src/okf/write.rs | equationalapplications__curated-thoughts_232_final | code-change | 8,209 | 81,869 | 1 |
| system-one-reviewer | tests/test_field_evals.py | equationalapplications__system-one-reviewer_2_pre | code-change | 7,923 | 20,702 | 1 |
| system-one-reviewer | scripts/mine_corpus.py | equationalapplications__system-one-reviewer_7_final | code-change | 7,822 | 20,610 | 1 |
| curated-thoughts-integrations | integrations/hermes/scripts/ct_preflight.py | equationalapplications__curated-thoughts-integrations_5_final | code-change | 6,298 | 16,537 | 1 |
| clanker | __tests__/useAIChatPhoto.test.tsx | equationalapplications__clanker_592_final | code-change | 5,777 | 15,358 | 1 |
| system-one-reviewer | scripts/score_corpus.py | equationalapplications__system-one-reviewer_7_final | code-change | 4,999 | 13,073 | 1 |
| curated-thoughts | src-tauri/src/okf/repair_scan.rs | equationalapplications__curated-thoughts_232_final | code-change | 4,112 | 10,797 | 1 |
| curated-thoughts-integrations | tests/test_install.py | equationalapplications__curated-thoughts-integrations_4_pre | code-change | 4,004 | 10,424 | 1 |
| curated-thoughts-integrations | tests/test_ct_doctor.py | equationalapplications__curated-thoughts-integrations_5_final | code-change | 3,919 | 23,758 | 1 |
| system-one-reviewer | scripts/corpus_lib.py | equationalapplications__system-one-reviewer_7_final | code-change | 3,476 | 8,824 | 1 |
| curated-thoughts-integrations | integrations/hermes/scripts/ct_env.py | equationalapplications__curated-thoughts-integrations_5_final | code-change | 3,195 | 8,041 | 1 |
| system-one-reviewer | tests/test_mine_build.py | equationalapplications__system-one-reviewer_7_final | code-change | 2,957 | 7,421 | 1 |
| curated-journal | scripts/dev-model.js | equationalapplications__curated-journal_46_pre | code-change | 2,776 | 7,188 | 1 |
| system-one-reviewer | tests/test_score_corpus.py | equationalapplications__system-one-reviewer_7_final | code-change | 2,708 | 6,758 | 1 |
| system-one-reviewer | tests/test_corpus_lib.py | equationalapplications__system-one-reviewer_7_final | code-change | 2,520 | 6,182 | 1 |
| clanker | src/hooks/useChatPhotoUpload.ts | equationalapplications__clanker_592_final | code-change | 2,513 | 6,428 | 1 |
| clanker | __tests__/chatComposer.test.tsx | equationalapplications__clanker_592_final | code-change | 2,434 | 60,091 | 1 |
| system-one-reviewer | tests/test_mine_corpus.py | equationalapplications__system-one-reviewer_7_final | code-change | 2,369 | 5,767 | 1 |
| curated-thoughts | scripts/check-release-config.mjs | equationalapplications__curated-thoughts_161_final | code-change | 2,224 | 5,549 | 1 |
| curated-thoughts-integrations | .github/workflows/ci.yml | equationalapplications__curated-thoughts-integrations_5_final | code-change | 2,186 | 5,498 | 1 |
| clanker | __tests__/chatImageBubble.test.tsx | equationalapplications__clanker_592_final | code-change | 2,169 | 5,486 | 1 |
| system-one-reviewer | tests/test_run_corpus.py | equationalapplications__system-one-reviewer_7_final | code-change | 2,106 | 5,108 | 1 |
| curated-thoughts-integrations | integrations/hermes/__init__.py | equationalapplications__curated-thoughts-integrations_5_final | code-change | 2,089 | 5,214 | 1 |
| curated-journal | __tests__/themeContrast.test.ts | equationalapplications__curated-journal_38_final | code-change | 1,981 | 4,973 | 1 |
| clanker | src/components/ChatImageBubble.tsx | equationalapplications__clanker_592_final | code-change | 1,936 | 4,780 | 1 |
| clanker | src/hooks/useAIChat.ts | equationalapplications__clanker_592_final | code-change | 1,920 | 22,543 | 1 |
| curated-journal | src/components/ui/button.tsx | equationalapplications__curated-journal_38_final | code-change | 1,856 | 4,543 | 1 |
| clanker | __tests__/useChatPhotoUpload.test.tsx | equationalapplications__clanker_592_final | code-change | 1,851 | 4,556 | 1 |
| curated-journal | src/components/ui/markdown-styles.ts | equationalapplications__curated-journal_38_final | code-change | 1,779 | 4,334 | 1 |
| curated-journal | src/components/ui/states.tsx | equationalapplications__curated-journal_38_final | code-change | 1,662 | 3,950 | 1 |
| curated-journal | src/components/ui/sheet.tsx | equationalapplications__curated-journal_38_final | code-change | 1,571 | 3,755 | 1 |

## Brief-named offenders not present as v06 corpus skips

The CTI PR #22 field triggers (whole-file adds — the runs that started
this investigation) serialized from the pinned checkouts at their two
real commits:

| repo | file | commit | est tokens | src chars | soft-cap splits |
|---|---|---|---:|---:|---:|
| curated-thoughts-integrations | integrations/deepseek/src/wisdom.ts | b6a12fc8 (542-line add) | 8,876 | 23,748 | 1 |
| curated-thoughts-integrations | integrations/deepseek/tests/test_wisdom.ts | b6a12fc8 (1019-line add) | 17,015 | 46,511 | 1 |
| curated-thoughts-integrations | integrations/deepseek/src/wisdom.ts | 8aba71e5 (507-line add) | 8,625 | 23,101 | 1 |
| curated-thoughts-integrations | integrations/deepseek/tests/test_wisdom.ts | 8aba71e5 (966-line add) | 16,053 | 43,794 | 1 |

## Findings

- **32 unique code files** measured (59 `hunk>` skip records re-derived
  across 26 samples; every re-derived diff reproduced its ledger's skip
  records). Every one of them fits in **ONE per-cluster call**: the
  worst serialized per-cluster state is 12,196 tokens
  (axon-runtime `release.yml`) — 44% of `SOFT_CAP_TOKENS=28_000` — and
  the largest test file (`test_wisdom.ts`, 17,015 tokens) stays under
  the soft cap too.
- **Zero soft-cap splits projected** on today's corpus at the shipped
  per-cluster transport (hunk_state-v1). The brief's 5-files-over-25k-
  source-chars alarm collapses when serialized per cluster: e.g.
  `write.rs` is 81,869 source chars but only ~8.2k serialized tokens
  (the skipped span was the changed region plus ±4 context, not the
  whole file), and `chatComposer.test.tsx` 60,091 chars → ~2.4k tokens.
- **Source chars vs serialized tokens diverge up to ~10×** (write.rs:
  81,869 chars vs 8,209 tokens) — the brief's r3-M6 caution is
  confirmed in both directions; the census had to be run on serialized
  state, and future gates must quote the serialized figure only.
- **Ast-unit splitting (Tasks 2/3) is engagement-insurance, not a
  measured need, on this corpus:** no oversize cluster exceeds the
  soft cap as a single per-cluster call. The estimator + guard still
  ship (Task 5) because post-enrichment states (Task 6, enclosing
  context) and future corpora can cross it — the projections here are
  pre-enrichment (r1-M5: the units-level census is recomputed for real
  in Task 8 on the `ast-units-v1` transport and compared against this
  table).
- Constants in force: `SOFT_CAP_TOKENS=28_000`,
  `HARD_CAP_TOKENS=56_000`, `CHARS_PER_TOKEN=3.0`.

## Coverage gaps (recorded, not silently dropped)

- `equationalapplications__system-one-reviewer_1_pre` and
  `equationalapplications__expo-llm-wiki_97_pre`: pinned SHAs absent
  from the local clones — their skip files
  (`jev-review.py`, `sweep-thresholds.py`, `test_package.py`,
  `test_providers.py`, `test_sweep.py`, `system_one_reviewer.py`,
  `instanceofErrorProxyGuard.test.ts`) could not be re-serialized.
  These same files also appear in OTHER samples that DID resolve
  (`system-one-reviewer_2_pre`/`_7_final`, `expo-llm-wiki_97_final`),
  so every file NAME is still represented in the table above; only the
  _pre variant of two samples is unmeasured.
- Doc/lockfile skip records (`.md`, `README.md`, lock files,
  `LICENSE`, `.gitignore`) were excluded: they are never model-judged
  (`SKIP_PATTERNS`/`DOC_EXT`/`DATA_EXT` triage), so their serialized
  size is irrelevant to the call budget.
