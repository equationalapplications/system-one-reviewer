# jev-review v0.2 Evaluation — Implementation Plan (rev 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Rev 2 note (Task 12, E8):** provider abstraction added — `--provider jev|laya`, local inference via the `laya` package behind the same answers contract. Task 11 executes after Task 12.

**Goal:** Complete the evaluation story for jev-review: honest fixtures, correct packaging, negative controls, a reproducible threshold sweep, and an offline test suite with CI.

**Architecture:** Single-file tool `jev-review.py` gains structured hunk entries, parameterized `compose`, per-run negative eval, and additive CLI flags/fields. New offline pieces: `tests/` (pytest, monkeypatched `jev_ask`), `scripts/sweep-thresholds.py` (imports the tool, replays `compose`), deterministic fixture builders in `examples/`.

**Tech Stack:** Python 3.10+ stdlib only (tool); pytest (dev); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-27-jev-review-v02-evaluation-design.md` (E1–E7). **Review trail:** `docs/superpowers/specs/2026-09-27-jev-review-v02-dispositions.md`.

## Global Constraints

- No third-party runtime deps in `jev-review.py` (stdlib only).
- metrics.jsonl changes are additive only: `golden_eval.tp_severities`, `golden_eval.negative_eval` (when the negative flag is passed), top-level `fixture`, `packaging_version`, `fixture_head`.
- CLI additive flags on `jev-review.py`: `--negative-golden FILE`, `--fixture NAME`.
- Fixture builds deterministic: `GIT_AUTHOR_DATE=GIT_COMMITTER_DATE=2026-09-27T12:00:00 +0000`, author/committer `jev-fixture <fixture@example.invalid>`. Build scripts take their root from `ROOT=${JEV_FIXTURE_ROOT:-/tmp/<name>}`; they end by verifying every golden TSV line (extra TSV columns: description, then verification substring, then expected severity class) against the actual file content, and by printing the head SHA. Expected SHAs live as committed constants in `examples/fixture-shas.txt` (`name=full40`), read by both the build scripts (assert) and the sweep (gate).
- No labels in fixture diffs — golden TSVs are the only label source.
- `pytest` passes offline (no network, no API key); conftest also `monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)`.
- Every task: `git add <explicit paths>` (new files are never staged by `-a`), then commit; `python3 -m pytest tests/ -q` green before committing. Branch `v02-evaluation`; merge = regular merge commit, never squash, and only after Task 8's merge gate is re-checked at final head.

---

### Task 1: Test harness + `sev_level` behavior change (E6)

**Files:**
- Create: `tests/conftest.py`, `tests/test_sev_level.py`
- Modify: `jev-review.py` (`sev_level`; add `import math` to the top-level imports, not inside the function)

**Interfaces:**
- Produces: conftest `jr` fixture (module loaded via `spec_from_file_location` with `JEV_REVIEW_METRICS`, `HOME` in tmp and `TYPESAFE_API_KEY` unset); `sev_level(v)` = `floor(v+0.5)` clamped 0..3, `None`→0.

- [ ] **Step 1: Write conftest + failing tests** (conftest as designed in cycle-1 review — `jr` sets env before `exec_module`, then re-points `mod.METRICS_PATH`)

```python
# tests/test_sev_level.py
def test_halves_round_up(jr):
    assert jr.sev_level(0.5) == 1
    assert jr.sev_level(1.5) == 2
    assert jr.sev_level(2.5) == 3          # banker's rounding said 2

def test_clamping_and_none(jr):
    assert jr.sev_level(-1) == 0
    assert jr.sev_level(None) == 0
    assert jr.sev_level(9) == 3
    assert jr.sev_level(2.6) == 3
```

- [ ] **Step 2: Run — expect FAIL** (`2.5→3` fails under banker's rounding)
- [ ] **Step 3: Implement**

```python
def sev_level(v):
    """Nearest integer level, halves round up (2.5 is a BLOCKER)."""
    if v is None:
        return 0
    return max(0, min(3, math.floor(v + 0.5)))
