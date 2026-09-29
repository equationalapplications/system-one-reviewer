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
