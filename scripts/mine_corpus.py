#!/usr/bin/env python3
"""Mine PR review threads into corpus candidates, then build corpus TSVs.

  mine_corpus.py fetch --repo OWNER/NAME [--repo ...] [--limit N] [--corpus DIR]
  mine_corpus.py spotcheck [--corpus DIR]
  mine_corpus.py build [--private OWNER/NAME ...] [--corpus DIR]

fetch lists merged PRs' review threads via `gh api graphql`, anchors each
thread at originalLine/originalCommit (never the diff-relative position),
and records its disposition: the /fix-pr follow-up summary comment first,
else a mechanical check for a later PR commit touching the anchored lines.
Adjudication (Claude subagents) writes corpus/work/adjudicated.jsonl;
spotcheck and build are in the second half of this file.
Spec: docs/superpowers/specs/2026-09-28-corpus-eval-design.md
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus_lib as cl  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join(REPO_ROOT, "corpus")
FIXPR_HEADER = "## /fix-pr follow-up"
STATUS = re.compile(r"\*\*(Fixed|Not applied)\b[^*]*\*\*")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)
BODY_MAX = 4000

QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: MERGED, first: 20, after: $cursor,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number url baseRefOid headRefOid
        comments(first: 100) { nodes { author { login } body } }
        reviewThreads(first: 100) {
          pageInfo { hasNextPage }
          nodes {
            id isOutdated path line originalLine startLine originalStartLine diffSide
            comments(first: 1) {
              nodes { author { login } body url originalCommit { oid } }
            }
          }
        }
      }
    }
  }
}
"""


RETRYABLE = re.compile(r"\b(429|500|502|503|504)\b|timeout|timed out|connection reset",
                       re.I)
RETRY_DELAYS = (2, 5, 15, 40)


def gh_graphql(query, _sleep=None, **variables):
    """The only network call in this module (tests monkeypatch it).

    GitHub answers heavy paginated queries with 5xx/504 often enough that a
    single transient failure must not abort a multi-repo mine, so retryable
    errors are re-issued with backoff before giving up. `_sleep` is a test seam.
    """
    sleep = _sleep or time.sleep
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if v is not None:
            args += ["-f", f"{k}={v}"]
    last = ""
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            sleep(RETRY_DELAYS[attempt - 1])
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            payload = json.loads(r.stdout)
            if not payload.get("errors"):
                return payload
            last = f"graphql errors: {str(payload['errors'])[:500]}"
        else:
            last = f"gh api graphql failed: {r.stderr.strip()[:500]}"
        if not RETRYABLE.search(last):
            break
        if attempt < len(RETRY_DELAYS):
            print(f"  graphql retry {attempt + 1}/{len(RETRY_DELAYS)}: {last[:120]}",
                  file=sys.stderr)
    raise cl.CorpusError(last)


def fetch_prs(repo, limit):
    owner, name = repo.split("/")
    cursor, n = None, 0
    while True:
        data = gh_graphql(QUERY, owner=owner, name=name, cursor=cursor)
        conn = data["data"]["repository"]["pullRequests"]
        for node in conn["nodes"]:
            if limit is not None and n >= limit:
                return
            n += 1
            yield node
        if not conn["pageInfo"]["hasNextPage"]:
            return
        nxt = conn["pageInfo"]["endCursor"]
        if not nxt or nxt == cursor:
            raise cl.CorpusError(f"{repo}: pagination cursor did not advance")
        cursor = nxt


# ---------- dispositions ----------

def parse_fixpr_bullets(body):
    """[(status, bullet_line)] from a /fix-pr follow-up comment, else []."""
    if not body.lstrip().startswith(FIXPR_HEADER):
        return []
    out = []
    for line in body.splitlines():
        if not line.startswith("- **"):
            continue
        m = STATUS.search(line)
        if m:
            out.append(("fixed" if m.group(1) == "Fixed" else "not-applied", line))
    return out


