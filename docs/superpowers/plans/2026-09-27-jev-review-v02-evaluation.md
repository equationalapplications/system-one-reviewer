# jev-review v0.2 Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the evaluation story for jev-review: honest fixtures, correct packaging, negative controls, a reproducible threshold sweep, and an offline test suite with CI.

**Architecture:** Single-file tool `jev-review.py` gains structured hunk entries, parameterized `compose`, per-run negative eval, and two additive CLI flags. New offline pieces: `tests/` (pytest, monkeypatched `jev_ask`), `scripts/sweep-thresholds.py` (imports the tool, replays `compose`), deterministic fixture builders in `examples/`.

**Tech Stack:** Python 3.10+ stdlib only (tool); pytest (dev); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-27-jev-review-v02-evaluation-design.md` (E1–E7). **Review trail:** `docs/superpowers/specs/2026-09-27-jev-review-v02-dispositions.md`.

## Global Constraints

- No third-party runtime deps in `jev-review.py` (stdlib only).
- metrics.jsonl changes are additive only (`tp_severities`, `fixture`, `packaging_version`).
- CLI: additive flags only — `--negative-golden FILE`, `--fixture NAME`.
- Fixture builds deterministic: fixed `GIT_AUTHOR_DATE=2026-09-27T12:00:00 +0000`, `GIT_COMMITTER_DATE` same, author/committer `jev-fixture <fixture@example.invalid>`. Both scripts end by verifying golden TSV lines against file content and printing the expected head SHA.
- No labels in fixture diffs — golden TSVs are the only label source.
- `pytest` must pass offline (no network, no API key).
- Commits: conventional summaries; branch `v02-evaluation`; merge with a regular merge commit, never squash.
- Every task ends with `python3 -m pytest tests/ -q` green (from Task 1 on) before committing.

---

### Task 1: Test harness + `sev_level` behavior change (E6)

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_sev_level.py`
- Modify: `jev-review.py` (`sev_level`, currently `int(round(v or 0))`)

**Interfaces:**
- Produces: `tests/conftest.py:load_module()` returning the loaded module with `JEV_REVIEW_METRICS` pointed at a tmp path; `sev_level(v)` semantics = `floor(v+0.5)` clamped to 0..3, `None`→0.

- [ ] **Step 1: Write conftest + failing test**

```python
# tests/conftest.py
import importlib.util, os, sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO_ROOT, "jev-review.py")

@pytest.fixture
def jr(tmp_path, monkeypatch):
    """The tool module, isolated: metrics into tmp, HOME into tmp."""
    metrics = tmp_path / "state" / "jev-review" / "metrics.jsonl"
    monkeypatch.setenv("JEV_REVIEW_METRICS", str(metrics))
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("jev_review_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "jev_review_tool", mod)
    spec.loader.exec_module(mod)
    mod.METRICS_PATH = str(metrics)
    return mod
```

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

