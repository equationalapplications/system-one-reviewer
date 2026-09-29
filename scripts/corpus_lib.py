"""Shared corpus schema, split, and checkout helpers (stdlib only).

The corpus is pointers, not code: corpus/*.tsv name a repo, SHAs, a file
and a line, and every golden/dismissed row carries a verify_substring that
must appear on that line at that SHA. Spec:
docs/superpowers/specs/2026-09-28-corpus-eval-design.md
"""

import hashlib
import json
import os
import re
import subprocess

PRS_COLS = ["sample_id", "repo", "base_sha", "head_sha", "kind", "split", "source"]
ISSUE_COLS = ["sample_id", "file", "line", "verify_substring", "severity_class",
              "category", "evidence", "fix_sha", "adjudicator", "spot_checked"]
DISMISSED_COLS = ISSUE_COLS + ["label", "dismissal_reason"]

KINDS = {"positive", "clean"}
SPLITS = {"train", "holdout"}
SOURCES = {"fix-pr", "thread-fix", "session", "injected", "promoted"}
SEVERITY_CLASSES = {"blocker", "major", "minor"}
LABELS = {"real-bug", "style", "false-positive", "unclear"}
DISMISSED_LABELS = {"false-positive", "style"}
DISMISSAL_REASONS = {"missing-context", "test-code", "style-nit", "hallucinated",
                     "change-reaction", "duplicate", "other"}

SAMPLE_ID = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)#(?P<pr>\d+)@(?P<phase>pre|final)$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
HOLDOUT_MOD, HOLDOUT_BELOW = 10, 3


class CorpusError(Exception):
    pass


def sample_id(repo, pr, phase):
    return f"{repo}#{pr}@{phase}"


def parse_sample_id(sid):
    m = SAMPLE_ID.match(sid)
    if not m:
        raise CorpusError(f"bad sample_id {sid!r} (want owner/repo#N@pre|final)")
    return m["repo"], int(m["pr"]), m["phase"]


def split_for(repo, pr):
    """Deterministic and PR-atomic: both samples of a PR share one split."""
    h = int(hashlib.sha256(f"{repo}#{pr}".encode()).hexdigest(), 16)
    return "holdout" if h % HOLDOUT_MOD < HOLDOUT_BELOW else "train"


# ---------- files ----------

def read_tsv(path, cols):
    rows = []
    with open(path) as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts == cols:
                continue  # header row
            if len(parts) != len(cols):
                raise CorpusError(f"{path}:{n}: expected {len(cols)} columns, "
                                  f"got {len(parts)}")
            rows.append(dict(zip(cols, parts, strict=True)))
    return rows


