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


def test_compose_returns_no_verdict(jr):
    """v0.9 fork resolution (A+C): compose() NEVER computes a verdict —
    the third return value is always the empty string, regardless of
    how many blockers/majors are in `reported`. The retired blocker/
    major counting rule moved to `majors_verdict_for_measurement`
    (measurement only, V3(c)) — see test_majors_verdict_for_measurement
    below."""
    findings = [_f(0.9, 2.2), _f(0.9, 2.4)]
    _, _, verdict = jr.compose(findings, [], None)
    assert verdict == ""
    _, _, verdict = jr.compose(findings[:1], [], None)
    assert verdict == ""


def test_majors_verdict_for_measurement_flat(jr):
    """The retired verdict rule, preserved for V3(c) measurement only:
    2+ majors (or any blocker) => 'Changes requested'."""
    findings = [_f(0.9, 2.2), _f(0.9, 2.4)]
    assert jr.majors_verdict_for_measurement(findings) == "Changes requested"
    assert jr.majors_verdict_for_measurement(findings[:1]) == "Approved"


def test_majors_verdict_per_declaration_guard(jr):
    """E2 guard (a): two majors in the SAME enclosing top-level
    declaration count ONCE under per_declaration=True — flat counting
    still trips 'Changes requested' on the identical input, so the flip
    is attributable SOLELY to the per-declaration rule (spec V3(c))."""
    same_decl = [
        {"hunk": {"file": "a.py", "line": 5, "parent_declaration": "def:f:1"},
         "is_real": 0.9, "severity": 2.2, "category": "bug-risk"},
        {"hunk": {"file": "a.py", "line": 7, "parent_declaration": "def:f:1"},
         "is_real": 0.9, "severity": 2.4, "category": "bug-risk"},
    ]
    assert jr.majors_verdict_for_measurement(
        same_decl, per_declaration=False) == "Changes requested"
    assert jr.majors_verdict_for_measurement(
        same_decl, per_declaration=True) == "Approved", \
        "one declaration, two sites -> counts once, never trips the rule"

    separate_decls = [
        {"hunk": {"file": "a.py", "line": 5, "parent_declaration": "def:f:1"},
         "is_real": 0.9, "severity": 2.2, "category": "bug-risk"},
        {"hunk": {"file": "a.py", "line": 50, "parent_declaration": "def:g:40"},
         "is_real": 0.9, "severity": 2.4, "category": "bug-risk"},
    ]
    assert jr.majors_verdict_for_measurement(
        separate_decls, per_declaration=True) == "Changes requested", \
        "genuinely separate declarations still count separately"
