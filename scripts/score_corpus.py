#!/usr/bin/env python3
"""Score reviewer runs against the corpus by replaying saved judgments.

  score_corpus.py --config NAME [--split train|holdout] [--replay-grid] [--json]

Reads each run's ledger record (judged[] with scores and cluster spans) and
its --out JSON (skipped clusters), re-composes judged[] through the tool's
own compose() — so threshold/rule variants cost no model calls — and
reports strict (+-1 line) and cluster recall, precision, FPs per clean PR,
findings per PR, verdict accuracy, known-FP repeats, a miss decomposition,
and repeat variance.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_lib as cl  # noqa: E402
import run_corpus as rc  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP_PATH = os.path.join(REPO_ROOT, "scripts", "sweep-thresholds.py")
MISS_BUCKETS = ("anchor-offset", "judged-below-threshold", "judged-low-severity",
                "skipped-triage", "not-judged")


def load_sweep():
    """Import sweep-thresholds.py under a private name: not registered, main() not run."""
    spec = importlib.util.spec_from_file_location(f"_sor_sweep_{uuid.uuid4().hex}",
                                                  SWEEP_PATH)
    if spec is None or spec.loader is None:
        raise cl.CorpusError(f"cannot load {SWEEP_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _span(e):
    lo = e.get("line_start", e.get("line"))
    hi = e.get("line_end", lo)
    return lo, hi


def _covers(e, file, line):
    lo, hi = _span(e)
    return e["file"] == file and lo <= line <= hi


def replay_indices(jr, sw, rec, t, dt):
    wrapped = [sw.rewrap(j, run_version=rec.get("packaging_version")) for j in rec["judged"]]
    reported, _, verdict = jr.compose(wrapped, [], None, threshold=t, deletion_threshold=dt)
    ids = {id(f) for f in reported}
    return [i for i, w in enumerate(wrapped) if id(w) in ids], reported, verdict


def classify_miss(file, line, judged, idx, skipped, t, dt):
    covering = [i for i, j in enumerate(judged) if _covers(j, file, line)]
    if any(i in idx for i in covering):
        return "anchor-offset"
    if covering:
        best = max(covering, key=lambda i: judged[i].get("is_real") or 0)
        j = judged[best]
        thr = dt if j.get("rubric") == "deletion" else t
        return ("judged-low-severity" if (j.get("is_real") or 0) >= thr
                else "judged-below-threshold")
    for s in skipped:
        if s.get("file") == file and ("line_start" not in s or _covers(s, file, line)):
            return "skipped-triage"
    return "not-judged"


def score_sample(jr, sw, sample, goldens, dismissed, rec, out, t, dt, tmpdir):
    judged = rec["judged"]
    idx, reported, verdict = replay_indices(jr, sw, rec, t, dt)
    idx_set = set(idx)
    res = {"sample_id": sample["sample_id"], "repo": sample["repo"], "kind": sample["kind"],
           "verdict": verdict, "n_reported": len(idx),
           "latency_ms": rec.get("total_latency_ms"), "golden": len(goldens),
           "strict_matched": 0, "cluster_matched": 0, "tp": 0,
           "misses": dict.fromkeys(MISS_BUCKETS, 0), "clean_fp": 0,
           "known_fp_repeats": sum(
               1 for d in dismissed
               if any(_covers(judged[i], d["file"], int(d["line"])) for i in idx))}
    if goldens:
        gpath = os.path.join(tmpdir, "golden.tsv")
        with open(gpath, "w") as f:
            for g in goldens:
                f.write(f"{g['file']}\t{g['line']}\t{g['category']}\n")
        e = jr.eval_against_golden(reported, gpath)
        missed = {(m[0], m[1]) for m in e["missed"]}
        res["tp"] = e["true_positives"]
        res["strict_matched"] = len(goldens) - len(e["missed"])
        for g in goldens:
            gf, gl = g["file"], int(g["line"])
            if any(_covers(judged[i], gf, gl) for i in idx):
                res["cluster_matched"] += 1
            if (gf, gl) in missed:
                res["misses"][classify_miss(gf, gl, judged, idx_set,
                                            (out or {}).get("skipped", []), t, dt)] += 1
    if sample["kind"] == "clean":
        counts = jr.eval_negative(reported)
        res["clean_fp"] = counts["blocker_major"] + counts["other_fp"]
    if sample["kind"] == "positive":
        serious = any(g["severity_class"] in ("blocker", "major") for g in goldens)
        res["expected_verdict"] = "Changes requested" if serious else None
    else:
        res["expected_verdict"] = "Approved"
    res["verdict_ok"] = (None if res["expected_verdict"] is None
                         else verdict == res["expected_verdict"])
    return res


def _aggregate(rows, dismissed_total):
    pos = [r for r in rows if r["kind"] == "positive"]
    clean = [r for r in rows if r["kind"] == "clean"]
    golden = sum(r["golden"] for r in pos)
    reported_pos = sum(r["n_reported"] for r in pos)
    tp = sum(r["tp"] for r in pos)
    recall = sum(r["strict_matched"] for r in pos) / golden if golden else None
    precision = tp / reported_pos if reported_pos else None
    scored = [r for r in rows if r["verdict_ok"] is not None]
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    misses = dict.fromkeys(MISS_BUCKETS, 0)
    for r in pos:
        for k, v in r["misses"].items():
            misses[k] += v
    return {
        "samples": len(rows), "positive": len(pos), "clean": len(clean),
        "golden_total": golden, "recall_strict": recall,
        "recall_cluster": sum(r["cluster_matched"] for r in pos) / golden if golden else None,
        "precision": precision,
        "f1": (2 * precision * recall / (precision + recall)
               if precision and recall else None),
        "fp_per_clean": sum(r["clean_fp"] for r in clean) / len(clean) if clean else None,
        "findings_per_pr": sum(r["n_reported"] for r in rows) / len(rows) if rows else None,
        "verdict_accuracy": (sum(r["verdict_ok"] for r in scored) / len(scored)
                             if scored else None),
        "known_fp_repeats": sum(r["known_fp_repeats"] for r in rows),
        "dismissed_total": dismissed_total, "misses": misses,
        "avg_latency_ms": sum(lat) / len(lat) if lat else None,
    }


def _load_ledger(corpus_dir, config):
    recs = {}
    for r in cl.read_jsonl(rc.ledger_path(corpus_dir, config)):
        recs[r["label"]] = r  # last write wins (re-runs with --force)
    return recs


def _variance(by_sample):
    flips, spreads, identical = 0, [], True
    for recs in by_sample.values():
        if len(recs) < 2:
            continue
        if len({json.dumps(r["judged"], sort_keys=True) for r, _ in recs}) > 1:
            identical = False
        if len({v for _, v in recs}) > 1:
            flips += 1
        scores: dict[tuple, list] = {}
        for r, _ in recs:
            for j in r["judged"]:
                scores.setdefault((j["file"], j["line"]), []).append(j.get("is_real") or 0)
        spreads += [max(v) - min(v) for v in scores.values() if len(v) > 1]
    return {"identical": identical, "verdict_flips": flips,
            "max_is_real_spread": max(spreads) if spreads else 0.0,
            "mean_is_real_spread": sum(spreads) / len(spreads) if spreads else 0.0}


def score(corpus_dir, config, split="train", jr=None, sw=None, threshold=None,
          deletion_threshold=None, repeats=None):
    sw = sw or load_sweep()
    jr = jr or sw.load_tool()
    t = jr.REAL_THRESHOLD if threshold is None else threshold
    dt = jr.DELETION_REAL_THRESHOLD if deletion_threshold is None else deletion_threshold
    corpus = cl.load_corpus(corpus_dir)
    ledger = _load_ledger(corpus_dir, config)
    samples = {sid: r for sid, r in corpus["prs"].items() if split in ("all", r["split"])}
    ks = range(1, (repeats or 1) + 1) if repeats else None
    rows: list[dict] = []
    missing: list[dict] = []
    fail_open = 0
    by_sample: dict[str, list] = {}
    dismissed_total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for sid, s in sorted(samples.items()):
            goldens = [i for i in corpus["issues"] if i["sample_id"] == sid]
            dismissed = [d for d in corpus["dismissed"] if d["sample_id"] == sid]
            dismissed_total += len(dismissed)
            k_list = ks or sorted(int(lbl.rsplit(":r", 1)[1]) for lbl in ledger
                                  if lbl.startswith(rc.label_for(config, sid, "")))
            for k in k_list or [1]:
                rec = ledger.get(rc.label_for(config, sid, k))
                if rec is None:
                    missing.append({"sample_id": sid, "k": k})
                    continue
                if rec.get("fail_open"):
                    fail_open += 1
                    continue
                path = rc.out_path(corpus_dir, config, sid, k)
                out = json.load(open(path)) if os.path.exists(path) else None
                row = score_sample(jr, sw, s, goldens, dismissed, rec, out, t, dt, tmp)
                row["k"] = k
                rows.append(row)
                by_sample.setdefault(sid, []).append((rec, row["verdict"]))
    agg = _aggregate(rows, dismissed_total)
    agg["fail_open"] = fail_open
    by_repo = {}
    for repo in sorted({r["repo"] for r in rows}):
        repo_rows = [r for r in rows if r["repo"] == repo]
        by_repo[repo] = _aggregate(repo_rows, sum(
            1 for d in corpus["dismissed"] if cl.parse_sample_id(d["sample_id"])[0] == repo
            and d["sample_id"] in samples))
    return {"config": config, "split": split, "threshold": t, "deletion_threshold": dt,
            "samples": rows, "aggregate": agg, "by_repo": by_repo,
            "variance": _variance(by_sample), "missing": missing}


def replay_grid(corpus_dir, config, split="train", jr=None, sw=None):
    sw = sw or load_sweep()
    jr = jr or sw.load_tool()
    return [{"threshold": t, **score(corpus_dir, config, split, jr=jr, sw=sw,
                                     threshold=t)["aggregate"]}
            for t in sw.GRID]


def _fmt(v):
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def render_markdown(res, grid=None):
    a = res["aggregate"]
    lines = [f"## Corpus score — config `{res['config']}`, split `{res['split']}`", "",
             f"threshold {res['threshold']}, deletion threshold {res['deletion_threshold']}",
             "", "| metric | value |", "|---|---|"]
    for label, key in (("samples (positive / clean)", None), ("golden issues", "golden_total"),
                       ("recall (strict)", "recall_strict"),
                       ("recall (cluster)", "recall_cluster"), ("precision", "precision"),
                       ("F1", "f1"), ("FPs per clean PR", "fp_per_clean"),
                       ("findings per PR", "findings_per_pr"),
                       ("verdict accuracy", "verdict_accuracy"),
                       ("known-FP repeats", "known_fp_repeats"),
                       ("fail-open runs", "fail_open"), ("avg latency ms", "avg_latency_ms")):
        val = f"{a['positive']} / {a['clean']}" if key is None else _fmt(a[key])
        lines.append(f"| {label} | {val} |")
    lines += ["", "misses: " + ", ".join(f"{k} {v}" for k, v in a["misses"].items()),
              "", "variance: " + ", ".join(f"{k} {_fmt(v)}"
                                           for k, v in res["variance"].items())]
    if res["missing"]:
        lines.append(f"\nmissing runs: {len(res['missing'])}")
    if grid:
        lines += ["", "| threshold | recall | precision | FPs/clean | verdict acc |",
                  "|---|---|---|---|---|"]
        lines += [f"| {g['threshold']} | {_fmt(g['recall_strict'])} | {_fmt(g['precision'])} "
                  f"| {_fmt(g['fp_per_clean'])} | {_fmt(g['verdict_accuracy'])} |"
                  for g in grid]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--split", choices=["train", "holdout", "all"], default="train")
    ap.add_argument("--repeats", type=int, default=None)
    ap.add_argument("--replay-grid", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--corpus", default=rc.DEFAULT_CORPUS)
    args = ap.parse_args(argv)
    try:
        res = score(args.corpus, args.config, args.split, repeats=args.repeats)
        grid = replay_grid(args.corpus, args.config, args.split) if args.replay_grid else None
    except cl.CorpusError as e:
        print(f"score_corpus: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"result": res, "grid": grid}, indent=2, default=str))
    else:
        print(render_markdown(res, grid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
