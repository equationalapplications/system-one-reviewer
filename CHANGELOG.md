## [0.8.0](https://github.com/equationalapplications/system-one-reviewer/compare/v0.7.0...v0.8.0) (2026-10-04)

### Features

* **ast-units:** AST-aware sub-cluster cutter + lazy tree-sitter + line-window fallback (plan Tasks 2/3) ([fad23a1](https://github.com/equationalapplications/system-one-reviewer/commit/fad23a15e446821ac15e12855459d3810564133d))
* **budget:** HARD_CAP send gate + typed _OverBudget runtime split with injected splitter; judge() 3-tuple contract (plan Task 5) ([8aa18e7](https://github.com/equationalapplications/system-one-reviewer/commit/8aa18e7d5d84a9ae2e2a374f3974d7c6473e2034))
* **budget:** option-2 band engagement (Kurt ruling 2026-10-02) — BAND_ENGAGE_LINES=120 splits the 121-line..84k band via the Task 2/3 cutter order; band units never become unsplittable>cap leaves (G-D band-check escalation) ([5158f6c](https://github.com/equationalapplications/system-one-reviewer/commit/5158f6cf4bfc4216964160c0c47d257013960037))
* **budget:** token-based call-size estimator + 28k/56k token constants ([18eb256](https://github.com/equationalapplications/system-one-reviewer/commit/18eb256d7cc174a23d2c4026780ac4ac39766ad1))
* **enrichment:** AST enclosing-symbol + file symbol table on unit states (D3, per-unit ledger flag) ([aff0dee](https://github.com/equationalapplications/system-one-reviewer/commit/aff0dee05cd0d8b670d2ccce4a0da745525ee2ec))
* **ledger:** D7 contract stamps + v08-ast packaging version ([8395b4f](https://github.com/equationalapplications/system-one-reviewer/commit/8395b4f5d75122aec2467d298a496acc47709098))
* **units:** oversize clusters → AST sub-clusters; MAX_HUNK_LINES retired for jev; unit-consistent counters (r1-B1); --max-hunks = units-per-run (plan Task 4) ([7023edf](https://github.com/equationalapplications/system-one-reviewer/commit/7023edf26903c0ab1b04dccf8c7f335b82a10ead))

### Bug Fixes

* **release:** force conventional-changelog-writer 9 via npm overrides — the ^9 devDep pin created a third top-level copy while release-notes-generator/commit-analyzer kept their nested writer 8.4.0 (their plain ESM imports bind locally), so CI still hit the Missing helper crash; overrides dedupe every copy to 9.2.1 ([35dfd58](https://github.com/equationalapplications/system-one-reviewer/commit/35dfd585db41c2c5e115ff4074ded0e5a293a9f3))
* **release:** pin conventional-changelog-writer ^9 — semantic-release 25 + preset 10.4 requires writer 9+ (lockfile resolved 8.4.0, breaking changelog generation on main since the v0.7.0 release) ([a201b1b](https://github.com/equationalapplications/system-one-reviewer/commit/a201b1b3802789b2341dc5d7bc4b63c272ab4f85))
* **review:** Opus Task-10 r15 — B1 leaf-insertion window (all-leaf diff can never compose to clean Approved), M1 leaves before digest/compose, M2 median halving, M3 caller-gated AST cutter, M4 sub-unit anchors on runtime splits, M5 loose '-' run grouping; minors m2/m3/m5/m7/m8/m9; m1 deferred (rename plumbing), m6 documented ([7968cdb](https://github.com/equationalapplications/system-one-reviewer/commit/7968cdbae381482fceeb1d21b8b311e597c75890))
* **review:** Opus Task-10 r16 — M1 no-op single-sub AST cut falls through to line windows, M2 context-only sub-clusters glued to neighbors, M3 diff-order entry iteration (before/after text unscrambled); minors m1 double-count, m2 keep judged siblings on below-split failure, m3 transport-failure leaves don't suppress fail-open, m5 ValueError parse guard, m6 module-level merge-base cache, m7 sub-unit anchors on parse-error records ([f887c03](https://github.com/equationalapplications/system-one-reviewer/commit/f887c03321eae866ea50f636c166c27fecfa0fdc))
* **review:** Opus Task-10 r17 — B1 below-split transport failure now PARSES successful sibling carriers (leak fix r16-m2 incomplete: conversion-only discarded good judgments and could trip all-failed fail-open); M1 parse_failures reset moved back to post-success (consecutive shape errors fail open mid-run again); m1 dead shape_fail branch uses parent hunk, m2 no-op cut compares changed entries; tests for B1 + M1 ([36a3411](https://github.com/equationalapplications/system-one-reviewer/commit/36a34114383239dcfb787010d2910057a417004c))
* **review:** Opus Task-10 r18 — B1 leaf-first carrier leak (always partition records; all-leaf chains skip carrier parse), M1 glued context rebuilt in parent diff order (ast_units + ts_units), M2 deletion runs size by old-file line + halving splits at median changed-entry INDEX; r18-B1 leaf-first regression test ([4674a8d](https://github.com/equationalapplications/system-one-reviewer/commit/4674a8da7f8937458365237d1e13836c978cd5a5))
* **review:** Opus Task-10 r19 — MAJOR-1 RecursionError/MemoryError guards on all ast.parse sites + splitter wrapped inside the _OverBudget handler (sibling-clause semantics), wrong r15-m4 comment corrected; MAJOR-2 ts_units unwraps export_statement/lexical_declaration (real TS/JS symbols) + README names the real grammar packages; minors m3 untried-sibling leaves + chain growth, m4 all-leaf chains don't reset the failure counter, m5 clear_runtime_caches at main(), m6 n_changed/header count only changed lines, m7 dead code removed ([93374d3](https://github.com/equationalapplications/system-one-reviewer/commit/93374d3d858a6f470cd131fdf40c964d50c2dce9))
* **review:** Opus Task-10 r20 — M1 enrichment context picks the INNERMOST enclosing symbol (narrowest span, was head-first class header), M2 halving cut never emits a context-only half (changed half only when one side is glue), M3 below-split transport failure keeps nested added deltas (depth-cap math); r20-M2 n_analyzed=1 expectation updated in runtime-split test ([66c377b](https://github.com/equationalapplications/system-one-reviewer/commit/66c377ba5a2404beffab908b86dd9f138b2db5bd))
* **review:** r22 delta review (GLM dual-cycle) — D4/D6 dedupe the leaf-resolved net-growth predicate (one shared _net_sub_added; tok-merge arithmetic documented as contract-uniform dead code), fix stale ts_units 'rest' comment (r21-m3: changed entries outside top-level units ride with subs[0]) ([9d5aaef](https://github.com/equationalapplications/system-one-reviewer/commit/9d5aaefee1b13d42151267e029ca5cee35c429bc))
* **review:** r22 self-review (GLM dual-cycle) — revert r21 n_sent wiring (judge() meta carries no jev_calls key: KeyError on every non-JSON run; render()'s fallback was already correct), shape-fail branch mirrors r21-M1 accounting (dead today, correct if ever fired), r22-m5 ExceptHandler chain regression test; verified non-JSON main() end-to-end + token/latency single-count through nested split failure ([ee3870f](https://github.com/equationalapplications/system-one-reviewer/commit/ee3870f2a0bc27616a3f37fdd5c10a40e78a1e1b))

## [0.7.0](https://github.com/equationalapplications/system-one-reviewer/compare/v0.6.0...v0.7.0) (2026-10-02)

### Features

* **honesty:** Step 0′ — size-skipped code clusters count as unjudged ([d2a981e](https://github.com/equationalapplications/system-one-reviewer/commit/d2a981e22772e30e70f565255a97a1a33154dfa0)), closes [#9](https://github.com/equationalapplications/system-one-reviewer/issues/9)

## [0.6.0](https://github.com/equationalapplications/system-one-reviewer/compare/v0.5.0...v0.6.0) (2026-09-29)

### Features

* **corpus:** PR-atomic, repo-quota candidate sampling ([fcc7410](https://github.com/equationalapplications/system-one-reviewer/commit/fcc74106a66eceedac1d4bf2d3312621281f9dc5))
* **corpus:** v1 build — 47 samples, 85 rows, README provenance ([bb6ea12](https://github.com/equationalapplications/system-one-reviewer/commit/bb6ea120a4e07edecaeb33dec6a48c2b4b4d7945)), closes [curated-journal#27](https://github.com/equationalapplications/curated-journal/issues/27) [curated-thoughts#73](https://github.com/equationalapplications/curated-thoughts/issues/73) [equationalapplications.com#35](https://github.com/equationalapplications/equationalapplications.com/issues/35)

### Bug Fixes

* **corpus:** address CodeRabbit review — cache scope, PR-atomic errors, quota redistribution ([d6163f7](https://github.com/equationalapplications/system-one-reviewer/commit/d6163f78a82d0669f671c4ee37974740408ed593))
* **corpus:** Opus delta r2 — repair+validate dedup, dedup tests, counter reason, real round-robin test ([c31d841](https://github.com/equationalapplications/system-one-reviewer/commit/c31d841e60845b8dbfdfdaeeb2ebc75582750441)), closes [curated-journal#27](https://github.com/equationalapplications/curated-journal/issues/27)
* **corpus:** Opus delta r2 — RETRYABLE malformed-JSON, verify-then-dedup, round-robin pass-2, honest tests ([0006c5c](https://github.com/equationalapplications/system-one-reviewer/commit/0006c5c768c30e0878f5fc66376ffacbcaa866a4))
* **corpus:** Opus delta r3 — label-agnostic dedup, tested validation, verified round-robin ([36f2cf0](https://github.com/equationalapplications/system-one-reviewer/commit/36f2cf0594294a5ce1cb4a78a858a309f4eadc4a)), closes [curated-journal#27](https://github.com/equationalapplications/curated-journal/issues/27)
* **corpus:** Opus delta r4 minors — deterministic dedup tie-break, hand-edit note ([2b4c397](https://github.com/equationalapplications/system-one-reviewer/commit/2b4c39794e0ca826d527dd6d04958ad5d212062d))
* **corpus:** Opus r1 — dedup golden anchors, carry human notes into evidence, bound error retries, README corrections ([cddcae4](https://github.com/equationalapplications/system-one-reviewer/commit/cddcae421343779cd58247cc5cbdc0d0b8dd6c3e)), closes [curated-journal#27](https://github.com/equationalapplications/curated-journal/issues/27)
* **corpus:** retry transient GraphQL errors; make fetch resumable ([54c683b](https://github.com/equationalapplications/system-one-reviewer/commit/54c683b4d9003acb760f667126b9f68c7f0f4e1b))
* **corpus:** self-review round — empty-cache scope gate, working quota redistribution, regression tests ([31c23ed](https://github.com/equationalapplications/system-one-reviewer/commit/31c23ed3ce85685a0eb5832c1dfb0fb21e0b28e1))

## [0.5.0](https://github.com/equationalapplications/system-one-reviewer/compare/v0.4.0...v0.5.0) (2026-09-29)

### Features

* **corpus:** mine review threads with /fix-pr and commit-based dispositions ([63e8bbd](https://github.com/equationalapplications/system-one-reviewer/commit/63e8bbd8bafe1879a563932bf8dfe1c56e6f56bd))
* **corpus:** replay scoring with miss decomposition, variance, and threshold grid ([d267a54](https://github.com/equationalapplications/system-one-reviewer/commit/d267a54e2b47a7bd7719ef903f047ef0c696c7e9))
* **corpus:** run the reviewer per sample with an isolated metrics ledger ([49a6e23](https://github.com/equationalapplications/system-one-reviewer/commit/49a6e2379d230c06157a44fe837128ff06f87cce))
* **corpus:** schema, deterministic split, git cache, line verification ([6c47a4c](https://github.com/equationalapplications/system-one-reviewer/commit/6c47a4cb8f1a0905b8a86ecb70095d59bdea969f))
* **corpus:** spot-check sheet with 85% gate and TSV build from adjudications ([3e23599](https://github.com/equationalapplications/system-one-reviewer/commit/3e23599914808614d8ab9de0aa9c02a617265ad4))
* expose cluster line span (line_start/line_end) in reports and metrics ([936029e](https://github.com/equationalapplications/system-one-reviewer/commit/936029e32899747daab958f88d0856e5a0bb0ff5))

### Bug Fixes

* **corpus:** address PR [#7](https://github.com/equationalapplications/system-one-reviewer/issues/7) review feedback ([6c3a4b8](https://github.com/equationalapplications/system-one-reviewer/commit/6c3a4b8db6ff4cec4fdf73fccfd186b4c432abce))

## [0.4.0](https://github.com/equationalapplications/system-one-reviewer/compare/v0.3.0...v0.4.0) (2026-09-28)

### Features

* --version flag, tool_version in metrics, release build script ([a7d1be0](https://github.com/equationalapplications/system-one-reviewer/commit/a7d1be029e43bdc57579dfc5f8e8dbd3f8ac2c00))

### Bug Fixes

* **ci:** recover partial semantic-release drafts ([25b830d](https://github.com/equationalapplications/system-one-reviewer/commit/25b830d7aec2a0b4a2e93ef352c326d5a0cda188))
