"""Offline tests for the enrichment census and A/B harness helpers."""

import importlib.util
import json
import os
import subprocess

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "scripts")


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _load("enrichment_ab")
census = _load("enrichment_census")


# ---------- A/B: vacuity guard + decision rules ----------

def _res(stamp, wheels=True):
    return {"meta": {"enrichment": stamp,
                     "wheels": {"python": {"available": True},
                                "ts": {"available": wheels}}}}


def test_guard_rejects_an_arm_that_never_engaged():
    assert ab.guard(_res("ts-ast"), "on", "ts-ast") is None
    assert "stamped 'none'" in ab.guard(_res("none"), "on", "ts-ast")
    assert "stamped 'ast'" in ab.guard(_res("ast"), "on", "ts-ast")
    assert ab.guard(_res("ast+ts-ast"), "on", "ts-ast") is None
    # python's cutter is always "available"; only the TS wheels count
    assert "wheels" in ab.guard(_res("ts-ast", wheels=False), "on", "ts-ast")
    assert ab.guard(_res("ast", wheels=False), "on", "ast") is None
    assert ab.guard(_res("none"), "off", "ts-ast") is None
    assert "off-arm" in ab.guard(_res("ts-ast"), "off", "ts-ast")


def test_guard_rejects_a_fail_open_run():
    for arm, stamp in (("on", "ts-ast"), ("off", "none")):
        res = _res(stamp)
        res["meta"].update(fail_open=True, status="fail-open",
                           fail_reason="HTTP 503")
        assert "failed open" in ab.guard(res, arm, "ts-ast")
    res = _res("ts-ast")
    res["meta"]["status"] = "fail-open"
    assert "failed open" in ab.guard(res, "on", "ts-ast")


def test_sign_test():
    assert ab.sign_test_p([]) == 1.0
    assert ab.sign_test_p([0, 0]) == 1.0
    assert ab.sign_test_p([-0.1] * 8) < 0.05
    assert ab.sign_test_p([0.1, -0.1, 0.1, -0.1]) == 1.0


def _row(on_rep, off_rep, on_tp, off_tp, deltas=None):
    return {"on_reported": on_rep, "off_reported": off_rep,
            "on_tp": on_tp, "off_tp": off_tp, "deltas": dict(deltas or {})}


def _units(value, n=8):
    return {f"a.ts:{i}:{i + 2}": value for i in range(n)}


