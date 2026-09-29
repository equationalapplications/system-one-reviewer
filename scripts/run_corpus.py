#!/usr/bin/env python3
"""Run system-one-reviewer over corpus samples.

  run_corpus.py --config NAME [--split train|holdout|all] [--repeats K] [--force]

Each sample runs `--range base...head --json --out <runs>/<sample>/r<k>.json`
with label corpus:<config>:<sample_id>:r<k>. JEV_REVIEW_METRICS points at
corpus/work/runs/<config>/metrics.jsonl so corpus runs never touch the
personal ledger. Existing outputs are skipped (resume) unless --force.
The reviewer under test is this checkout's system_one_reviewer.py.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_lib as cl  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join(REPO_ROOT, "corpus")
TOOL = [sys.executable, os.path.join(REPO_ROOT, "system_one_reviewer.py")]


def run_dir(corpus_dir, config):
    return os.path.join(corpus_dir, "work", "runs", config)


def ledger_path(corpus_dir, config):
    return os.path.join(run_dir(corpus_dir, config), "metrics.jsonl")


def label_for(config, sample_id, k):
    return f"corpus:{config}:{sample_id}:r{k}"


def out_path(corpus_dir, config, sample_id, k):
    safe = sample_id.replace("/", "__").replace("#", "_").replace("@", "_")
    return os.path.join(run_dir(corpus_dir, config), safe, f"r{k}.json")


def plan_runs(corpus, corpus_dir, config, split, repeats):
    specs = []
    for sid, r in sorted(corpus["prs"].items()):
        if split != "all" and r["split"] != split:
            continue
        _, pr, _ = cl.parse_sample_id(sid)
        for k in range(1, repeats + 1):
            specs.append({"sample_id": sid, "k": k, "repo": r["repo"], "pr": pr,
                          "base": r["base_sha"], "head": r["head_sha"],
                          "out": out_path(corpus_dir, config, sid, k),
                          "label": label_for(config, sid, k)})
    return specs


def build_cmd(tool, repo_path, spec):
    return [*tool, "--repo", repo_path, "--range", f"{spec['base']}...{spec['head']}",
            "--json", "--out", spec["out"], "--label", spec["label"]]


def prepare_checkout(spec):
    d = cl.ensure_clone(spec["repo"])
    cl.ensure_commit(d, spec["base"], spec["pr"])
    cl.ensure_commit(d, spec["head"], spec["pr"])
    return d


def run_all(specs, tool, corpus_dir, config, force=False, prepare=prepare_checkout,
            runner=subprocess.run):
    env = dict(os.environ)
    env["JEV_REVIEW_METRICS"] = ledger_path(corpus_dir, config)
    ledger_labels = {r.get("label") for r in cl.read_jsonl(env["JEV_REVIEW_METRICS"])}
    os.makedirs(run_dir(corpus_dir, config), exist_ok=True)
    failed = []
    for i, spec in enumerate(specs, 1):
        if (os.path.exists(spec["out"]) and spec["label"] in ledger_labels
                and not force):
            continue
        os.makedirs(os.path.dirname(spec["out"]), exist_ok=True)
        r = runner(build_cmd(tool, prepare(spec), spec), env=env,
                   capture_output=True, text=True)
        status = "ok" if r.returncode == 0 else "FAILED"
        print(f"run_corpus: [{i}/{len(specs)}] {spec['label']} {status}")
        if r.returncode != 0:
            failed.append((spec["label"], (r.stderr or "").strip()[-500:]))
    return failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, help="name of this reviewer build/experiment")
    ap.add_argument("--split", choices=["train", "holdout", "all"], default="train")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    args = ap.parse_args(argv)
    try:
        corpus = cl.load_corpus(args.corpus)
        specs = plan_runs(corpus, args.corpus, args.config, args.split, args.repeats)
        failed = run_all(specs, TOOL, args.corpus, args.config, force=args.force)
    except cl.CorpusError as e:
        print(f"run_corpus: {e}", file=sys.stderr)
        return 1
    for label, err in failed:
        print(f"run_corpus: FAILED {label}: {err}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
