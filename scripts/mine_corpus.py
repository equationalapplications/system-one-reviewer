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
import re
import subprocess
import sys

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


def gh_graphql(query, **variables):
    """The only network call in this module (tests monkeypatch it)."""
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if v is not None:
            args += ["-f", f"{k}={v}"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise cl.CorpusError(f"gh api graphql failed: {r.stderr.strip()[:500]}")
    return json.loads(r.stdout)


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
        cursor = conn["pageInfo"]["endCursor"]


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
    all_cands = []
    for repo in args.repo:
        cands, totals = mine_repo(repo, args.limit)
        print(f"mine: {repo}: {len(cands)} candidates from {totals}")
        all_cands += cands
    cl.write_jsonl(os.path.join(args.corpus, "work", "candidates.jsonl"), all_cands)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--repo", action="append", required=True)
    f.add_argument("--limit", type=int, default=None, help="max merged PRs per repo")
    f.add_argument("--corpus", default=DEFAULT_CORPUS)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "fetch":
            return cmd_fetch(args)
    except cl.CorpusError as e:
        print(f"mine_corpus: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