def test_decide():
    flat = _units(0.0, 4)
    # recall signal in every repeat, precision held
    rows = [_row(1, 1, 5, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "SIGNAL"
    # a single repeat short of +2 is not signal
    rows = [_row(1, 1, 5, 3, flat), _row(1, 1, 4, 3, flat)]
    assert ab.decide(rows)["verdict"] == "NO-DETECTABLE-EFFECT"
    # clean sample: any extra surfaced finding is a new false positive
    rows = [_row(2, 1, 0, 0, flat)] * 3
    assert ab.decide(rows, clean=True)["verdict"] == "KILL"
    # golden sample: extra TRUE positives are the point, not a kill
    rows = [_row(5, 3, 5, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "SIGNAL"
    # ...but extra false positives (reported - tp) still are
    rows = [_row(6, 3, 4, 3, flat)] * 3
    assert ab.decide(rows)["verdict"] == "KILL"
    assert ab.decide([])["verdict"] == "NO-DETECTABLE-EFFECT"
    # systematic softening kills even when precision and recall pass
    rows = [_row(1, 1, 5, 3, _units(-0.1))] * 2
    d = ab.decide(rows)
    assert d["verdict"] == "KILL" and not d["softening_test_underpowered"]
    # too few non-zero pairs to ever reach p < 0.05: say so, do not kill
    rows = [_row(1, 1, 5, 3, _units(-0.1, 4))] * 2
    d = ab.decide(rows)
    assert d["verdict"] == "SIGNAL" and d["softening_test_underpowered"]
    # repeats of one unit are averaged, not counted as independent pairs
    rows = [_row(1, 1, 5, 3, _units(-0.1, 3))] * 5
    assert ab.decide(rows)["n_paired_units"] == 3


def test_paired_deltas_pair_by_unit():
    on = [{"file": "a.ts", "line": 1, "line_end": 3, "is_real": 0.5},
          {"file": "b.ts", "line": 1, "line_end": 3, "is_real": 0.9}]
    off = [{"file": "a.ts", "line": 1, "line_end": 3, "is_real": 0.7}]
    got = ab.paired_is_real_deltas(on, off)
    assert list(got) == ["a.ts:1:3"] and got["a.ts:1:3"] == pytest.approx(-0.2)


def test_guard_files_aborts_only_when_no_unit_is_enriched():
    # (modified: previously required EVERY golden unit enriched; the over-cap
    # context drop legitimately leaves some units "none")
    judged = [{"file": "g.ts", "enrichment": "ts-ast"},
              {"file": "g.ts", "enrichment": "ts-ast"},
              {"file": "other.ts", "enrichment": "none"}]
    assert ab.guard_files(judged, {"g.ts"}, "ts-ast") is None
    judged[1]["enrichment"] = "none"  # partial: no abort, share reported
    assert ab.guard_files(judged, {"g.ts"}, "ts-ast") is None
    assert ab.golden_file_shares(judged, {"g.ts"}, "ts-ast") == {"g.ts": 0.5}
    judged[0]["enrichment"] = "none"  # none enriched: abort
    assert "parse error" in ab.guard_files(judged, {"g.ts"}, "ts-ast")
    assert "not judged" in ab.guard_files(judged, {"missing.ts"}, "ts-ast")
    assert ab.golden_file_shares(judged, {"missing.ts"}, "ts-ast") == {
        "missing.ts": 0.0}


def test_combine_verdicts():
    g = lambda v: {"verdict": v, "golden": True}  # noqa: E731
    c = lambda v: {"verdict": v, "golden": False}  # noqa: E731
    assert ab.combine_verdicts([g("SIGNAL"), g("SIGNAL"), c("NO-DETECTABLE-EFFECT")]) == "SIGNAL"
    assert ab.combine_verdicts([g("SIGNAL"), g("NO-DETECTABLE-EFFECT")]) == "NO-DETECTABLE-EFFECT"
    assert ab.combine_verdicts([g("SIGNAL"), c("KILL")]) == "KILL"
    assert ab.combine_verdicts([g("KILL"), g("SIGNAL")]) == "KILL"
    assert ab.combine_verdicts([c("NO-DETECTABLE-EFFECT")]) == "NO-DETECTABLE-EFFECT"
    assert ab.combine_verdicts([]) == "NO-DETECTABLE-EFFECT"


def test_combine_cli(tmp_path, capsys):
    import json as _json
    paths = []
    for i, v in enumerate(("SIGNAL", "KILL")):
        p = tmp_path / f"{i}.json"
        p.write_text(_json.dumps({"sample": f"s{i}", "verdict": v, "golden": True}))
        paths.append(str(p))
    assert ab.main(["--combine", *paths]) == 0
    assert _json.loads(capsys.readouterr().out)["combined_verdict"] == "KILL"


def _fake_subprocess(monkeypatch, tmp_path, *, on_is_real, stamp_on="ts-ast",
                     n_findings=0, tp_out=0, severity=2, rubric="code-change",
                     off_surface=8, golden_lines=(10,), status="ok",
                     reflex_class=None, cmds=None):
    """Stand in for the reviewer CLI: write the --out file and append a
    ledger record for the requested label, like the real tool does. Eight
    units at lines 0, 10, ..., 70; the off-arm puts `off_surface` of them at
    0.9 and the rest at 0.1. `tp_out` is the (capped) golden_eval value."""
    import json as _json
    import types

    def fake_run(cmd, env=None, capture_output=None, text=None):
        if cmds is not None:
            cmds.append(list(cmd))
        label = cmd[cmd.index("--label") + 1]
        out = cmd[cmd.index("--out") + 1]
        arm = "off" if "--no-enrichment" in cmd else "on"
        enr = "none" if arm == "off" else stamp_on
        res = {"meta": {"enrichment": enr, "status": status, "fail_open": False,
                        "wheels": {"ts": {"available": True}}},
               "findings": [{}] * n_findings, "golden_eval": {"true_positives": tp_out}}
        with open(out, "w") as f:
            _json.dump(res, f)
        judged = [{"file": "g.ts", "line": i * 10, "line_end": i * 10 + 2,
                   "enrichment": enr, "severity": severity, "rubric": rubric,
                   "is_real": on_is_real if arm == "on"
                   else (0.9 if i < off_surface else 0.1)}
                  for i in range(8)]
        if reflex_class is not None:
            for j in judged:
                j["reflex_class"] = reflex_class
        with open(env["JEV_REVIEW_METRICS"], "a") as f:
            f.write(_json.dumps({"label": label, "judged": judged}) + "\n")
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(ab.subprocess, "run", fake_run)
    golden = tmp_path / "g.tsv"
    golden.write_text("".join(f"g.ts\t{n}\tdesc\n" for n in golden_lines))
    return str(golden)


def test_main_wires_labels_so_the_softening_kill_can_fire(
        monkeypatch, tmp_path, capsys):
    import json as _json
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.5)
    rc = ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                  "--expect", "ts-ast", "--golden", golden, "--repeats", "2",
                  "--outdir", str(tmp_path / "o")])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["n_paired_units"] == 8 and out["verdict"] == "KILL"
    assert out["mean_is_real_delta"] == pytest.approx(-0.4)


def test_main_counts_reported_from_the_ledger_not_the_capped_findings(
        monkeypatch, tmp_path, capsys):
    import json as _json
    # --out findings are capped at 5; the ledger has 8 units above the gate
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.85,
                              n_findings=5)
    rc = ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                  "--expect", "ts-ast", "--golden", golden, "--repeats", "1",
                  "--outdir", str(tmp_path / "o")])
    out = _json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["repeats"][0]["on_reported"] == 8
    assert out["repeats"][0]["off_reported"] == 8
    assert out["golden_file_enriched_share"] == {"g.ts": 1.0}
    assert out["golden"] is True
    # below the gate nothing is reported
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.79,
                              n_findings=5)
    ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "t",
             "--expect", "ts-ast", "--golden", golden, "--repeats", "1",
             "--outdir", str(tmp_path / "o2")])
    assert _json.loads(capsys.readouterr().out)["repeats"][0]["on_reported"] == 0