def match_bullet(path, bullets):
    """The single bullet naming this file's basename, else None (absent/ambiguous)."""
    base = os.path.basename(path)
    hits = [b for b in bullets if base in b[1]]
    return hits[0] if len(hits) == 1 else None


def old_side_touches(diff_text, line, slack=2):
    """True if any `git diff -U0` hunk's old-side range is within `slack` of `line`.

    A pure insertion (`-a,0`) sits after old line a; the slack counts an added
    guard right next to the flagged line as addressing it.
    """
    for m in HUNK.finditer(diff_text):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        end = start + max(count, 1) - 1
        if start - slack <= line <= end + slack:
            return True
    return False


def first_fix_commit(repo_path, since_sha, until_sha, path, line):
    """Oldest commit in since..until whose cumulative diff touches path:line (as of since)."""
    commits = cl.git(repo_path, "log", "--reverse", "--format=%H",
                     f"{since_sha}..{until_sha}", "--", path).stdout.split()
    for c in commits:
        diff = cl.git(repo_path, "diff", "-U0", since_sha, c, "--", path).stdout
        if old_side_touches(diff, line):
            return c
    return None


def candidates_from_pr(repo, pr):
    bullets = []
    for c in pr["comments"]["nodes"]:
        bullets += parse_fixpr_bullets(c.get("body") or "")
    stats = {"left_side": 0, "no_line": 0, "no_commit": 0,
             "threads_truncated": int(pr["reviewThreads"]["pageInfo"]["hasNextPage"])}
    out = []
    for t in pr["reviewThreads"]["nodes"]:
        first = t["comments"]["nodes"][0] if t["comments"]["nodes"] else None
        if t.get("diffSide") == "LEFT":
            stats["left_side"] += 1
            continue
        if t.get("originalLine") is None or first is None:
            stats["no_line"] += 1
            continue
        commit = (first.get("originalCommit") or {}).get("oid")
        if not commit:
            stats["no_commit"] += 1
            continue
        hit = match_bullet(t["path"], bullets)
        out.append({
            "id": f"{repo}#{pr['number']}:{t['id']}", "repo": repo, "pr": pr["number"],
            "pr_url": pr["url"], "thread_url": first.get("url"),
            "reviewer": (first.get("author") or {}).get("login"),
            "body": (first.get("body") or "")[:BODY_MAX],
            "path": t["path"], "line": t["originalLine"],
            "start_line": t.get("originalStartLine"), "original_commit": commit,
            "base_ref_oid": pr["baseRefOid"], "head_ref_oid": pr["headRefOid"],
            "is_outdated": t.get("isOutdated"),
            "disposition": hit[0] if hit else "unknown",
            "disposition_source": "fix-pr" if hit else None,
            "disposition_note": hit[1] if hit else None,
            "fix_sha": None, "error": None})
    return out, stats


def mine_repo(repo, limit, url=None):
    d = cl.ensure_clone(repo, url)
    out: list[dict] = []
    totals = {"prs": 0}
    for pr in fetch_prs(repo, limit):
        totals["prs"] += 1
        cands, stats = candidates_from_pr(repo, pr)
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v
        for c in cands:
            try:
                cl.ensure_commit(d, c["original_commit"], c["pr"])
                cl.ensure_commit(d, c["head_ref_oid"], c["pr"])
            except cl.CorpusError as e:
                c["error"] = str(e)
                out.append(c)
                continue
            if c["disposition"] in ("unknown", "fixed"):
                fix = first_fix_commit(d, c["original_commit"], c["head_ref_oid"],
                                       c["path"], c["line"])
                c["fix_sha"] = fix
                if c["disposition"] == "unknown":
                    c["disposition"] = "fixed" if fix else "unaddressed"
                    c["disposition_source"] = "thread-fix"
            out.append(c)
    return out, totals