```

- [ ] **Step 4: Run — PASS**
- [ ] **Step 5: Commit** — `git add tests/conftest.py tests/test_sev_level.py jev-review.py && git commit -m "fix: sev_level rounds halves up (2.5=BLOCKER); add isolated test harness"`

### Task 2: Structured hunks — packaging + hunk_state rewrite (E2)

**Files:**
- Modify: `jev-review.py` (`package_hunks`, `hunk_state`; fix the stale "separated by <=2 unchanged lines" docstring; add the new flags to the module usage docstring)
- Create: `tests/test_package_hunks.py`, `tests/test_hunk_state.py`, `tests/data/v01-fixture.diff` (saved now from the current v0.1 fixture: `git -C /tmp/jev-review-test diff HEAD~1..HEAD > tests/data/v01-fixture.diff`)

**Interfaces:**
- Produces: hunk dicts carry `entries` (list of `(kind, lineno, text, hunk_start)`; kind ∈ `+ - space`; `lineno=None` for `-` lines) alongside rendered `lines`. Windows are clamped at `@@` hunk boundaries (entries know their `hunk_start`). Anchor rules: first `+` in the cluster's own run → else the first context entry with a lineno at/after the run → else the run's `hunk_start`. `hunk_state(h)` reads `entries` only.

- [ ] **Step 1: Write failing tests** — from `tests/data/v01-fixture.diff`, `package_hunks` yields anchors exactly `[11, 14, 17, 20, 26]` (offline regression for the anchor bug); multi-file diff; 2 unchanged lines between changes → 2 clusters; cluster 2's window contains no `kind != space` entries of cluster 1; no window crosses an `@@` boundary; empty diff → `[]`. `hunk_state`: a context line whose text contains `": + "` lands in both `before` and `after` untruncated.
- [ ] **Step 2: Run — expect FAIL** (anchors are `[11, 11, 14, 17, 26]` today)
- [ ] **Step 3: Implement** (structured entries, own-run anchor, window clamp to neighboring changed indices and hunk boundaries, `hunk_state` from entries; docstring + usage fixes)
- [ ] **Step 4: PASS**
- [ ] **Step 5: Commit** — `git add tests/ jev-review.py && git commit -m "feat: structured hunk entries; own-run anchors; sealed, hunk-bounded windows"`

### Task 3: Golden eval rewrite (E3)

**Files:**
- Modify: `jev-review.py` (`eval_against_golden`)
- Create: `tests/test_golden.py` (synthetic TSVs in `tmp_path` — the real TSV is Task 4's deliverable)

**Interfaces:**
- `eval_against_golden(reported, golden_path, tol=1)`: reported sorted by `(file, line)`; nearest unmatched golden within ±1, ties → lower golden line; returns dict with `tp_severities: [reported severity per TP]`. Field name `precision` is unchanged (additive-only rule); render output and README label it "raw precision" — no rename.

- [ ] Steps: failing tests (3-lines-apart distinct matches; tie; tolerance rejects distance 2; severity capture) → FAIL → implement → PASS → commit `feat: nearest-distance golden matching, ±1, tp_severities` (`git add tests/test_golden.py jev-review.py`)

### Task 4: Deterministic positive fixture + `--fixture` flag + baseline re-runs (E1a, part of E4)

**Files:**
- Rewrite: `examples/build-fixture.sh`, `examples/fixture-golden.tsv`
- Modify: `jev-review.py` — log additive `packaging_version: "v02"`, `fixture`, `fixture_head` (FULL 40-char SHA — the existing `head` field stays truncated for display; the SHA gate compares `fixture_head`)
- Create: `tests/test_fixture_labels.py` (builds both scripts into `tmp_path` via `JEV_FIXTURE_ROOT`, asserts head == `examples/fixture-shas.txt` constant and every verification substring matches its golden line)

**The fixture, fully specified (M8).** `src/app.py`, base commit:

```python
import json

def load_config(path):
    with open(path) as f:
        return json.load(f)