def test_main_reports_partial_enrichment_without_aborting(
        monkeypatch, tmp_path, capsys):
    import json as _json
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    real_run = ab.subprocess.run

    def half_stamped(cmd, **kw):
        r = real_run(cmd, **kw)
        if "--no-enrichment" not in cmd:
            p = kw["env"]["JEV_REVIEW_METRICS"]
            lines = open(p).read().splitlines()
            rec = _json.loads(lines[-1])
            for j in rec["judged"][:2]:
                j["enrichment"] = "none"
            lines[-1] = _json.dumps(rec)
            open(p, "w").write("\n".join(lines) + "\n")
        return r

    monkeypatch.setattr(ab.subprocess, "run", half_stamped)
    rc = ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                  "--expect", "ts-ast", "--golden", golden, "--repeats", "1",
                  "--outdir", str(tmp_path / "o")])
    assert rc == 0
    assert _json.loads(capsys.readouterr().out)[
        "golden_file_enriched_share"] == {"g.ts": 0.75}


def test_main_aborts_when_a_golden_file_never_enriched(
        monkeypatch, tmp_path, capsys):
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)

    real_run = ab.subprocess.run

    def broken_unit_stamp(cmd, **kw):
        r = real_run(cmd, **kw)
        # corrupt the on-arm ledger record: file unenriched, run still ts-ast
        if "--no-enrichment" not in cmd:
            p = kw["env"]["JEV_REVIEW_METRICS"]
            lines = open(p).read().splitlines()
            import json as _json
            rec = _json.loads(lines[-1])
            for j in rec["judged"]:  # (modified: ALL units, not just one)
                j["enrichment"] = "none"
            lines[-1] = _json.dumps(rec)
            open(p, "w").write("\n".join(lines) + "\n")
        return r

    monkeypatch.setattr(ab.subprocess, "run", broken_unit_stamp)
    rc = ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                  "--expect", "ts-ast", "--golden", golden, "--repeats", "1",
                  "--outdir", str(tmp_path / "o")])
    assert rc == 2
    assert "parse error" in capsys.readouterr().err


def test_main_refuses_a_run_with_neither_golden_nor_clean(tmp_path):
    with pytest.raises(SystemExit):
        ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                 "--expect", "ts-ast", "--outdir", str(tmp_path / "o")])


