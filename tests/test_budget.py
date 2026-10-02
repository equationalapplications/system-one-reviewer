"""Task 1 (AST-units plan rev 14): serialized-size TOKEN estimator.

The estimator measures the 32k-rule quantity — the `state` plus the
single LONGEST question, in tokens (chars / CHARS_PER_TOKEN) — NOT the
all-questions wire total (r2-M5). The full payload total is capped by
the HARD_CAP send-gate in Task 5 (r1-m2); the per-call estimate is a
lower bound of that total.

Uses the shared `jr` fixture (offline, isolated module import) like the
rest of the suite.
"""
import json
import math


def _real_questions(jr):
    """The real 3-question hunk triple (HUNK_QUESTIONS)."""
    return jr.HUNK_QUESTIONS


def test_estimate_matches_32k_quantity(jr):
    # The 32k quantity is state + longest question, NOT the total
    # (r2-M5). estimate_call_size must equal exactly that quantity in
    # tokens: (len(state_json) + max(len(q_json))) / CHARS_PER_TOKEN.
    state = {"file": "a.py",
             "location": "around line 1",
             "change_type": "code-change",
             "code_before_change": ["x = " + "1" * 500],
             "code_after_change": ["y = " + "2" * 500]}
    questions = _real_questions(jr)
    expected = ((len(json.dumps(state)) +
                 max(len(json.dumps(q)) for q in questions.values())) /
                jr.CHARS_PER_TOKEN)
    got = jr.estimate_call_size(state, questions)
    assert math.isclose(got, expected, rel_tol=1e-9)
    # NOT the all-questions total: that would be strictly larger.
    total = (len(json.dumps(state)) +
             sum(len(json.dumps(q)) for q in questions.values())) / 3.0
    assert got < total


def test_estimate_lower_bounds_full_payload(jr):
    # The per-call estimate lower-bounds the serialized wire payload of
    # one call (state + ALL questions) (r2-M5).
    state = {"file": "b.ts",
             "location": "around line 10",
             "change_type": "code-change",
             "code_before_change": ["let a = " + "b" * 300 + ";"],
             "code_after_change": ["let a = " + "c" * 300 + ";"]}
    questions = _real_questions(jr)
    est = jr.estimate_call_size(state, questions)
    full = json.dumps({"state": state, "model": "jev-latest",
                       "questions": questions})
    assert est <= len(full) / jr.CHARS_PER_TOKEN


def test_estimate_monotonic(jr):
    # r1-m3: doubling a state's text roughly doubles the estimate.
    q = jr.HUNK_QUESTIONS

    def mk(n):
        return {"file": "m.py", "location": "around line 1",
                "change_type": "code-change",
                "code_before_change": [f"line {i}" for i in range(n)],
                "code_after_change": [f"ln {i}" for i in range(n)]}

    small = jr.estimate_call_size(mk(200), q)
    big = jr.estimate_call_size(mk(400), q)
    ratio = big / small
    assert 1.8 < ratio < 2.2  # "roughly doubles" (state dominates)


def test_soft_cap_units(jr):
    # r2-M1 regression guard: the unit is TOKENS, not chars. A 100k-char
    # state estimates to ~33.3k tokens at CHARS_PER_TOKEN=3.0 — above
    # SOFT_CAP_TOKENS (28_000 TOKENS). If the estimator returned chars
    # it would read 100k and this comparison would be trivially true
    # for the wrong unit; the ~33.3k value pins the division.
    state = {"file": "big.py", "location": "around line 1",
             "change_type": "code-change",
             "code_before_change": [],
             "code_after_change": ["x" * 100_000]}
    q = jr.HUNK_QUESTIONS
    est = jr.estimate_call_size(state, q)
    assert 30_000 < est < 40_000  # ~33.3k tokens, not ~100k chars
    assert est > jr.SOFT_CAP_TOKENS