def find_user(users, uid, missing=None):
    for u in users:
        if u.id == uid:
            return u
    return missing

def divide(a, b):
    if b == 0:
        return None
    return a / b

def render(items):
    return ",".join(str(i) for i in items)
```

HEAD commit introduces exactly five bugs as code (severity class in parens is golden metadata only, never in the diff):

1. `load_config` reads with write mode — `open(path, "w")` (BLOCKER: truncates the file it is supposed to read)
2. `find_user` drops the `missing` sentinel, returns `None` while `render` still treats callers as sentinel-checked (MAJOR: silent-missing contract break)
3. `divide` loses the zero guard (MAJOR: ZeroDivisionError)
4. duplicate `import json` appended at the bottom (MINOR, style)
5. `render` becomes `out = ""` / `out += str(i) + ","` loop (MINOR, performance)

Golden TSV (`file<TAB>line<TAB>desc<TAB>verify-substring<TAB>severity-class`), lines verified mechanically by the build script against HEAD content; expected severities: BLOCKER, MAJOR, MAJOR, MINOR, MINOR.

- [ ] Steps: rewrite script + TSV → build twice, assert identical SHA; commit SHA constant to `examples/fixture-shas.txt` → add `--fixture` flag + the three additive metric fields (failing test first) → **3 live runs** `--golden ... --label v02-baseline-N --fixture positive` (each ~6 Jev calls) → commit (`git add examples/ jev-review.py tests/test_fixture_labels.py ...`)

### Task 5: Negative fixture + `eval_negative` + `--negative-golden` (E1b, E4)

**Files:**
- Create: `examples/build-negative-fixture.sh`, `examples/negative-golden.tsv`, `tests/test_negative.py`
- Modify: `jev-review.py` (`eval_negative(reported)`; `--negative-golden` triggers it; result stored additively at `golden_eval.negative_eval`)

**Interfaces:** `eval_negative` → `{"blocker_major": N, "minor_notes": N, "other_fp": N}` where minor-note := `sev_level(severity)==1 and category=="style"`; combined precision is NOT computed here. Negative fixture (base→HEAD, all benign code): rename local `items`→`entries` in `render`-precursor, reorder the two imports, reformat one block's whitespace, add one comment + one docstring, plus a README.md change asserted **skipped** by `triage` (asserted in `tests/test_negative.py` from the built diff — never judged).

- [ ] Steps: TDD `eval_negative` → flags + additive field → builder + SHA constant → 3 live runs `--fixture negative --negative-golden ...` → commit (explicit adds).

### Task 6: `compose(threshold=...)` + plumbing tests (E5/E6: M6 items)

**Files:** Modify `jev-review.py`; Create `tests/test_compose.py`, `tests/test_judge.py`, `tests/test_triage.py`, `tests/test_api_key.py`

- `compose(findings, skipped, pr_level, threshold=REAL_THRESHOLD)` — gate AND jitter `near()` use the parameter.
- Tests (these are where `jev_ask` is monkeypatched): fail-open (CALL_FAIL_LIMIT consecutive raises → `(None, latencies)`); `parse_error` record on malformed payload; triage lockfile/docs skips + oversize flag; `load_api_key` env-beats-file, fallback order, `SystemExit` message.

- [ ] TDD each; commit in two commits (compose param; plumbing tests) with explicit adds.

### Task 7: Sweep script (E5)

**Files:** Create `scripts/sweep-thresholds.py` (with its own `load_tool()` via `spec_from_file_location` — a script cannot import conftest), `tests/test_sweep.py`

**Defined formulas (M7):**
- Thresholds `t = round(0.30 + 0.05*k, 2)`, k = 0..8, then **excluded** if `abs(t - 0.80) <= 0.05` (plateau rule; drops 0.75, leaving 0.30–0.70).
- Per positive run i at threshold t: `TP_i` (nearest-distance match per Task 3), `FP_pos_i` = unmatched reported MINOR-style notes excluded; `FP_neg` = negative-run blocker_major + other_fp counts, averaged across the N negative runs.
- `precision_i = TP_i / (TP_i + FP_pos_i + FP_neg_mean)`; `recall_i`; `F1_i`; combined curve = **min over i**; candidate = argmax of combined curve; even-size tie → the **lower** of the two middle thresholds.
- Table columns: t, TP range, FP_pos range, FP_neg_mean, Δ-FP-neg vs 0.50, per-run F1, min-F1; candidate must beat 0.50 by ≥0.20 min-F1 AND Δ-FP-neg ≤ 0 in every negative run (both rules printed with their verdicts).

- [ ] TDD on a synthetic metrics file (`packaging_version` gate, SHA gate, re-wrap into `compose`'s `f["hunk"]` shape, curve combination, tie rule). Commit.

### Task 8: Run the protocol, publish numbers, merge gate (E5 + Verification)

- [ ] Verify ≥3 fresh positive + ≥3 negative runs exist on the rebuilt fixtures (full `fixture_head` logged); run the sweep; write `docs/benchmarks/2026-09-27-threshold-sweep.md` (table + the exact committed metrics lines); evaluate the change rule (0.50 is the expected winner).
- [ ] **Merge gate:** zero blocker_major in EVERY negative run at the shipped threshold. If failed: threshold stays, analysis goes into the PR description, and a v0.3 issue is filed (include the issue link). Commit benchmark docs.

### Task 9: CI (E7)

**Files:** Create `.github/workflows/ci.yml` — pytest matrix 3.10/3.12, `pip install pytest`, no secrets, no network. Includes `tests/test_fixture_labels.py` (builds run in CI via `JEV_FIXTURE_ROOT`). Commit.

### Task 10: README refresh

- [ ] Correct miss count; refreshed numbers with run labels and "raw precision" labeling; document `--negative-golden`/`--fixture`; note the sev_level behavior change; link the benchmark doc. Commit.

### Task 12: Provider abstraction — hosted Jev or local Laya (E8)

**Files:**
- Modify: `jev-review.py` (provider facade, flags, metrics fields)
- Create: `tests/test_providers.py`
- Modify: `README.md` (providers section)

**Interfaces:**
- Provider contract: `ask(state, questions) -> (payload, latency_ms)` with
  `payload["answers"][name]` carrying `score`/`noul`/`choice` (+ optional
  `probabilities`, `confidence`). Both providers implement it; `judge`,
  `judge_pr_level`, and the sweep only ever see the contract.
- CLI: `--provider {jev,laya}` (default from `SOR_PROVIDER` env, else
  `jev`), `--model` (laya checkpoint). Unknown provider exits with a
  one-line error. Metrics records gain additive `provider` and `model`.
- Jev path: existing client unchanged behind the facade.
- Laya path: lazy `import laya`; `Router()` (or `load(--model)`);
  `predict(state, questions)`; keep the router instance for the process
  lifetime (one model load per run). If the package or weights are
  missing → clean error with the pip line.
- The sweep groups runs by `(provider, model)`; mixing providers in one
  table row is a hard error.

- [ ] Step 1: Failing tests — facade dispatch (jev → injected fake transport; laya → injected fake router object); unknown provider exit; `--model` passthrough; metrics carry provider/model; sweep grouping rejects mixed providers.
- [ ] Step 2: FAIL. Step 3: implement. Step 4: PASS.
- [ ] Step 5: (optional, if weights are downloadable) one live laya run on the positive fixture for a smoke check; otherwise mark the laya path tested-by-fake in the README table footnote.
- [ ] Step 6: Commit `feat: provider abstraction — hosted (jev) or local (laya) system one models` (explicit adds).

### Task 11: PR + dual review of the diff + gated merge

- [ ] Push, open PR (base `main`). Dual-review cycle on `main..v02-evaluation` (GLM self-review + `opus-review --repo . --range main..v02-evaluation`); fix BLOCKER/MAJOR.
- [ ] **Before merge, re-verify at final head:** CI green, pytest green, merge gate still holds (any commit after Task 8 can invalidate it). Merge with a regular merge commit.