def _run_main(tmp_path, golden, *extra, sample="s", flag="--golden"):
    return ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", sample,
                    "--expect", "ts-ast", flag, golden, "--repeats", "1",
                    "--outdir", str(tmp_path / f"o-{sample}"), *extra])


def test_main_scores_true_positives_uncapped_from_the_ledger(
        monkeypatch, tmp_path, capsys):
    import json as _json
    # the tool caps findings and golden_eval at 5; the ledger holds 8 real hits
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9,
                              n_findings=5, tp_out=5, off_surface=5,
                              golden_lines=tuple(range(0, 80, 10)))
    assert _run_main(tmp_path, golden) == 0
    out = _json.loads(capsys.readouterr().out)
    row = out["repeats"][0]
    assert (row["on_reported"], row["on_tp"]) == (8, 8)
    assert (row["off_reported"], row["off_tp"]) == (5, 5)
    assert out["verdict"] == "SIGNAL" and out["precision_ok"]


def _on_reported(monkeypatch, tmp_path, capsys, sample, **kw):
    import json as _json
    golden = _fake_subprocess(monkeypatch, tmp_path, **kw)
    assert _run_main(tmp_path, golden, sample=sample) == 0
    return _json.loads(capsys.readouterr().out)["repeats"][0]["on_reported"]


def test_main_does_not_count_a_severity_zero_unit(monkeypatch, tmp_path, capsys):
    assert _on_reported(monkeypatch, tmp_path, capsys, "a",
                        on_is_real=0.9, severity=0) == 0
    assert _on_reported(monkeypatch, tmp_path, capsys, "b",
                        on_is_real=0.9, severity=1) == 8


def test_main_uses_the_deletion_threshold_for_deletion_units(
        monkeypatch, tmp_path, capsys):
    kw = {"rubric": "deletion"}
    assert _on_reported(monkeypatch, tmp_path, capsys, "a",
                        on_is_real=0.75, **kw) == 8
    assert _on_reported(monkeypatch, tmp_path, capsys, "b",
                        on_is_real=0.65, **kw) == 0
    assert _on_reported(monkeypatch, tmp_path, capsys, "c",
                        on_is_real=0.75) == 0


def test_main_gate_is_inclusive(monkeypatch, tmp_path, capsys):
    assert _on_reported(monkeypatch, tmp_path, capsys, "a", on_is_real=0.80) == 8
    assert _on_reported(monkeypatch, tmp_path, capsys, "b",
                        on_is_real=0.7999) == 0


def test_main_aborts_on_a_non_ok_status(monkeypatch, tmp_path, capsys):
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9,
                              status="incomplete review")
    assert _run_main(tmp_path, golden) == 2
    err = capsys.readouterr().err
    assert "on-arm" in err and "incomplete review" in err


def test_guard_rejects_a_non_ok_status_on_either_arm():
    for arm, stamp in (("on", "ts-ast"), ("off", "none")):
        res = _res(stamp)
        res["meta"]["status"] = "incomplete review"
        msg = ab.guard(res, arm, "ts-ast")
        assert msg and f"{arm}-arm" in msg and "incomplete review" in msg
    assert ab.guard(_res("ts-ast"), "on", "ts-ast") is None


def _unstamp_on_arm(monkeypatch):
    import json as _json
    real_run = ab.subprocess.run

    def run(cmd, **kw):
        r = real_run(cmd, **kw)
        if "--no-enrichment" not in cmd:
            p = kw["env"]["JEV_REVIEW_METRICS"]
            lines = open(p).read().splitlines()
            rec = _json.loads(lines[-1])
            for j in rec["judged"]:
                j["enrichment"] = "none"
            lines[-1] = _json.dumps(rec)
            open(p, "w").write("\n".join(lines) + "\n")
        return r

    monkeypatch.setattr(ab.subprocess, "run", run)


def test_main_guards_files_of_a_negative_golden_sample(
        monkeypatch, tmp_path, capsys):
    import json as _json
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    assert _run_main(tmp_path, golden, flag="--negative-golden") == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["golden"] is False
    assert out["golden_file_enriched_share"] == {"g.ts": 1.0}
    assert out["repeats"][0]["on_tp"] == 0 and out["repeats"][0]["on_reported"] == 8
    _unstamp_on_arm(monkeypatch)
    assert _run_main(tmp_path, golden, flag="--negative-golden", sample="t") == 2
    assert "parse error" in capsys.readouterr().err