def cmd_fetch(args):
    per_repo = os.path.join(args.corpus, "work", "candidates")
    os.makedirs(per_repo, exist_ok=True)
    all_cands = []
    for repo in args.repo:
        cached = os.path.join(per_repo, repo.replace("/", "__") + ".jsonl")
        if os.path.exists(cached) and not args.force:
            cands = cl.read_jsonl(cached)
            print(f"mine: {repo}: {len(cands)} candidates (cached)")
        else:
            cands, totals = mine_repo(repo, args.limit)
            cl.write_jsonl(cached, cands)
            print(f"mine: {repo}: {len(cands)} candidates from {totals}")
        all_cands += cands
    cl.write_jsonl(os.path.join(args.corpus, "work", "candidates.jsonl"), all_cands)
    return 0


# ---------- sample ----------


def group_by_pr(candidates):
    """{(repo, pr): [candidates]}, errored rows dropped, PR keys sorted."""
    by_pr: dict[tuple, list] = {}
    for c in candidates:
        if c.get("error"):
            continue
        by_pr.setdefault((c["repo"], c["pr"]), []).append(c)
    return {k: by_pr[k] for k in sorted(by_pr)}


def repo_quotas(repos, target):
    """{repo: quota} splitting `target` evenly, remainder to the first repos."""
    base, extra = divmod(target, len(repos))
    return {r: base + (1 if i < extra else 0) for i, r in enumerate(sorted(repos))}


def sample_candidates(candidates, target, seed=0):
    """Draw ~`target` findings, whole PRs only, with a per-repo quota.

    PR-atomic by necessity: a corpus sample is a PR and scoring computes
    precision/recall per sample, so labeling part of a PR would make the
    reviewer's unlabeled findings in that PR score as false positives.

    Quotas exist because the mined pool is heavily skewed (clanker alone is
    over half of it), so a uniform draw collapses onto a handful of large PRs
    and learns nothing about the other repos. Each repo is shuffled under its
    own seed, so adding or removing a repo does not reshuffle the others.
    """
    by_pr = group_by_pr(candidates)
    per_repo: dict[str, list] = {}
    for repo, _ in by_pr:
        per_repo.setdefault(repo, [])
    for repo in per_repo:
        per_repo[repo] = [k for k in by_pr if k[0] == repo]
    out = []
    for repo, quota in repo_quotas(per_repo, target).items():
        rng = random.Random(f"{seed}:{repo}")
        keys = list(per_repo[repo])
        rng.shuffle(keys)
        n = 0
        for k in keys:
            if n >= quota:
                break
            out += by_pr[k]
            n += len(by_pr[k])
    return sorted(out, key=lambda c: c["id"])


def cmd_sample(args):
    src = os.path.join(args.corpus, "work", "candidates.jsonl")
    cands = cl.read_jsonl(src)
    if not cands:
        raise cl.CorpusError(f"no candidates at {src}; run fetch first")
    picked = sample_candidates(cands, args.target, args.seed)
    dst = os.path.join(args.corpus, "work", "sample.jsonl")
    cl.write_jsonl(dst, picked)
    prs = {(c["repo"], c["pr"]) for c in picked}
    print(f"sample: {len(picked)} findings from {len(prs)} PRs -> {dst}")
    by_repo: dict[str, list] = {}
    for c in picked:
        by_repo.setdefault(c["repo"], []).append(c)
    for repo in sorted(by_repo):
        rows = by_repo[repo]
        disp: dict[str, int] = {}
        for c in rows:
            disp[c["disposition"]] = disp.get(c["disposition"], 0) + 1
        n_prs = len({c["pr"] for c in rows})
        print(f"  {repo}: {len(rows)} findings / {n_prs} PRs  {disp}")
    return 0


# ---------- spot-check ----------

SPOT_COLS = ["candidate_id", "why", "thread", "code", "disposition", "label",
             "severity", "evidence", "verdict", "correct_label", "note"]
GATE = 0.85


def is_disagreement(disposition, label):
    return ((disposition == "fixed" and label == "false-positive")
            or (disposition in ("not-applied", "unaddressed") and label == "real-bug"))


