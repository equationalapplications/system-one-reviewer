"""Offline tests for the enrichment census and A/B harness helpers."""

import importlib.util
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
                     off_surface=8, golden_lines=(10,), status="ok"):
    """Stand in for the reviewer CLI: write the --out file and append a
    ledger record for the requested label, like the real tool does. Eight
    units at lines 0, 10, ..., 70; the off-arm puts `off_surface` of them at
    0.9 and the rest at 0.1. `tp_out` is the (capped) golden_eval value."""
    import json as _json
    import types

    def fake_run(cmd, env=None, capture_output=None, text=None):
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