# ---------- census ----------

def test_census_on_a_throwaway_repo(tmp_path):
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    repo = tmp_path / "r"
    repo.mkdir()
    long_body = "".join(f"  const v{i} = {i};\n" for i in range(40))
    (repo / "a.ts").write_text(
        "export function short() {\n  return 1;\n}\n"
        f"export function long() {{\n{long_body}  return 2;\n}}\n")
    (repo / "b.py").write_text("def f():\n    return 1\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    tool = census.load_tool()
    recs = census.census(tool, str(repo), "HEAD",
                         [("a.ts", 2), ("a.ts", 40), ("b.py", 2), ("gone.ts", 1)])
    by = {(r["file"], r["line"]): r for r in recs}
    assert by[("a.ts", 2)]["covered"] and by[("a.ts", 2)]["enclosing"] == "short"
    # position, not text: a repeated line outside the window is not covered
    assert by[("a.ts", 2)]["window"] == 3
    # a line deep in a long function is outside the 20-line head-first window
    assert by[("a.ts", 40)]["enriched"] and not by[("a.ts", 40)]["covered"]
    assert by[("b.py", 2)]["covered"]
    assert not by[("gone.ts", 1)]["enriched"]
    summ = census.summarize(recs)
    assert summ["rows"] == 4 and summ["enriched"] == 3 and summ["covered"] == 2
    assert summ["missing"] == 1 and by[("gone.ts", 1)]["missing"]


# ---------- golden rows must be judged; --clean conflicts with --golden ----------

def test_guard_rows_requires_every_golden_row_to_be_covered():
    # (modified: rows are matched against the unit ANCHOR `line` +-1, as
    # eval_against_golden does, not against the line_start..line_end span)
    judged = [{"file": "g.ts", "line": 10, "line_end": 12},
              {"file": "g.ts", "line": 40, "line_start": 38, "line_end": 44},
              {"file": "other.ts", "line": 90, "line_end": 95}]
    assert ab.guard_rows(judged, [("g.ts", 11), ("g.ts", 9), ("g.ts", 10)]) is None
    assert ab.guard_rows(judged, [("g.ts", 41), ("g.ts", 39)]) is None
    # inside the span but beyond the anchor slack: the scorer cannot match it
    assert "g.ts:13" in ab.guard_rows(judged, [("g.ts", 13)])
    assert "g.ts:42" in ab.guard_rows(judged, [("g.ts", 42)])
    assert "g.ts:37" in ab.guard_rows(judged, [("g.ts", 37)])
    # same file, no unit near the row: the file-level guard would pass this
    assert "g.ts:25" in ab.guard_rows(judged, [("g.ts", 11), ("g.ts", 25)])
    # right line, wrong file
    assert "g.ts:90" in ab.guard_rows(judged, [("g.ts", 90)])


def test_guard_rows_row_inside_a_wide_span_is_not_reachable():
    judged = [{"file": "g.ts", "line": 1, "line_start": 1, "line_end": 100}]
    msg = ab.guard_rows(judged, [("g.ts", 57)])
    assert msg and "g.ts:57" in msg and "anchor" in msg
    assert ab.guard_rows(judged, [("g.ts", 2)]) is None
    assert ab.guard_rows(judged, [("g.ts", 0)]) is None
    assert ab.guard_rows(judged, [("g.ts", 3)]) is not None


def test_main_aborts_when_a_golden_row_was_never_judged(
        monkeypatch, tmp_path, capsys):
    # units sit at lines 0..70 step 10; a golden row at 25 falls in no unit
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9,
                              golden_lines=(10, 25))
    assert _run_main(tmp_path, golden) == 2
    assert "golden row g.ts:25" in capsys.readouterr().err


def test_main_aborts_when_the_off_arm_never_judged_a_golden_row(
        monkeypatch, tmp_path, capsys):
    """Both arms must have judged every golden row, or the comparison scores
    a never-shown defect as missed."""
    import json as _json
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    real_run = ab.subprocess.run

    def drop_off_arm_units(cmd, **kw):
        r = real_run(cmd, **kw)
        if "--no-enrichment" in cmd:
            p = kw["env"]["JEV_REVIEW_METRICS"]
            lines = open(p).read().splitlines()
            rec = _json.loads(lines[-1])
            rec["judged"] = [j for j in rec["judged"] if j["line"] != 10]
            lines[-1] = _json.dumps(rec)
            open(p, "w").write("\n".join(lines) + "\n")
        return r

    monkeypatch.setattr(ab.subprocess, "run", drop_off_arm_units)
    assert _run_main(tmp_path, golden) == 2
    err = capsys.readouterr().err
    assert "off-arm" in err and "golden row g.ts:10" in err


