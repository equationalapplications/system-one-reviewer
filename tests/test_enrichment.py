"""Task 6 (AST-units plan): AST enclosing-symbol enrichment on unit states.

r5-m3 mechanism: main() attaches `ast_context` to each unit AFTER pre-judge
expansion, ONLY when provider == "jev" AND --no-enrichment is absent;
`hunk_state` reads the key WHEN PRESENT, so a laya state never carries it.
r2-m4: deletion-only clusters ARE enriched from the PRE-image symbol map;
whole-file-deleted gets none. r2-m3: attachment clamps at 40 symbols /
20 context lines. r12-M1: a unit whose enrichment pushes it over
SOFT_CAP_TOKENS has its context DROPPED at re-expansion step 0 — CONTEXT
DROPPED, NEVER SPLIT. r1-M1: per-unit `enrichment` in judged entries;
run-level stamp is "ast" when ANY unit enriched.

Pipeline order under test (r11-M1): expand → attach ast_context →
re-estimate/re-expand (drop at step 0) → leaves aside → truncate →
freeze → judge.
"""

import json

# ---------- helpers ----------

def _add_file_diff(path, lines):
    """A whole-file-add diff for `path` with the given lines."""
    return (f"diff --git a/{path} b/{path}\n--- /dev/null\n"
            f"+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "\n".join("+" + ln for ln in lines) + "\n")


def _reexpansion_diff():
    """5 files: huge.py's diff is a small touch far BELOW the huge line —
    the oversize mass lives in the file's PRE/POST images (served by the
    injected images fn), NOT in the diff — so the unit is <=cap
    unenriched (hunk_state rides on entries only) and only the
    enrichment context pulls the huge line in and trips the soft cap.
    t0..t3.py stay small and enrichable."""
    diff = _add_file_diff("huge.py", ["def touched():", "    return 1"])
    for i in range(4):
        diff += _add_file_diff(f"t{i}.py", ["def t():", "    return 1"])
    return diff


def _reexpansion_images(repo_, mode_, head_, path_, old_file=None):
    if path_ == "huge.py":
        huge_line = '    x = "' + "a" * 90_000 + '"'
        # pre/post differ ONLY on the touched tail: the huge line is in
        # BOTH images at the same line, so the enriched context window
        # (context-lines +/- the enclosing function head) carries it.
        post = ("def huge():\n"
                f"{huge_line}\n"
                "def filler():\n"
                "    return 0\n\n\n"
                "def touched():\n"
                "    return 1\n")
        pre = post.replace("    return 1", "    return 0")
        return pre, post
    return None, "def t():\n    return 1\n"


def _run_main(jr, monkeypatch, tmp_path, capsys, diff, images,
              provider="jev", extra_args=()):
    """Drive main() offline: fake judge captures the judged units, log_run
    captures the ledger record. Returns (json_out, judged_units, records)."""
    records: list = []
    judged_units: list = []

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged_units.extend(kept)
        return ([{"hunk": h, "severity": 1.0, "is_real": 0.1,
                  "category": "style", "rubric": "code-change",
                  "references_remaining": None,
                  "change_type": h.get("change_type", "code-change"),
                  "latency_ms": 1.0} for h in kept], [1.0] * len(kept),
               {"added_units": 0, "avg_input_tokens": None})

    monkeypatch.setattr(jr, "judge", fake_judge)
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda repo, args: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "mode_file_images", images)
    monkeypatch.setattr(jr, "log_run", lambda rec: records.append(rec))
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    if provider == "laya":
        monkeypatch.setattr(jr, "laya_ask_or_die", lambda model=None: None)
    monkeypatch.setattr(
        jr.sys, "argv",
        ["system-one-reviewer", "--repo", str(tmp_path), "--staged",
         "--provider", provider, "--json", *extra_args])
    jr.main()
    out = json.loads(capsys.readouterr().out)
    return out, judged_units, records


# ---------- r5-m3 mechanism + r2-m4 pre-image enrichment ----------