def spotcheck_rows(adjudicated, candidates, seed=0, frac=0.2):
    rows = [a for a in sorted(adjudicated, key=lambda a: a["candidate_id"])
            if not candidates[a["candidate_id"]].get("error")]
    k = max(1, round(len(rows) * frac)) if rows else 0
    random_ids = {a["candidate_id"] for a in random.Random(seed).sample(rows, k)}
    out = []
    for a in rows:
        c = candidates[a["candidate_id"]]
        why = []
        if a["candidate_id"] in random_ids:
            why.append("random")
        if is_disagreement(c["disposition"], a["label"]):
            why.append("disagreement")
        if not why:
            continue
        out.append({
            "candidate_id": a["candidate_id"], "why": "+".join(why),
            "thread": f"[thread]({c['thread_url']})",
            "code": (f"[code](https://github.com/{c['repo']}/blob/{c['original_commit']}/"
                     f"{a['file']}#L{a['line']})"),
            "disposition": c["disposition"], "label": a["label"],
            "severity": a.get("severity_class") or "", "evidence": a.get("evidence") or "",
            "verdict": "", "correct_label": "", "note": ""})
    return out


def _esc(v):
    return str(v).replace("\n", " ").replace("\t", " ").replace("|", "\\|")


def _cells(line):
    parts = re.split(r"(?<!\\)\|", line.strip())
    return [p.strip() for p in parts[1:-1]]


def write_spot_check(path, rows):
    head = ["# Corpus spot-check", "",
            "Fill `verdict` with agree/disagree for every row. For a disagree, put the",
            "correct label (real-bug/style/false-positive/unclear) in `correct_label`.",
            f"Gate: agreement on `random` rows must be >= {GATE:.0%}.", "",
            "| " + " | ".join(SPOT_COLS) + " |",
            "|" + "---|" * len(SPOT_COLS)]
    body = ["| " + " | ".join(_esc(r[c]) for c in SPOT_COLS) + " |" for r in rows]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(head + body) + "\n")


def read_spot_check(path):
    """(overrides id->label, agreed ids, agreement over random rows | None if unfilled)."""
    overrides, agreed = {}, set()
    n_random = n_agree = 0
    unfilled = False
    with open(path) as f:
        for line in f:
            if not line.startswith("| ") or line.startswith("| candidate_id"):
                continue
            cells = _cells(line)
            if len(cells) != len(SPOT_COLS):
                raise cl.CorpusError(f"spot-check row has {len(cells)} cells: {line!r}")
            row = dict(zip(SPOT_COLS, cells, strict=True))
            verdict = row["verdict"].lower()
            if verdict not in ("agree", "disagree"):
                unfilled = True
                continue
            if "random" in row["why"]:
                n_random += 1
                n_agree += verdict == "agree"
            if verdict == "agree":
                agreed.add(row["candidate_id"])
            elif row["correct_label"]:
                if row["correct_label"] not in cl.LABELS:
                    raise cl.CorpusError(f"bad correct_label {row['correct_label']!r}")
                overrides[row["candidate_id"]] = row["correct_label"]
            else:
                overrides[row["candidate_id"]] = "unclear"
    if unfilled or n_random == 0:
        return overrides, agreed, None
    return overrides, agreed, n_agree / n_random


# ---------- build ----------

def _issue_row(sid, a, fix_sha, adjudicator, spot_checked):
    return {"sample_id": sid, "file": a["file"], "line": str(a["line"]),
            "verify_substring": a["verify_substring"],
            "severity_class": a.get("severity_class") or "minor",
            "category": a.get("category") or "", "evidence": _esc(a.get("evidence") or ""),
            "fix_sha": fix_sha or "", "adjudicator": adjudicator,
            "spot_checked": spot_checked}