def test_main_rejects_clean_together_with_golden(monkeypatch, tmp_path):
    def must_not_run(*a, **k):
        raise AssertionError("argument validation must fail before any run")

    monkeypatch.setattr(ab.subprocess, "run", must_not_run)
    g = tmp_path / "g.tsv"
    g.write_text("g.ts\t1\tdesc\n")
    with pytest.raises(SystemExit):
        ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                 "--expect", "ts-ast", "--golden", str(g), "--clean",
                 "--outdir", str(tmp_path / "o")])


# ---------- golden file readers ----------

REAL_NEGATIVE = os.path.join(os.path.dirname(SCRIPTS), "examples", "negative-golden.tsv")


def test_real_negative_golden_file_parses():
    assert ab.negative_golden_files(REAL_NEGATIVE, "ts-ast") == set()
    got = ab.negative_golden_files(REAL_NEGATIVE, "ast")
    assert got == {"src/app.py"}  # README.md is not code, format_extra.py is GONE


def test_negative_reader_filters_gone_and_extensions(tmp_path):
    p = tmp_path / "n.tsv"
    p.write_text("# c\n  # indented comment\n\nsrc/a.ts\tfoo\nsrc/b.tsx\tGONE\n"
                 "src/c.mjs\tbar\nREADME.md\tx\nsrc/d.py\tGONE\nsrc/e.py\ty\n")
    assert ab.negative_golden_files(str(p), "ts-ast") == {"src/a.ts", "src/c.mjs"}
    assert ab.negative_golden_files(str(p), "ast") == {"src/e.py"}


def test_golden_rows_skip_indented_comments_and_blank_lines(tmp_path):
    p = tmp_path / "g.tsv"
    p.write_text("  # indented comment\n\n\t\ng.ts\t10\tdesc\n  g.ts\t20  \n")
    assert ab.golden_rows(str(p)) == [("g.ts", 10), ("g.ts", 20)]


@pytest.mark.parametrize("body", ["g.ts\n", "g.ts\tabc\tdesc\n", "README.md\t## Usage\n"])
def test_golden_rows_malformed_line_names_file_and_line(tmp_path, body):
    p = tmp_path / "g.tsv"
    p.write_text("g.ts\t1\n" + body)
    with pytest.raises(SystemExit) as e:
        ab.golden_rows(str(p))
    assert f"{p}:2" in str(e.value)


def _args(**kw):
    import types
    base = dict(golden=None, negative_golden=None, must_enrich=None, expect="ts-ast")
    return types.SimpleNamespace(**{**base, **kw})


def test_guard_file_set_is_the_union_of_golden_negative_and_must_enrich(tmp_path):
    g = tmp_path / "g.tsv"
    g.write_text("a.ts\t3\tdesc\nREADME.md\t4\tdesc\n")
    n = tmp_path / "n.tsv"
    n.write_text("b.ts\tfoo\nc.ts\tGONE\nd.md\tx\n")
    assert ab.guard_file_set(_args(golden=str(g), negative_golden=str(n))) == {
        "a.ts", "README.md", "b.ts"}
    assert ab.guard_file_set(_args(negative_golden=str(n), must_enrich=["z.ts"])) == {
        "b.ts", "z.ts"}
    assert ab.guard_file_set(_args()) == set()


def test_main_negative_golden_in_the_real_format_does_not_crash(
        monkeypatch, tmp_path, capsys):
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    neg = tmp_path / "n.tsv"
    neg.write_text("# c\ng.ts\tsome substring\nREADME.md\t## Usage\nold.ts\tGONE\n")
    assert ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                    "--expect", "ts-ast", "--negative-golden", str(neg),
                    "--repeats", "1", "--outdir", str(tmp_path / "o")]) == 0
    assert golden  # fixture side effect only
    assert json.loads(capsys.readouterr().out)["golden_file_enriched_share"] == {
        "g.ts": 1.0}