def write_tsv(path, cols, rows, comment=""):
    lines = [f"# {c}" for c in comment.splitlines()]
    lines.append("\t".join(cols))
    for r in rows:
        vals = [str(r[c]) for c in cols]
        for v in vals:
            if "\t" in v or "\n" in v:
                raise CorpusError(f"tab/newline in TSV value {v!r}")
        lines.append("\t".join(vals))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def read_jsonl(path):
    """Rows from a JSONL file, ignoring `# ` comment lines (write_jsonl meta)."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f
                if line.strip() and not line.startswith("# ")]


def write_jsonl(path, rows, meta=None):
    """Write rows as JSONL. `meta` dict goes on an optional `# ` first line."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        if meta:
            f.write("# " + json.dumps(meta, sort_keys=True) + "\n")
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def read_meta(path):
    """{} or the parsed `# {...}` first line written by write_jsonl(meta=...)."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            return json.loads(line[2:]) if line.startswith("# ") else {}
    return {}


# ---------- corpus ----------

def load_corpus(root):
    """Merge corpus/ and (if present) corpus/local/, validating everything."""
    prs: dict[str, dict] = {}
    issues: list[dict] = []
    dismissed: list[dict] = []
    for d in (root, os.path.join(root, "local")):
        p = os.path.join(d, "prs.tsv")
        if not os.path.exists(p):
            continue
        for r in read_tsv(p, PRS_COLS):
            if r["sample_id"] in prs:
                raise CorpusError(f"duplicate sample_id {r['sample_id']}")
            prs[r["sample_id"]] = r
        for name, cols, dest in (("issues.tsv", ISSUE_COLS, issues),
                                 ("dismissed.tsv", DISMISSED_COLS, dismissed)):
            q = os.path.join(d, name)
            if os.path.exists(q):
                dest.extend(read_tsv(q, cols))
    validate(prs, issues, dismissed)
    return {"prs": prs, "issues": issues, "dismissed": dismissed}


def validate(prs, issues, dismissed):
    for sid, r in prs.items():
        repo, pr, _phase = parse_sample_id(sid)
        if r["repo"] != repo:
            raise CorpusError(f"{sid}: repo column {r['repo']!r} does not match id")
        if r["kind"] not in KINDS:
            raise CorpusError(f"{sid}: bad kind {r['kind']!r}")
        if r["source"] not in SOURCES:
            raise CorpusError(f"{sid}: bad source {r['source']!r}")
        if r["split"] != split_for(repo, pr):
            raise CorpusError(f"{sid}: split {r['split']!r} != hash split "
                              f"{split_for(repo, pr)!r}")
        for k in ("base_sha", "head_sha"):
            if not SHA40.match(r[k]):
                raise CorpusError(f"{sid}: {k} is not a 40-char sha")
    for rows, what in ((issues, "issue"), (dismissed, "dismissed")):
        for r in rows:
            if r["sample_id"] not in prs:
                raise CorpusError(f"{what} row for unknown sample {r['sample_id']}")
            if not r["line"].isdigit() or int(r["line"]) < 1:
                raise CorpusError(f"{what} {r['sample_id']} {r['file']}: "
                                  f"bad line {r['line']!r}")
            if r["severity_class"] not in SEVERITY_CLASSES:
                raise CorpusError(f"{what} {r['sample_id']}: bad severity_class "
                                  f"{r['severity_class']!r}")
    for r in issues:
        if prs[r["sample_id"]]["kind"] != "positive":
            raise CorpusError(f"issue on non-positive sample {r['sample_id']}")
    for r in dismissed:
        if r["label"] not in DISMISSED_LABELS:
            raise CorpusError(f"dismissed {r['sample_id']}: bad label {r['label']!r}")
        if r["dismissal_reason"] not in DISMISSAL_REASONS:
            raise CorpusError(f"dismissed {r['sample_id']}: bad dismissal_reason "
                              f"{r['dismissal_reason']!r}")
    seen: set[tuple[str, str, str]] = set()
    for rows in (issues, dismissed):
        for r in rows:
            key = (r["sample_id"], r["file"], r["line"])
            if key in seen:
                raise CorpusError(
                    f"duplicate anchor {key[0]} {key[1]}:{key[2]} — the scorer "
                    "pairs one golden per finding, so a duplicated anchor caps "
                    "recall; rebuild (build_rows dedupes) or repair the TSV")
            seen.add(key)


def check_holdout_share(prs, lo=0.25, hi=0.35, min_prs=10):
    """Aggregate holdout share over distinct PRs; fails loudly when skewed."""
    splits = {}
    for sid, r in prs.items():
        repo, pr, _ = parse_sample_id(sid)
        splits[(repo, pr)] = r["split"]
    if not splits:
        return 0.0
    share = sum(s == "holdout" for s in splits.values()) / len(splits)
    if len(splits) >= min_prs and not lo <= share <= hi:
        raise CorpusError(f"holdout share {share:.2f} over {len(splits)} PRs is outside "
                          f"[{lo}, {hi}] — mine more PRs or document the skew")
    return share


# ---------- git cache ----------

def cache_root():
    return os.environ.get("SOR_CORPUS_CACHE", os.path.expanduser("~/.cache/sor-corpus"))


def repo_dir(repo):
    return os.path.join(cache_root(), *repo.split("/"))


def git(path, *args, check=True):
    r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise CorpusError(f"git {' '.join(args)} failed in {path}: {r.stderr.strip()}")
    return r


def ensure_clone(repo, url=None):
    d = repo_dir(repo)
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(os.path.dirname(d), exist_ok=True)
        r = subprocess.run(["git", "clone", "--quiet", url or f"git@github.com:{repo}.git", d],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise CorpusError(f"clone {repo} failed: {r.stderr.strip()}")
    return d


def _has_commit(path, sha):
    return git(path, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def ensure_commit(path, sha, pr):
    """Make `sha` available, fetching the PR head ref (merged branches get deleted)."""
    if _has_commit(path, sha):
        return
    git(path, "fetch", "--quiet", "origin", f"+refs/pull/{pr}/head:refs/sor/pr/{pr}",
        check=False)
    if not _has_commit(path, sha):
        raise CorpusError(f"{sha[:10]} not reachable in {path} even after fetching "
                          f"pull/{pr}/head")


def verify_row(path, sha, file, line, substring):
    """None if `substring` is on `line` of `file` at `sha`, else an error string."""
    r = git(path, "show", f"{sha}:{file}", check=False)
    if r.returncode != 0:
        return f"{file} missing at {sha[:10]}"
    lines = r.stdout.splitlines()
    if not 1 <= line <= len(lines):
        return f"{file}:{line} out of range at {sha[:10]} ({len(lines)} lines)"
    if substring not in lines[line - 1]:
        return f"{file}:{line} at {sha[:10]} lacks {substring!r}: {lines[line - 1]!r}"
    return None
