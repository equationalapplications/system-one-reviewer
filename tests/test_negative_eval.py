"""Task 5: eval_negative counts of negative-fixture findings.

minor-note := sev_level(severity)==1 and category=='style'
"""

import pytest


def _run(jr, sev, cat):
    return {"hunk": {"file": "x.py", "line": 1}, "severity": sev,
            "is_real": 0.9, "category": cat}


def test_blocker_major_and_minor_notes(jr):
    reported = [
        _run(jr, 3.1, "bug-risk"),   # BLOCKER
        _run(jr, 2.4, "security"),   # MAJOR
        _run(jr, 1.2, "style"),      # minor note
        _run(jr, 1.2, "bug-risk"),   # other fp (MINOR but not style)
    ]
    res = jr.eval_negative(reported)
    assert res == {"blocker_major": 2, "minor_notes": 1, "other_fp": 1}


def test_empty_report(jr):
    assert jr.eval_negative([]) == {"blocker_major": 0, "minor_notes": 0,
                                    "other_fp": 0}


def test_none_severity_ignored(jr):
    res = jr.eval_negative([_run(jr, None, "style")])
    assert res == {"blocker_major": 0, "minor_notes": 0, "other_fp": 0}