def test_main_golden_with_negative_golden_guards_both(
        monkeypatch, tmp_path, capsys):
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    neg = tmp_path / "n.tsv"
    neg.write_text("never_judged.ts\tsubstring\n")
    assert ab.main(["--repo", str(tmp_path), "--range", "a..b", "--sample", "s",
                    "--expect", "ts-ast", "--golden", golden,
                    "--negative-golden", str(neg), "--repeats", "1",
                    "--outdir", str(tmp_path / "o")]) == 2
    assert "never_judged.ts was not judged" in capsys.readouterr().err


def test_main_must_enrich_guards_a_clean_run(monkeypatch, tmp_path, capsys):
    _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9)
    base = ["--repo", str(tmp_path), "--range", "a..b", "--expect", "ts-ast",
            "--clean", "--repeats", "1"]
    assert ab.main([*base, "--sample", "s", "--outdir", str(tmp_path / "o1"),
                    "--must-enrich", "g.ts"]) == 0
    capsys.readouterr()
    assert ab.main([*base, "--sample", "t", "--outdir", str(tmp_path / "o2"),
                    "--must-enrich", "g.ts", "absent.ts"]) == 2
    assert "absent.ts" in capsys.readouterr().err
    _unstamp_on_arm(monkeypatch)
    assert ab.main([*base, "--sample", "u", "--outdir", str(tmp_path / "o3"),
                    "--must-enrich", "g.ts"]) == 2
    assert "parse error" in capsys.readouterr().err


# ---------- pooled precision rule ----------

def test_precision_a_single_repeat_spike_is_noise_not_a_kill():
    rows = [_row(2, 1, 0, 0), _row(1, 2, 0, 0), _row(1, 1, 0, 0)]
    d = ab.decide(rows, clean=True)
    assert d["precision_ok"] and d["verdict"] != "KILL"


def test_precision_consistent_excess_is_a_kill():
    d = ab.decide([_row(2, 1, 0, 0)] * 3, clean=True)
    assert not d["precision_ok"] and d["verdict"] == "KILL"


def test_precision_exactly_at_the_margin_is_not_a_kill():
    assert ab.MARGIN == 1
    rows = [_row(2, 1, 0, 0), _row(1, 1, 0, 0), _row(1, 1, 0, 0)]
    assert ab.decide(rows, clean=True)["precision_ok"]
    rows = [_row(2, 1, 0, 0), _row(2, 1, 0, 0), _row(1, 1, 0, 0)]
    assert not ab.decide(rows, clean=True)["precision_ok"]


def test_precision_pooling_uses_golden_false_positives_not_reported():
    # on surfaces 3 more but they are all true positives: no excess FPs
    rows = [_row(4, 1, 4, 1)] * 3
    assert ab.decide(rows)["precision_ok"]


# ---------- softening rule ----------

def _delta_rows(values, repeats=1):
    return [_row(1, 1, 0, 0, {f"u.ts:{i}:{i}": v for i, v in enumerate(values)})
            for _ in range(repeats)]


def test_softening_needs_more_worse_units_than_better_ones():
    values = [0.05] * 30 + [-0.9] * 3
    d = ab.decide(_delta_rows(values))
    assert d["mean_is_real_delta"] < 0 and d["sign_test_p"] < 0.05
    assert d["verdict"] != "KILL"


def test_softening_many_small_losses_few_gains_is_a_kill():
    d = ab.decide(_delta_rows([-0.05] * 10 + [0.01] * 2))
    assert d["sign_test_p"] < 0.05 and d["verdict"] == "KILL"


def test_softening_float_noise_pairs_are_ties():
    noise = 0.1 + 0.2 - 0.3
    assert noise != 0
    d = ab.decide(_delta_rows([noise] * 8))
    assert d["softening_test_underpowered"] and d["sign_test_p"] == 1.0
    # noise that survives averaging across repeats is also a tie
    rows = [_row(1, 1, 0, 0, {f"u{i}": v for i in range(8)}) for v in (0.1, 0.2, -0.3)]
    d = ab.decide(rows)
    assert d["softening_test_underpowered"] and d["mean_is_real_delta"] == 0


