"""Task 6: compose takes threshold as a parameter (gate AND jitter near()),
keeping the plateau rule semantics for whatever value is passed.
"""



def _f(is_real, severity, parse_error=None):
    return {"hunk": {"file": "a.py", "line": 1}, "is_real": is_real,
            "severity": severity, "category": "bug-risk",
            "parse_error": parse_error}


def test_gate_uses_parameter(jr):
    findings = [_f(0.65, 2.0)]
    reported, jitter, _ = jr.compose(findings, [], None, threshold=0.60)
    assert len(reported) == 1
    reported, jitter, _ = jr.compose(findings, [], None, threshold=0.70)
    assert reported == []


def test_default_threshold_is_real_threshold(jr):
    findings = [_f(jr.REAL_THRESHOLD, 2.0)]
    reported, jitter, _ = jr.compose(findings, [], None)
    assert len(reported) == 1
    assert jitter  # at-threshold score sits in the jitter zone


def test_jitter_near_uses_parameter(jr):
    findings = [_f(0.63, 2.0)]
    _, jitter, _ = jr.compose(findings, [], None, threshold=0.65)
    assert jitter


def test_verdict_major_rule(jr):
    findings = [_f(0.9, 2.2), _f(0.9, 2.4)]
    _, _, verdict = jr.compose(findings, [], None)
    assert verdict == "Changes requested"
    _, _, verdict = jr.compose(findings[:1], [], None)
    assert verdict == "Approved"