def build_rows(candidates, adjudicated, overrides, agreed, promotions, verify,
               private=frozenset()):
    """Adjudications -> {"public"|"private": (prs, issues, dismissed)}, warnings.

    verify(repo, sha, pr, file, line, substring) -> error str | None.
    """
    by_pr: dict[tuple[str, int], list[tuple[dict, dict, str]]] = {}
    for a in adjudicated:
        cid = a["candidate_id"]
        if cid not in candidates:
            raise cl.CorpusError(f"adjudication for unknown candidate {cid}")
        if candidates[cid].get("error"):
            continue  # retain in candidates.jsonl for retry; drop from corpus output
        label = overrides.get(cid, a["label"])
        if label not in cl.LABELS:
            raise cl.CorpusError(f"{cid}: bad label {label!r}")
        if (cid not in overrides and label in cl.DISMISSED_LABELS
                and a.get("dismissal_reason") not in cl.DISMISSAL_REASONS):
            raise cl.CorpusError(f"{cid}: {label} needs a valid dismissal_reason")
        if label == "unclear":
            continue
        c = candidates[cid]
        by_pr.setdefault((c["repo"], c["pr"]), []).append((c, a, label))

    out: dict[str, tuple[list[dict], list[dict], list[dict]]] = {
        "public": ([], [], []), "private": ([], [], [])}
    warnings: list[str] = []
    promo_by_sid: dict[str, list[dict]] = {}
    for p in promotions:
        promo_by_sid.setdefault(p["sample_id"], []).append(p)

    for (repo, pr), rows in sorted(by_pr.items()):
        prs, issues, dismissed = out["private" if repo in private else "public"]
        split = cl.split_for(repo, pr)
        c0 = rows[0][0]
        bugs = [r for r in rows if r[2] == "real-bug"]
        pre_head = c0["original_commit"]
        if bugs:  # the commit most real bugs were reported against
            heads = [c["original_commit"] for c, _, _ in bugs]
            pre_head = max(set(heads), key=heads.count)
        pre_sid = cl.sample_id(repo, pr, "pre")
        source = "fix-pr" if any(c["disposition_source"] == "fix-pr"
                                 for c, _, _ in rows) else "thread-fix"
        verified_real_bug_rows = []
        for c, a, label in rows:
            err = verify(repo, pre_head, pr, a["file"], int(a["line"]), a["verify_substring"])
            if err:
                warnings.append(f"{c['id']}: dropped — {err}")
                continue
            cid = c["id"]
            human = cid in overrides
            checked = "y" if (human or cid in agreed) else "n"
            row = _issue_row(pre_sid, a, c.get("fix_sha"), "human" if human else "claude",
                             checked)
            if label == "real-bug":
                issues.append(row)
                verified_real_bug_rows.append((c, a, label))
            else:
                row["label"] = label
                row["dismissal_reason"] = ("other" if human and not a.get("dismissal_reason")
                                           else a.get("dismissal_reason") or "other")
                dismissed.append(row)
        if issues or dismissed:
            prs.append({"sample_id": pre_sid, "repo": repo, "base_sha": c0["base_ref_oid"],
                        "head_sha": pre_head,
                        "kind": "positive" if verified_real_bug_rows else "clean",
                        "split": split, "source": source})
        if verified_real_bug_rows and all(
                a.get("fixed_at_final") is True for _, a, _ in verified_real_bug_rows):
            fin_sid = cl.sample_id(repo, pr, "final")
            promos = promo_by_sid.get(fin_sid, [])
            verified_promos = []
            for p in promos:
                err = verify(repo, c0["head_ref_oid"], pr, p["file"], int(p["line"]),
                             p["verify_substring"])
                if err:
                    warnings.append(f"{fin_sid} promotion {p['file']}:{p['line']}: {err}")
                    continue
                verified_promos.append(p)
                issues.append(_issue_row(fin_sid, p, "", "claude", "n"))
            if not promos or verified_promos:
                prs.append({"sample_id": fin_sid, "repo": repo, "base_sha": c0["base_ref_oid"],
                            "head_sha": c0["head_ref_oid"],
                            "kind": "positive" if verified_promos else "clean",
                            "split": split,
                            "source": "promoted" if verified_promos else source})
    return out, warnings