def test_softening_underpowered_boundary():
    assert ab.decide(_delta_rows([-0.1] * 5 + [0.0] * 3))[
        "softening_test_underpowered"] is True
    assert ab.decide(_delta_rows([-0.1] * 6 + [0.0] * 3))[
        "softening_test_underpowered"] is False
    # at exactly 6 all-negative pairs p = 2/64 < 0.05: the kill fires
    assert ab.decide(_delta_rows([-0.1] * 6))["verdict"] == "KILL"


# ---------- harness details ----------

def test_guard_splits_the_stamp_on_plus():
    assert "expected 'ast'" in ab.guard(_res("ts-ast"), "on", "ast")
    assert ab.guard(_res("ast+ts-ast"), "on", "ast") is None


def test_run_one_never_returns_a_stale_out_file(monkeypatch, tmp_path):
    import types
    outdir = tmp_path / "o"
    outdir.mkdir()
    stale = outdir / "on-s-r1.json"
    stale.write_text(json.dumps({"meta": {"enrichment": "ts-ast"}}))
    monkeypatch.setattr(ab.subprocess, "run", lambda *a, **k: types.SimpleNamespace(
        returncode=1, stderr="boom"))
    args = types.SimpleNamespace(sample="s", outdir=str(outdir), repo=".",
                                 range="a..b", golden=None, negative_golden=None,
                                 include_test_findings=False)
    with pytest.raises(SystemExit, match="produced no --out"):
        ab.run_one(args, "on", 1)
    assert not stale.exists()


def test_combine_expect_samples_refuses_signal_when_a_sample_is_missing():
    g = lambda n, v: {"sample": n, "verdict": v, "golden": True}  # noqa: E731
    both = [g("a", "SIGNAL"), g("b", "SIGNAL")]
    assert ab.combine_verdicts(both, ["a", "b"]) == "SIGNAL"
    assert ab.combine_verdicts(both[:1], ["a", "b"]) == "NO-DETECTABLE-EFFECT"
    assert ab.combine_verdicts(both[:1]) == "SIGNAL"
    assert ab.combine_verdicts([g("a", "KILL")], ["a", "b"]) == "KILL"
    assert ab.missing_samples(both[:1], ["a", "b"]) == ["b"]


def test_combine_cli_expect_samples(tmp_path, capsys):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"sample": "a", "verdict": "SIGNAL", "golden": True}))
    assert ab.main(["--combine", str(p), "--expect-samples", "a", "b"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["combined_verdict"] == "NO-DETECTABLE-EFFECT" and out["missing"] == ["b"]
    assert ab.main(["--combine", str(p), "--expect-samples", "a"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["combined_verdict"] == "SIGNAL" and out["missing"] == []


# ---------- test-file class: held by default, --include-test-findings ----------

def _entry(cls=None, real=0.9):
    j = {"file": "g.ts", "line": 10, "severity": 2, "rubric": "code-change",
         "is_real": real}
    if cls is not None:
        j["reflex_class"] = cls
    return j


def test_surfaced_holds_test_entries_unless_included():
    assert ab.surfaced([_entry("test")]) == []
    assert len(ab.surfaced([_entry("test")], include_test=True)) == 1
    # code, and old-style entries with no key, surface either way
    assert len(ab.surfaced([_entry("code")])) == 1
    assert len(ab.surfaced([_entry()])) == 1
    assert len(ab.surfaced([_entry()], include_test=True)) == 1


def test_main_forwards_include_test_findings_to_both_arms(
        monkeypatch, tmp_path, capsys):
    import json as _json
    cmds: list = []
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9,
                              reflex_class="test", cmds=cmds)
    assert _run_main(tmp_path, golden, "--include-test-findings") == 0
    assert len(cmds) == 2
    assert all("--include-test-findings" in c for c in cmds)
    row = _json.loads(capsys.readouterr().out)["repeats"][0]
    assert (row["on_reported"], row["off_reported"]) == (8, 8)


def test_main_without_the_flag_holds_test_entries_and_omits_it(
        monkeypatch, tmp_path, capsys):
    import json as _json
    cmds: list = []
    golden = _fake_subprocess(monkeypatch, tmp_path, on_is_real=0.9,
                              reflex_class="test", cmds=cmds)
    assert _run_main(tmp_path, golden) == 0
    assert len(cmds) == 2
    assert not any("--include-test-findings" in c for c in cmds)
    row = _json.loads(capsys.readouterr().out)["repeats"][0]
    assert (row["on_reported"], row["off_reported"]) == (0, 0)