def test_enrichment_present_for_python(jr):
    """A unit inside a class method gets ast_context with the enclosing
    chain (Class.method) + the file top-level symbol table; when
    enrichment is unavailable the key is ABSENT, never None-valued."""
    post = ("class C:\n"
            "    def method(self):\n"
            "        return 1\n"
            "\n"
            "def top():\n"
            "    return 2\n")
    unit = {"file": "m.py", "line": 3, "hunk_start": 1,
            "entries": [("+", 3, "        return 1", 1)],
            "change_type": "code-change"}
    units = jr.attach_ast_context([unit], lambda path, img: (None, post))
    ctx = units[0]["ast_context"]
    assert ctx["enclosing"] == "C.method"
    assert set(ctx["symbols"]) == {"C", "top"}
    assert ctx["symbols"]["top"] == "def top():"
    assert ctx["context"][0] == "    def method(self):"
    # r20-M1: the context window is the INNERMOST enclosing symbol (the
    # method), not the class header — the old head-first pick showed
    # `class C:` + attributes and never the changed method.
    # r22-m5: ExceptHandler names never enter the chain — `except E as
    # err:` wrapping a nested def gives 'f.helper', not 'f.err.helper'.
    post2 = ("def f():\n"
             "    try:\n"
             "        pass\n"
             "    except ValueError as err:\n"
             "        def helper():\n"
             "            return 1\n"
             "        return helper()\n")
    unit2 = {"file": "m2.py", "line": 6, "hunk_start": 1,
             "entries": [("+", 6, "            return 1", 1)],
             "change_type": "code-change"}
    units2 = jr.attach_ast_context([unit2], lambda p, i: (None, post2))
    assert units2[0]["ast_context"]["enclosing"] == "f.helper"
    # non-Python text: no usable symbol table -> NO key (not None-valued)
    txt = {"file": "r.txt", "line": 1, "hunk_start": 1,
           "entries": [("+", 1, "hello", 1)], "change_type": "code-change"}
    units = jr.attach_ast_context([txt], lambda p, i: (None, "plain text"))
    assert "ast_context" not in units[0]
    # missing images entirely (binary / no text image): NO key
    unit2 = dict(unit, file="gone.py")
    units = jr.attach_ast_context([unit2], lambda p, i: (None, None))
    assert "ast_context" not in units[0]


def test_enrichment_absent_for_wholefile_deletion(jr):
    """whole-file-deleted cluster (no post-image at all) gets NO
    ast_context — even though a parseable pre-image exists."""
    pre = "def gone():\n    return 1\n"
    unit = {"file": "w.py", "line": 1, "hunk_start": 1,
            "entries": [("-", 1, "def gone():", 1, 1)],
            "change_type": "whole-file-deleted"}
    units = jr.attach_ast_context([unit], lambda p, i: (pre, None))
    assert "ast_context" not in units[0]


def test_deletion_only_enriched_from_pre_image(jr):
    """r2-m4: an in-file deletion-only unit HAS a post-image but its
    removed code lives only in the PRE image — its ast_context names the
    old-file symbols whose code was removed."""
    pre = ("def kept_fn():\n    return 1\n\n"
           "def removed_fn():\n    return old\n")
    post = "def kept_fn():\n    return 1\n"
    unit = {"file": "d.py", "line": 5, "hunk_start": 1,
            "entries": [("-", 5, "    return old", 1, 5)],
            "change_type": "deletion-only"}
    units = jr.attach_ast_context([unit], lambda p, i: (pre, post))
    ctx = units[0]["ast_context"]
    assert ctx["enclosing"] == "removed_fn"
    assert "removed_fn" in ctx["symbols"]
    assert ctx["symbols"]["removed_fn"] == "def removed_fn():"


# ---------- r5-m2 flag + r5-m3 laya guard (main-level) ----------

def test_no_enrichment_flag(jr, monkeypatch, tmp_path, capsys):
    """--no-enrichment: main() never attaches ast_context; every judged
    entry logs enrichment: none and the run-level stamp is none (Task 8's
    mandatory enrichment-off arm depends on this)."""
    out, judged_units, records = _run_main(
        jr, monkeypatch, tmp_path, capsys, _reexpansion_diff(),
        _reexpansion_images, extra_args=("--no-enrichment",))
    assert len(judged_units) == 5
    assert all("ast_context" not in u for u in judged_units)
    assert all(e["enrichment"] == "none" for e in records[0]["judged"])
    assert out["meta"]["enrichment"] == "none"


def test_laya_states_never_carry_ast_context(jr, monkeypatch, tmp_path,
                                             capsys):
    """r5-m3 mechanism-level guard: a full laya run — same fixture that
    enriches under jev — produces no unit state carrying ast_context, at
    the unit level OR through hunk_state; every judged entry is none."""
    out, judged_units, records = _run_main(
        jr, monkeypatch, tmp_path, capsys, _reexpansion_diff(),
        _reexpansion_images, provider="laya")
    assert len(judged_units) == 5
    assert all("ast_context" not in u for u in judged_units)
    assert all("ast_context" not in jr.hunk_state(u) for u in judged_units)
    assert all(e["enrichment"] == "none" for e in records[0]["judged"])
    assert out["meta"]["enrichment"] == "none"


# ---------- r1-M1 per-unit flag + run-level stamp ----------

