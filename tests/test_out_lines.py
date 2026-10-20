"""--out JSON findings carry `lines`: the judged unit's rendered lines.

main() builds each `--out` finding from the reported unit, including
`lines` (the unit's rendered lines, so a receipt is self-contained for
REAL/FP adjudication). Offline driver: a fake judge returns one finding at
a chosen is_real; compose() reports it only at or above the 0.80 gate.
"""

import json

from test_enrichment import _add_file_diff


def _run_out(jr, monkeypatch, tmp_path, capsys, is_real, records=None):
    """Drive main() with --out; returns (out_json, judged_units). `records`
    collects what main() hands to log_run."""
    diff = _add_file_diff("m.py", ["def f():", "    return 1"])
    judged_units: list = []
    out_path = tmp_path / "out.json"

    def fake_judge(kept, ask, errors=None, split_unit=None):
        judged_units.extend(kept)
        return ([{"hunk": h, "severity": 3.0, "is_real": is_real,
                  "category": "bug", "rubric": "code-change",
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
    monkeypatch.setattr(jr, "mode_file_images",
                        lambda repo_, mode_, head_, path_, old_file=None:
                        (None, "def f():\n    return 1\n"))
    monkeypatch.setattr(jr, "log_run",
                        lambda rec: records.append(rec) if records is not None else None)
    monkeypatch.setattr(jr, "make_provider",
                        lambda *a, **k: lambda s, q: ({"answers": {}}, 1.0))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(
        jr.sys, "argv",
        ["system-one-reviewer", "--repo", str(tmp_path), "--staged",
         "--provider", "jev", "--json", "--out", str(out_path)])
    jr.main()
    stdout = capsys.readouterr().out
    with open(out_path) as f:
        out = json.load(f)
    if records is not None:
        records.append({"stdout": json.loads(stdout)})
    return out, judged_units


def test_out_findings_carry_judged_unit_lines(jr, monkeypatch, tmp_path,
                                              capsys):
    """A reported finding in --out has `lines` equal to the judged unit's
    rendered lines, as a list of strings."""
    out, judged_units = _run_out(jr, monkeypatch, tmp_path, capsys,
                                 is_real=0.95)
    assert len(judged_units) == 1
    assert out["findings"]
    finding = out["findings"][0]
    assert "lines" in finding
    assert isinstance(finding["lines"], list)
    assert all(isinstance(ln, str) for ln in finding["lines"])
    assert finding["lines"] == judged_units[0]["lines"]
    assert finding["lines"]


def test_out_findings_empty_below_gate(jr, monkeypatch, tmp_path, capsys):
    """A finding below the 0.80 gate is not reported, so --out findings
    is an empty list."""
    out, judged_units = _run_out(jr, monkeypatch, tmp_path, capsys,
                                 is_real=0.10)
    assert len(judged_units) == 1
    assert out["findings"] == []


def test_ledger_record_carries_no_finding_lines(jr, monkeypatch, tmp_path,
                                                capsys):
    """`lines` is source text: --out and the --json stdout keep it, the
    append-only ledger never gets it (AGENTS.md: finding TEXT is not
    persisted unless --out)."""
    records: list = []
    out, _ = _run_out(jr, monkeypatch, tmp_path, capsys, is_real=0.95,
                      records=records)
    stdout = records.pop()["stdout"]
    assert len(records) == 1
    assert records[0]["findings"]
    assert all("lines" not in f for f in records[0]["findings"])
    # the other finding fields still reach the ledger
    assert records[0]["findings"][0]["file"] == out["findings"][0]["file"]
    assert out["findings"][0]["lines"]
    assert stdout["findings"][0]["lines"] == out["findings"][0]["lines"]
