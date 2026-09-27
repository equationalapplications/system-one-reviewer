# jev-review

A local pull-request reviewer built from two ingredients: **deterministic
code** for all the plumbing, and **[Jev](https://typesafe.ai)** (TypeSafe's
System One model) for every judgment. No agent loop, no prompt engineering,
no cloud CI — one Python file, git, and an API key.

```
$ jev-review.py --repo ~/myrepo --range main..HEAD
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
cp jev-review.py ~/.local/bin/     # any PATH dir works
```

Requires: Python 3.10+, git, a TypeSafe API key. No third-party packages.

## Usage

```bash
jev-review.py --repo PATH --range A..B     # commit range
jev-review.py --repo PATH --pr N           # GitHub PR (via gh)
jev-review.py --repo PATH --staged         # staged changes
jev-review.py --repo PATH --uncommitted    # working tree

# scored run against planted issues (TSV: file, line, description)
jev-review.py --repo PATH --range A..B --golden golden.tsv --label run1

--json      machine-readable output to stdout
--out FILE  write full JSON report (all scores) to a file
```

Metrics append to `$XDG_STATE_HOME/jev-review/metrics.jsonl` (default
`~/.local/state/...`). Nothing leaves your machine except the Jev calls.

## The example fixture

```bash
examples/build-fixture.sh           # builds /tmp/jev-review-test
jev-review.py --repo /tmp/jev-review-test --range HEAD~1..HEAD \
    --golden examples/fixture-golden.tsv --label first-run
```

Five planted issues (silent-None return, unguarded division, duplicate
import, redundant argument, O(n²) loop). Current published numbers from
this fixture: recall 2/5, precision 2/3, F1 0.50 — with the two misses being
genuine nits the model deliberately scores below threshold. Thresholds and
question phrasing are meant to be tuned; the jsonl gives you the data.

## Status

Experimental, built in public. Verdicts are advisory. The evaluation
harness, per-run score logs, and honest miss analysis are the point —
treat every published number as a snapshot of the current tuning, and the
commit history as the tuning log.

## License

MIT
