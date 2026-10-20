#!/usr/bin/env python3
"""Model-off coverage census for ast_context enrichment.

    enrichment_census.py --repo DIR --head REV --golden FILE.tsv [--json]

For each golden row (file<TAB>line<TAB>...), build the ast_context the
reviewer would attach to a unit starting at that line, from the file as it
is at REV, and report: did an enclosing symbol resolve, and does the
head-first context window actually CONTAIN the golden line. The window
shows the first ENRICHMENT_MAX_CONTEXT_LINES lines of the innermost
symbol, so a defect deep inside a long function is outside it; run this
before any on/off model A/B so a null result is not really a window bug.

Costs nothing: no model call, no network. The golden line stands in for a
unit's first line (a real unit may start earlier).
"""

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_tool() -> Any:
    spec = importlib.util.spec_from_file_location(
        "system_one_reviewer", os.path.join(REPO_ROOT, "system_one_reviewer.py"))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_golden(path: str) -> list[tuple[str, int]]:
    rows = []
    with open(path) as f:
        for ln in f:
            if ln.strip() and not ln.startswith("#"):
                parts = ln.rstrip("\n").split("\t")
                rows.append((parts[0], int(parts[1])))
    return rows


def git_show(repo: str, rev: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def window_start(tool: Any, path: str, src: str, line: int) -> int | None:
    """First source line of the window build_ast_context shows for `line`:
    the start of the innermost enclosing symbol, or None."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in tool.TS_LANGUAGE_BY_EXT:
        derived = tool._ts_parse(src, ext)
        best = tool._ts_enclosing_span(derived[1], line) if derived else None
        return None if best is None else best[0]
    import ast
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    best_key = None
    for node, _chain in tool._walk_with_parents(tree):
        end = getattr(node, "end_lineno", None)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) or end is None \
                or not node.lineno <= line <= end:
            continue
        key = (end - node.lineno, -node.lineno)
        if best_key is None or key < best_key:
            best_key = key
    return None if best_key is None else -best_key[1]


def census(tool: Any, repo: str, rev: str,
           rows: list[tuple[str, int]]) -> list[dict]:
    out = []
    for path, line in rows:
        src = git_show(repo, rev, path)
        rec: dict = {"file": path, "line": line, "enriched": False,
                     "enclosing": None, "window": 0, "covered": False,
                     "missing": src is None}
        if src is not None:
            unit = {"file": path, "line": line, "change_type": "code-change",
                    "entries": []}
            ctx = tool.build_ast_context(path, None, src, unit)
            if ctx is not None:
                start = window_start(tool, path, src, line)
                rec.update(enriched=True, enclosing=ctx["enclosing"],
                           window=len(ctx["context"]),
                           covered=start is not None
                           and start <= line < start + len(ctx["context"]))
        out.append(rec)
    return out


def summarize(recs: list[dict]) -> dict:
    n = len(recs)
    enriched = [r for r in recs if r["enriched"]]
    return {"rows": n, "missing": sum(r["missing"] for r in recs),
            "enriched": len(enriched),
            "covered": sum(r["covered"] for r in recs),
            "median_window": statistics.median([r["window"] for r in enriched])
            if enriched else 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--head", required=True, help="revision the golden lines refer to")
    ap.add_argument("--golden", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = read_golden(args.golden)
    if any(os.path.splitext(p)[1].lower().lstrip(".") in
           ("ts", "tsx", "js", "jsx", "mjs", "cjs") for p, _ in rows):
        # without the wheels every TS row reads "not enriched", which looks
        # like poor coverage; make it an abort instead (AGENTS.md
        # interpreter gotcha)
        for mod in ("tree_sitter", "tree_sitter_typescript",
                    "tree_sitter_javascript"):
            if importlib.util.find_spec(mod) is None:
                print(f"enrichment_census: {mod} not importable under "
                      f"{sys.executable}; install the wheels into the "
                      f"interpreter that runs the reviewer", file=sys.stderr)
                return 3
    recs = census(load_tool(), args.repo, args.head, rows)
    summ = summarize(recs)
    if args.json:
        print(json.dumps({"summary": summ, "rows": recs}, indent=2))
    else:
        for r in recs:
            print(f"{r['file']}:{r['line']}\t"
                  f"{'MISSING-AT-REV ' if r['missing'] else ''}"
                  f"enriched={r['enriched']}"
                  f"\tcovered={r['covered']}\twindow={r['window']}"
                  f"\t{r['enclosing']}")
        print(f"enriched {summ['enriched']}/{summ['rows']}, window covers the "
              f"golden line in {summ['covered']}/{summ['rows']}, "
              f"median window {summ['median_window']} lines")
        if summ["missing"]:
            print(f"{summ['missing']} row(s) could not be read at "
                  f"{args.head}: wrong repo or revision?", file=sys.stderr)
    return 1 if summ["missing"] == summ["rows"] else 0


if __name__ == "__main__":
    sys.exit(main())