def test_judged_entry_carries_enrichment_flag(jr, monkeypatch, tmp_path,
                                              capsys):
    """A run mixing an enriched (Python) and an unenriched (non-Python)
    unit: judged entries carry per-entry enrichment values that differ
    correctly; the run-level stamp is ast when ANY unit enriched."""
    diff = _add_file_diff("m.py", ["def f():", "    return 1"])
    diff += _add_file_diff("m.js", ["function g() {", "  return 2;", "}"])

    def images(repo_, mode_, head_, path_, old_file=None):
        if path_ == "m.py":
            return None, "def f():\n    return 1\n"
        return None, "function g() {\n  return 2;\n}\n"

    out, judged_units, records = _run_main(jr, monkeypatch, tmp_path,
                                           capsys, diff, images)
    by_file = {e["file"]: e for e in records[0]["judged"]}
    assert by_file["m.py"]["enrichment"] == "ast"
    assert by_file["m.js"]["enrichment"] == "none"
    assert out["meta"]["enrichment"] == "ast"


# ---------- r2-m3 size bounds ----------

def test_enrichment_size_bounded(jr):
    """Symbol table truncated deterministically at 40 symbols (source
    order); unit context <= 20 lines."""
    post = "\n".join(f"def fn_{i:02d}():\n    return {i}"
                     for i in range(60))
    unit = {"file": "big.py", "line": 3, "hunk_start": 1,
            "entries": [("+", 3, "    return 1", 1)],
            "change_type": "code-change"}
    units = jr.attach_ast_context([unit], lambda p, i: (None, post))
    ctx = units[0]["ast_context"]
    assert len(ctx["symbols"]) == 40
    assert list(ctx["symbols"]) == [f"fn_{i:02d}" for i in range(40)]
    assert len(ctx["context"]) <= 20
    # an enclosing function with a 50-line body: context clamps at 20
    body = "\n".join(f"    v{i} = {i}" for i in range(50))
    post2 = f"def big():\n{body}\n"
    unit2 = {"file": "big2.py", "line": 10, "hunk_start": 1,
             "entries": [("+", 10, "    v8 = 8", 1)],
             "change_type": "code-change"}
    units = jr.attach_ast_context([unit2], lambda p, i: (None, post2))
    assert len(units[0]["ast_context"]["context"]) == 20


# ---------- r12-M1 budget interaction: DROP, never split ----------

def test_budget_interaction(jr):
    """Enrichment counts in estimate_call_size (via hunk_state); a state
    whose huge enrichment trips the soft cap has its CONTEXT DROPPED at
    re-expansion step 0 — the images (and so any splitter) are never
    consulted: CONTEXT DROPPED, NOT SPLIT (r12-M1)."""
    base = {"file": "m.py", "line": 1, "hunk_start": 1,
            "entries": [("+", 1, "x = 1", 1)], "change_type": "code-change"}
    enriched = dict(base, ast_context={
        "symbols": {"f": "def f():"}, "enclosing": "f",
        "context": ["y = " + "9" * 90_000]})
    assert (jr.estimate_call_size(jr.hunk_state(enriched),
                                  jr.HUNK_QUESTIONS) > jr.SOFT_CAP_TOKENS)
    assert (jr.estimate_call_size(jr.hunk_state(base),
                                  jr.HUNK_QUESTIONS) < jr.SOFT_CAP_TOKENS)

    def _boom(path, unit):
        raise AssertionError("r12-M1: context drop, never a split")

    out, leaves = jr.expand_oversize_units([enriched], _boom)
    assert len(out) == 1 and leaves == []
    assert "ast_context" not in out[0]
    assert out[0]["entries"] == base["entries"]


def test_enrichment_reexpansion_before_freeze(jr, monkeypatch, tmp_path,
                                              capsys):
    """r12-M1: enrichment pushes 1 of 5 units over cap -> that unit's
    context is DROPPED -> len(kept) unchanged, n_dropped == 0, the unit's
    judged entry says enrichment: none (while the 4 small units stay
    enriched) — and the whole thing happens BEFORE n_units_pre/n_dropped
    freeze (r11-M1 pipeline order)."""
    out, judged_units, records = _run_main(
        jr, monkeypatch, tmp_path, capsys, _reexpansion_diff(),
        _reexpansion_images)
    assert len(judged_units) == 5, "len(kept) unchanged by the drop"
    assert out["n_dropped"] == 0
    assert out["n_unjudged"] == 0
    assert out["meta"]["n_analyzed"] == 5
    huge = next(u for u in judged_units if u["file"] == "huge.py")
    assert "ast_context" not in huge, "over-cap unit's context DROPPED"
    tiny = [u for u in judged_units if u["file"] != "huge.py"]
    assert all("ast_context" in u for u in tiny)
    by_file = {e["file"]: e for e in records[0]["judged"]}
    assert by_file["huge.py"]["enrichment"] == "none"
    assert all(by_file[f"t{i}.py"]["enrichment"] == "ast"
               for i in range(4))
    assert out["meta"]["enrichment"] == "ast"
    assert "(incomplete" not in out["verdict"]