- [ ] **Step 2: Run — expect FAIL** (`python3 -m pytest tests/test_sev_level.py -q`; `2.5→3` fails under banker's rounding)

- [ ] **Step 3: Implement**

```python
def sev_level(v):
    """Nearest integer level, halves round up (2.5 is a BLOCKER)."""
    import math
    if v is None:
        return 0
    return max(0, min(3, math.floor(v + 0.5)))
```

- [ ] **Step 4: Run — PASS**
- [ ] **Step 5: Commit** `git commit -am "fix: sev_level rounds halves up (2.5=BLOCKER); add isolated test harness"`

### Task 2: Structured hunks — packaging + hunk_state rewrite (E2)

**Files:**
- Modify: `jev-review.py` (`package_hunks`, `hunk_state`)
- Create: `tests/test_package_hunks.py`, `tests/test_hunk_state.py`

**Interfaces:**
- Produces: hunk dicts carry `entries` (list of `(kind, lineno, text)` where kind ∈ `+ - space`) alongside rendered `lines`; anchors = first `+` in the cluster's own run; windows exclude other clusters' changed entries; `hunk_state(h)` reads `h["entries"]`.

- [ ] **Step 1: Write failing tests** — cases: multi-file diff; two changes separated by 2 unchanged lines → 2 clusters; window of cluster 2 contains no `entries` of cluster 1 with kind != space; anchors 11/14 for plants 3 lines apart; deletion-only cluster anchors on the next context line, else the @@ start; empty diff → []; a context line whose text contains `": + "` lands in `before` AND `after` via `hunk_state` (not truncated).
- [ ] **Step 2: Run — expect FAIL** (anchor assertion fails today)
- [ ] **Step 3: Implement.** In `package_hunks`: keep `entries` on each hunk; anchor = `next((n for k, n, _ in run_entries if k == "+" and n), first_ctx_or_hunk_start)`; compute `changed_indices` per file once; window bounds `[max(prev_cluster_last_changed+1, g[0]-CTX), min(next_cluster_first_changed, g[-1]+CTX+1))`. Rewrite `hunk_state` to iterate `h["entries"]` (`+`→after, `-`→before, space→both). Delete the `": + "` string parsing.
- [ ] **Step 4: Run — PASS**; also run the live fixture (`jev-review --repo /tmp/jev-review-test --range HEAD~1..HEAD`) and confirm 5 distinct anchors — no API key needed to observe packaging? It is needed for judge; only assert anchors via `--json` up to judge? If key present, full run; else assert via unit tests only.
- [ ] **Step 5: Commit** `feat: structured hunk entries; own-run anchors; sealed context windows`

### Task 3: Golden eval rewrite (E3)

**Files:**
- Modify: `jev-review.py` (`eval_against_golden`)
- Modify: `examples/fixture-golden.tsv` (lines re-verified in Task 4)
- Create: `tests/test_golden.py`

**Interfaces:**
- Produces: `eval_against_golden(reported, golden_path, tol=1)` — nearest-distance assignment, findings sorted by anchor ascending; returns `golden_eval` dict with `tp_severities: [...]` added; precision labeled raw.

- [ ] **Step 1: Failing tests** — two reports 3 lines apart match distinct goldens; tie breaks to lower line; severity captured per TP; ±1 tolerance rejects distance 2.
- [ ] **Step 2: FAIL. Step 3: implement** nearest-distance matching (sort reported by (file,line); for each, nearest unmatched golden in same file with |Δ| ≤ 1; tie → lower golden line). Add `tp_severities`.
- [ ] **Step 4: PASS. Step 5: Commit** `feat: nearest-distance golden matching, ±1, tp_severities`

### Task 4: Deterministic positive fixture + baseline re-run (E1a)

**Files:**
- Rewrite: `examples/build-fixture.sh` (clean base commit → HEAD commit introduces 5 real code bugs; fixed dates/identity; golden verification block; prints expected SHA)
- Rewrite: `examples/fixture-golden.tsv` (verified lines; verification column)
- Modify: `jev-review.py` — log additive `packaging_version: "v02"` and `fixture` in `log_run`
- Create: `tests/test_fixture_labels.py` (parses the TSV verification block, checks against a fresh build if `/tmp/jev-review-test` exists)

- [ ] Steps: rewrite script → run it → verify SHA stability (rebuild twice, same SHA) → update TSV → 3 live runs `--golden ... --label v02-baseline-N --fixture positive` → commit script+TSV+code stamp. Fixture content: base has `find_user` returning sentinel with caller check, guarded `divide`, single import, `"".join` loop, `open(path)`; HEAD flips each to the bug (no comments).

### Task 5: Negative fixture + eval_negative + flags (E1b, E4)

**Files:**
- Create: `examples/build-negative-fixture.sh`, `examples/negative-golden.tsv`
- Modify: `jev-review.py` (`eval_negative(reported)`, `--negative-golden`, `--fixture`)
- Create: `tests/test_negative.py`

**Interfaces:** `eval_negative` returns `{"blocker_major": N, "minor_notes": N, "other_fp": N}`; combined precision is NOT computed here.

- [ ] Steps: TDD `eval_negative` → add flags (wired into `log_run`/`golden_eval` path) → write builder (rename, import reorder, whitespace, one comment+docstring, README change) → rebuild-twice SHA check → 1 live negative run → commit.

### Task 6: `compose(threshold=...)` + jitter param (E5)

**Files:** Modify `jev-review.py` (`compose` signature, `near` calls); `tests/test_compose.py`
- [ ] Tests: blocker→Changes requested; two majors→CR; single minor→Approved; jitter uses the parameter; gate moves with threshold. Commit.

### Task 7: Sweep script (E5)

**Files:** Create `scripts/sweep-thresholds.py`, `tests/test_sweep.py`
- Loads module via conftest-style loader; args `--metrics --golden --negative-golden --fixture-positive --fixture-negative --labels`; rejects `packaging_version != v02` or `head` ≠ committed expected SHA; re-wraps flat `judged` into `compose`'s shape; combined curve = per-threshold min F1; candidate = argmax (tie→middle); prints table + every-run margin check; writes the markdown table to stdout for `docs/benchmarks/`.
- [ ] TDD with a synthetic metrics file. Commit.

### Task 8: Run the protocol, publish numbers (E5 + Verification)

- [ ] Ensure ≥3 fresh positive runs + ≥3 negative runs on rebuilt fixtures; run sweep; apply the change rule (likely: 0.50 holds — margin 0.20 in every run is a high bar); write `docs/benchmarks/2026-09-27-threshold-sweep.md` with table + committed metrics lines; check negative merge gate (0 BLOCKER/MAJOR in all runs). Commit.

### Task 9: CI (E7)

**Files:** Create `.github/workflows/ci.yml`
- [ ] pytest matrix 3.10/3.12, `pip install pytest`, no secrets. Commit.

### Task 10: README refresh

- [ ] Correct miss count, publish refreshed numbers with run labels, document `--negative-golden`/`--fixture`, note sev_level behavior change, link the benchmark doc. Commit.

### Task 11: PR + dual review of the diff

- [ ] Push branch, open PR (base main). Run dual-review cycle on the range `main..v02-evaluation` (GLM self-review + `opus-review --repo . --range main..v02-evaluation`), fix BLOCKER/MAJOR, then merge with a regular merge commit when green.