def _verify_via_cache(repo, sha, pr, file, line, substring):
    try:
        d = cl.ensure_clone(repo)
        cl.ensure_commit(d, sha, pr)
    except cl.CorpusError as e:
        return str(e)
    return cl.verify_row(d, sha, file, line, substring)


def cmd_spotcheck(args):
    work = os.path.join(args.corpus, "work")
    cands = {c["id"]: c for c in cl.read_jsonl(os.path.join(work, "candidates.jsonl"))}
    adj = cl.read_jsonl(os.path.join(work, "adjudicated.jsonl"))
    rows = spotcheck_rows(adj, cands)
    write_spot_check(os.path.join(work, "spot-check.md"), rows)
    print(f"spotcheck: {len(rows)} rows -> {os.path.join(work, 'spot-check.md')}")
    return 0


def cmd_build(args, verify=_verify_via_cache):
    work = os.path.join(args.corpus, "work")
    sheet = os.path.join(work, "spot-check.md")
    if not os.path.exists(sheet):
        raise cl.CorpusError("no spot-check.md — run `spotcheck` and fill it in first")
    overrides, agreed, agreement = read_spot_check(sheet)
    if agreement is None:
        raise cl.CorpusError("spot-check.md is not fully filled in")
    if agreement < GATE:
        raise cl.CorpusError(f"spot-check agreement {agreement:.0%} < {GATE:.0%} — revise "
                             "the adjudication prompt and re-adjudicate")
    cands = {c["id"]: c for c in cl.read_jsonl(os.path.join(work, "candidates.jsonl"))}
    adj = cl.read_jsonl(os.path.join(work, "adjudicated.jsonl"))
    promos = cl.read_jsonl(os.path.join(work, "promotions.jsonl"))
    out, warnings = build_rows(cands, adj, overrides, agreed, promos, verify,
                               private=set(args.private or ()))
    for w in warnings:
        print(f"build: warning: {w}", file=sys.stderr)
    note = "generated by scripts/mine_corpus.py build — do not hand-edit"
    for key, root in (("public", args.corpus), ("private", os.path.join(args.corpus, "local"))):
        prs, issues, dismissed = out[key]
        if key == "private" and not prs:
            continue
        cl.write_tsv(os.path.join(root, "prs.tsv"), cl.PRS_COLS, prs, note)
        cl.write_tsv(os.path.join(root, "issues.tsv"), cl.ISSUE_COLS, issues, note)
        cl.write_tsv(os.path.join(root, "dismissed.tsv"), cl.DISMISSED_COLS, dismissed, note)
    corpus = cl.load_corpus(args.corpus)  # full validation of what was written
    share = cl.check_holdout_share(corpus["prs"])
    print(f"build: {len(corpus['prs'])} samples, {len(corpus['issues'])} issues, "
          f"{len(corpus['dismissed'])} dismissed, holdout share {share:.2f}, "
          f"agreement {agreement:.0%}, {len(warnings)} dropped")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--repo", action="append", required=True)
    f.add_argument("--limit", type=int, default=None, help="max merged PRs per repo")
    f.add_argument("--force", action="store_true",
                   help="re-mine repos that already have a cached candidates file")
    f.add_argument("--corpus", default=DEFAULT_CORPUS)
    sm = sub.add_parser("sample")
    sm.add_argument("--target", type=int, default=100, help="approx findings to draw")
    sm.add_argument("--seed", type=int, default=0)
    sm.add_argument("--corpus", default=DEFAULT_CORPUS)
    s = sub.add_parser("spotcheck")
    s.add_argument("--corpus", default=DEFAULT_CORPUS)
    b = sub.add_parser("build")
    b.add_argument("--private", action="append", help="repos whose rows go to corpus/local/")
    b.add_argument("--corpus", default=DEFAULT_CORPUS)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "fetch":
            return cmd_fetch(args)
        if args.cmd == "sample":
            return cmd_sample(args)
        if args.cmd == "spotcheck":
            return cmd_spotcheck(args)
        if args.cmd == "build":
            return cmd_build(args)
    except cl.CorpusError as e:
        print(f"mine_corpus: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
