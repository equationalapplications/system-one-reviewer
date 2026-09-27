# jev-review

A local pull-request reviewer built from two ingredients: **deterministic
code** for all the plumbing, and **[Jev](https://typesafe.ai)** (TypeSafe's
System One model) for every judgment. No agent loop, no prompt engineering,
no cloud CI — one Python file, git, and an API key.

```
$ system-one-reviewer --repo ~/myrepo --range main..HEAD
JEV REVIEW (experimental local reviewer — advisory only)
repo=myrepo mode=range:main..HEAD head=13fa9d8a3e
analyzed=5 hunks, skipped=0, total_latency=785ms, jev_calls=5

[MAJOR] src/app.py:11 (bug-risk, is_real=0.61)
  hunk: @@ src/app.py around line 11 (4 changed lines) @@
    ...

PR-level risk: 2.1/3, needs_human_review=0.93
Verdict: Changes requested
```

## Why this shape

- **Jev owns judgments; code owns everything else.** Diff gathering, triage,
  packaging, thresholds, and the verdict composition are ordinary
  deterministic Python. Jev answers typed questions (severity Score,
  true-positive Noul, category Choice) about each change — under ~100 ms and
  fractions of a cent per call, cheap enough to run on *every* diff.
- **One batched round-trip per change cluster.** Changes are isolated into
  clusters (no gap-merging) so no change dilutes another; each cluster is one
  Jev call with three questions.
- **Structured state beats raw diffs.** Hunk state is sent as explicit
  `code_before_change` / `code_after_change` lists. This one choice moved a
  planted bug's true-positive score from 0.36 to 0.69 in our fixture runs.
- **Measurement is the loop, not an afterthought.** Every run appends all
  scores (reported or not) to a local jsonl, and `--golden` scores precision /
  recall / F1 against planted issues. We built the reviewer by iterating on
  that loop — F1 went 0.0 → 0.29 → 0.50 across three design changes — and
  the loop ships with the tool.

## Install

```bash
export TYPESAFE_API_KEY=...        # or ~/.config/jev-review/.env
cp system_one_reviewer.py ~/.local/bin/system-one-reviewer   # any PATH dir works
```

Requires: Python 3.10+, git, a TypeSafe API key. No third-party packages.

## Usage

```bash
system-one-reviewer --repo PATH --range A..B     # commit range
system-one-reviewer --repo PATH --pr N           # GitHub PR (needs a local pr/N ref: git fetch origin pull/N/head:pr/N)
system-one-reviewer --repo PATH --staged         # staged changes
system-one-reviewer --repo PATH --uncommitted    # working tree

# scored run against planted issues (TSV: file, line, description)
system-one-reviewer --repo PATH --range A..B --golden golden.tsv --label run1

# negative (all-benign) fixture: FP census instead of precision/recall
system-one-reviewer --repo PATH --range A..B --negative-golden negative.tsv --label run2

# declare which committed fixture a run exercises (recorded in metrics;
# the threshold sweep refuses runs whose head SHA doesn't match it)
system-one-reviewer --repo PATH --range A..B --fixture positive --label run3

--json      machine-readable output to stdout
--out FILE  write full JSON report (all scores) to a file
```

Metrics append to `$XDG_STATE_HOME/jev-review/metrics.jsonl` (default
`~/.local/state/...`). Nothing leaves your machine except the model calls.

## Providers: hosted Jev or local Laya

Every judgment goes through one contract — `ask(state, questions) ->
(payload, latency_ms)` — with two interchangeable providers:

| provider | flag | backend | status |
|---|---|---|---|
| `jev` | `--provider jev` (default; `SOR_PROVIDER` env also works) | hosted TypeSafe System One, `TYPESAFE_API_KEY` | live-tested (all published numbers) |
| `laya` | `--provider laya`, checkpoint via `--model` (default `convaiinnovations/rl-agent`) | local inference via the `laya` package (`pip install laya`) | **tested-by-fake**: contract covered by `tests/test_providers.py`; no live run yet (no local weights at publish time) |

`laya` imports lazily, so the tool keeps zero hard dependencies; a missing
package or checkpoint exits with a one-line fix hint. Metrics records carry
additive `provider` and `model` fields, and the threshold sweep
(`scripts/sweep-thresholds.py`) only compares runs within one
(provider, model) group — mixing providers is a hard error.

## The example fixture

```bash
examples/build-fixture.sh           # builds /tmp/jev-review-pos
system-one-reviewer --repo /tmp/jev-review-pos --range HEAD~1..HEAD \
    --golden examples/fixture-golden.tsv --label first-run
```

Five planted issues (silent-None return, unguarded division, duplicate
import, redundant argument, O(n²) loop). Current published numbers from
this fixture (runs `v02-r2-baseline-1..3`, 2026-09-27, provider `jev`):
**recall 5/5, raw precision 5/5 (1.00), F1 1.00** — identical across all
three fresh runs. "Raw precision" counts reported-findings on the positive
fixture only; on the negative fixture the same runs report **zero**
findings of any kind (`v02-r2-negative-1..3`). All five plants were
found and matched, including the O(n²) loop nit (scored 0.71–0.72) —
an earlier "4/5 with one miss" reading was a golden-placement artifact,
not a model miss (see the benchmark doc's correction note). Caveat
honesty: a 5-plant fixture's ceiling is 1.00; the number measures this
fixture, not general recall. The sweep confirms lowering the gate buys
nothing: the whole 0.30–0.55 region ties at F1 1.00, and raising it
starts losing the silent-None cluster (scored 0.57–0.59). Threshold
stays at 0.50. Full sweep table, merge-gate
evaluation, and the exact metrics lines:
[docs/benchmarks/2026-09-27-threshold-sweep.md](docs/benchmarks/2026-09-27-threshold-sweep.md).

(Supersedes the earlier `v02-final-*` numbers, which were a packaging
artifact: the old fixture packed two plants into one change cluster, so
they were never judged separately.)

Note: severity levels now round halves **up** (`sev_level(2.5)` is a
BLOCKER; previously banker's rounding made it a MAJOR). A fractional
severity of 2.5+ can flip a verdict from Approved to Changes requested, so
v0.2 verdicts are not directly comparable with v0.1 logs.

## Status

Experimental, built in public. Verdicts are advisory. The evaluation
harness, per-run score logs, and honest miss analysis are the point —
treat every published number as a snapshot of the current tuning, and the
commit history as the tuning log.

## License

MIT
