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

import pytest


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


# ======================================================================
# Task 5: SEND gate + typed _OverBudget runtime split (plan rev 14)
# ======================================================================

# ---------- helpers ----------

def _big_state(n_chars):
    return {"file": "big.py", "location": "around line 1",
            "change_type": "code-change", "code_before_change": [],
            "code_after_change": ["x" * n_chars]}


def _hunk(i, file="f.py"):
    return {"file": file, "line": i, "hunk_start": 1, "lines": ["x"],
            "entries": [(" ", i, "x", 1)], "n_changed": 1, "header": "h",
            "size": 1, "too_large": False}


def _ok_payload(usage=None):
    p = {"answers": {
        "severity": {"score": 1.0, "probabilities": None, "confidence": 0.9},
        "is_real_issue": {"noul": 0.1},
        "category": {"choice": "style", "probabilities": None}}}
    if usage is not None:
        p["usage"] = usage
    return p


class _FakeResp:
    def __init__(self, status, body=b'{"error": "nope"}'):
        self.status = status
        self._body = body

    def read(self):
        return self._body


class _FakeConn:
    """Fake connection that counts request() calls (the one-request-only
    assertions ride on this)."""

    def __init__(self, status, body=b'{"error": "nope"}'):
        self.status = status
        self._body = body
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1

    def getresponse(self):
        return _FakeResp(self.status, self._body)


# ---------- SEND gate (r1-m2, defense-in-depth) ----------

def test_send_payload_under_hard_cap(jr):
    """r1-m2: the SEND gate checks state + ALL questions (the serialized
    wire total) <= HARD_CAP_TOKENS. Real questions cannot cross 56k once
    state + longest <= 28k, so the check is DEFENSE-IN-DEPTH (labeled as
    such) and is tested here with SYNTHETIC oversized questions
    (r2-m2): an over-hard-cap payload must be rejected before send."""
    huge_q = {"q1": "x" * 300_000}
    total = (len(json.dumps(_big_state(10_000))) +
             sum(len(json.dumps(q)) for q in huge_q.values())) \
        / jr.CHARS_PER_TOKEN
    assert total > jr.HARD_CAP_TOKENS
    assert jr.payload_over_hard_cap(_big_state(10_000), huge_q) is True
    # a legal payload passes the gate
    assert jr.payload_over_hard_cap(_big_state(10),
                                    jr.HUNK_QUESTIONS) is False


def test_send_gate_labeled_defense_in_depth(jr):
    """The gate is a never-send backstop behind the pre-judge soft-cap
    pass: judge() must refuse (not send) a unit whose wire payload
    exceeds HARD_CAP_TOKENS even when the pre-judge pass somehow
    missed it."""
    sent = []

    def spy_ask(state, questions):
        sent.append((state, questions))
        return _ok_payload(), 1.0

    h = _hunk(1)
    # a genuinely over-hard-cap payload: one 200k-char changed line
    h["entries"] = [(" ", 1, "x" * 200_000, 1)]
    h["lines"] = ["x" * 200_000]
    findings, _lat, _meta = jr.judge([h], spy_ask)
    assert sent == [], "an over-HARD-cap payload must never be sent"
    assert findings is not None and len(findings) == 1
    assert findings[0].get("parse_error") is True


# ---------- jev_ask _OverBudget (r1-m4/r8-m1) ----------

def test_overbudget_raised_in_jev_ask_not_wrapper(jr, monkeypatch):
    """400 + 'max_tokens_exceeded' in the body surfaces as _OverBudget
    from jev_ask itself; _OverBudget is a _NoRetry subclass (no 5xx
    retry, one request only)."""
    conn = _FakeConn(400, b'{"error": {"code": "max_tokens_exceeded"}}')
    monkeypatch.setattr(jr, "_get_conn", lambda c=conn: c)
    with pytest.raises(jr._OverBudget):
        jr.jev_ask({"s": 1}, [], "test-key")
    assert conn.calls == 1, "over-budget 400 must never be retried"
    assert issubclass(jr._OverBudget, jr._NoRetry)


def test_other_400_still_NoRetry(jr, monkeypatch):
    """A 401 (no max_tokens marker) keeps today's exact _NoRetry
    behavior — one request, no retry."""
    conn = _FakeConn(401)
    monkeypatch.setattr(jr, "_get_conn", lambda c=conn: c)
    with pytest.raises(jr._NoRetry) as ei:
        jr.jev_ask({"s": 1}, [], "test-key")
    assert not isinstance(ei.value, jr._OverBudget)
    assert conn.calls == 1


# ---------- judge() 3-tuple contract (r5-m6/r7-m1/r6-m2) ----------

def test_judge_return_contract(jr):
    """judge() returns (findings, latencies, meta); meta carries
    added_units (0 on a clean run) and avg_input_tokens (float for a
    jev payload with usage, None without)."""
    findings, latencies, meta = jr.judge(
        [_hunk(1)], lambda s, q: (_ok_payload(usage={"input_tokens": 1234}),
                                  1.0))
    assert findings is not None and len(findings) == 1
    assert latencies == [1.0]
    assert meta["added_units"] == 0
    assert meta["avg_input_tokens"] == 1234.0

    # no usage in the payload (laya-shaped) -> None
    _f, _l, meta2 = jr.judge([_hunk(1)], lambda s, q: (_ok_payload(), 1.0))
    assert meta2["avg_input_tokens"] is None


def test_judge_fail_open_returns_3_tuple(jr):
    """r6-m2: EVERY early return — including the three fail-open
    returns — carries the meta, so callers can unpack 3-tuples without
    a ValueError."""
    def dead(state, questions):
        raise RuntimeError("certificate verify failed")
    out = jr.judge([_hunk(1), _hunk(2)], dead)
    assert len(out) == 3
    findings, latencies, meta = out
    assert findings is None
    assert meta["added_units"] == 0
    assert meta["avg_input_tokens"] is None


# ---------- runtime split via _OverBudget (r6-m3/r7-m1) ----------

def test_runtime_400_max_tokens_splits(jr):
    """Transport raises _OverBudget on the first ask, then succeeds:
    judge() halves-and-retries via the INJECTED split_unit; the parent
    is REPLACED by its leaves; _OverBudget never escapes judge()."""
    asks = []

    def over_then_ok(state, questions):
        asks.append(state)
        if len(asks) == 1:
            raise jr._OverBudget("HTTP 400 max_tokens_exceeded")
        return _ok_payload(), 1.0

    parent = _hunk(1)
    leaf_a = dict(_hunk(2), file="f.py")
    leaf_b = dict(_hunk(3), file="f.py")
    splits = []

    def split_unit(unit):
        splits.append(unit)
        return [leaf_a, leaf_b]

    findings, _lat, meta = jr.judge([parent], over_then_ok,
                                    split_unit=split_unit)
    assert len(splits) == 1 and splits[0] is parent
    assert len(findings) == 2, "parent replaced by 2 leaves"
    assert meta["added_units"] == 1, "leaves - 1 NET (r7-m1)"
    assert len(asks) == 3, "1 parent ask + 2 leaf asks (real retry)"


def test_runtime_split_then_transport_failure_keeps_shape():
    """r17-B1 (Opus round-3): a runtime split where sub 1 succeeds and
    sub 2 then hits an ordinary transport error must NOT leak raw
    sentinel carriers into findings — every record carries a 'hunk' key
    (the chain's transport_fail still feeds the consecutive counter)."""
    import system_one_reviewer as sor

    calls = []

    def ok_then_dead(state, questions):
        calls.append(state)
        if len(calls) == 1:
            raise sor._OverBudget("HTTP 400 max_tokens_exceeded")
        if len(calls) == 2:
            return _ok_payload(), 1.0  # sub 1 succeeds
        raise RuntimeError("sub 2 timeout")  # sub 2 transport failure

    parent = _hunk(1)
    sub_a = dict(_hunk(2), file="f.py")
    sub_b = dict(_hunk(3), file="f.py")

    def split_unit(unit):
        return [sub_a, sub_b]

    errors = []
    findings, _lat, _meta = sor.judge(
        [dict(parent, entries=[(" ", 1, "x", 1), (" ", 2, "x", 2)],
              n_changed=2)],
        ok_then_dead, errors=errors, split_unit=split_unit)
    assert findings is not None
    for f in findings:
        assert "hunk" in f, f"carrier leaked into findings: {f!r}"
    # sub 1's success is a real finding; sub 2's failure is a leaf/record
    judged = [f for f in findings if not f.get("parse_error")]
    assert len(judged) == 1, "sub 1's successful judgment survives"
    assert errors and "sub 2 timeout" in errors[-1]


def test_nested_split_transport_failure_two_level_accounting():
    """r21-M1 (Opus round-7): a transport failure TWO splits deep —
    parent U splits into [A, B]; A splits into [A1, A2]; A1 judged,
    A2 transport-fails. The chain must report exactly 3 units (A1
    judged + A2 leaf + B leaf), added_units == 2, and A1's latency
    must survive — no overlapping leaf for A, no lost counts."""
    import system_one_reviewer as sor

    calls = []

    def transport(state, questions):
        calls.append(state)
        if len(calls) == 1:
            raise sor._OverBudget("HTTP 400")       # U splits -> A, B
        if len(calls) == 2:
            raise sor._OverBudget("HTTP 400")       # A splits -> A1, A2
        if len(calls) == 3:
            return _ok_payload(), 2.5               # A1 judged
        raise RuntimeError("A2 transport down")     # A2 fails

    parent = _hunk(1)
    sub_a = dict(_hunk(2), file="f.py", entries=[(" ", 1, "x", 1),
                                                 ("+", 2, "y", 1)],
                 n_changed=1)
    sub_b = dict(_hunk(3), file="f.py", entries=[(" ", 3, "z", 1),
                                                 ("+", 4, "w", 1)],
                 n_changed=1)

    def split_unit(unit):
        if unit is parent:
            return [sub_a, sub_b]
        a1 = dict(_hunk(4), file="f.py")
        a2 = dict(_hunk(5), file="f.py")
        return [a1, a2]

    findings, lat, meta = sor.judge(
        [dict(parent, entries=[(" ", 1, "x", 1), ("+", 2, "y", 1),
                               (" ", 3, "z", 1), ("+", 4, "w", 1)],
              n_changed=2)],
        transport, split_unit=split_unit)
    assert findings is not None
    judged = [f for f in findings if not f.get("parse_error")]
    leaves = [f for f in findings if f.get("parse_error")]
    assert len(judged) == 1, "A1's judgment survives"
    assert len(leaves) == 2, "A2 and B leaves — NO leaf for A itself"
    for leaf in leaves:
        assert leaf["hunk"] is not sub_a, (
            "overlapping leaf for the whole failing sub A")
    # 3 units total (A1, A2, B) replacing parent + A's nested pair:
    # base len(subs)-1 = 1, plus A's own chain delta 1 = 2.
    assert meta["added_units"] == 2, (
        f"nested growth kept: got {meta['added_units']}")
    assert 2.5 in lat, "A1's latency merged into the chain's latencies"


def test_runtime_split_leaf_first_never_leaks_carriers():
    """r18-B1 (Opus round-4): a split chain whose FIRST sub resolves to
    a leaf and whose SECOND sub is judged (leaf-first record order) must
    not leak the raw carrier into findings — every record carries
    'hunk', and the judged sub's score survives."""
    import system_one_reviewer as sor

    calls = []

    def over_leaf_ok(state, questions):
        calls.append(state)
        if len(calls) == 1:
            raise sor._OverBudget("HTTP 400 max_tokens_exceeded")
        if len(calls) == 2:
            raise sor._OverBudget("HTTP 400 max_tokens_exceeded")
        return {"answers": {
            "severity": {"score": 2.0, "probabilities": None,
                         "confidence": 0.9},
            "is_real_issue": {"noul": 0.8},
            "category": {"choice": "bug-risk", "probabilities": None}}}, 1.0

    parent = {"file": "f.py", "line": 1, "hunk_start": 1,
              "lines": ["x", "x"], "entries": [(" ", 1, "x", 1),
                                               (" ", 2, "x", 2)],
              "n_changed": 2, "header": "h", "size": 2, "too_large": False}
    sub_a = dict(parent, line=2)
    sub_b = dict(parent, line=3)

    def split_unit(unit):
        # first split: 2 subs; sub_a then splits no further (leaf)
        return [sub_a, sub_b]

    def split_unit_leaf(unit):
        return None  # unsplittable -> leaf

    def router(unit):
        return split_unit(unit) if unit is parent else split_unit_leaf(unit)

    findings, _lat, _meta = sor.judge([parent], over_leaf_ok,
                                      split_unit=router)
    assert findings is not None
    for f in findings:
        assert "hunk" in f, f"raw carrier leaked: {f!r}"
    judged = [f for f in findings if not f.get("parse_error")]
    assert len(judged) == 1 and judged[0]["severity"] == 2.0
    leaves = [f for f in findings if f.get("parse_error")]
    assert len(leaves) == 1 and leaves[0]["reason"] == "unsplittable>cap"


def test_budget_termination_bounded(jr):
    """r2-m2: the recursion helper terminates on synthetic multi-unit
    input where every attempt still over-budgets — terminates, marks
    the unit unjudged, run continues (no infinite loop, no fail-open)."""

    def always_over(state, questions):
        raise jr._OverBudget("HTTP 400 max_tokens_exceeded")

    # splitter always returns 2 halves until it can't (single entry)
    def split_unit(unit):
        entries = unit["entries"]
        if len(entries) < 2:
            return None  # unsplittable
        mid = len(entries) // 2
        def half(es):
            h = dict(unit)
            h["entries"] = es
            h["lines"] = ["x"] * len(es)
            return h
        return [half(entries[:mid]), half(entries[mid:])]

    units = []
    for i in range(4):
        u = _hunk(i + 1)
        u["entries"] = [(" ", j, "x", j) for j in range(4)]
        u["lines"] = ["x"] * 4
        units.append(u)

    findings, _lat, meta = jr.judge(units, always_over,
                                    split_unit=split_unit)
    # bounded: every unit ends as a parse_error leaf, run continues
    assert findings is not None, "no fail-open from budget exhaustion"
    assert all(f.get("parse_error") for f in findings)
    assert meta["added_units"] >= 0


def test_runtime_split_unsplittable_marks_unjudged(jr):
    """When split_unit is None (or returns None), the over-budget unit
    is marked unjudged via the SAME leaf-record shape as Task 4 — never
    a crash, never fail-open."""
    asks = []

    def always_over(state, questions):
        asks.append(state)
        raise jr._OverBudget("HTTP 400 max_tokens_exceeded")

    findings, _lat, meta = jr.judge([_hunk(1)], always_over)
    assert findings is not None
    assert len(findings) == 1
    f = findings[0]
    assert f["parse_error"] is True and f["raw"] is None
    assert f["reason"] == "unsplittable>cap"
    assert meta["added_units"] == 0


def test_overbudget_counts_one_failure(jr):
    """r3-M5: a full over-budget chain counts as ONE attempt toward the
    consecutive-failure counter, not one per split/retry."""
    n_units = 6

    def always_over(state, questions):
        raise jr._OverBudget("HTTP 400 max_tokens_exceeded")

    # unsplittable units: each unit is one over-budget chain
    units = [_hunk(i + 1) for i in range(n_units)]
    findings, _lat, _meta = jr.judge(units, always_over)
    # a single unit's chain must NOT count 2+ consecutive failures —
    # with 2 unsplittable units we would already be at the limit if
    # each chain counted twice.
    assert findings is not None
    assert len(findings) == n_units


def test_consecutive_accounting_single(jr):
    """r3-M5: one unit's full over-budget chain (ask -> _OverBudget ->
    split -> ask -> _OverBudget -> leaf) advances the consecutive
    failure counter by exactly ONE — a second unit's chain can follow
    without tripping the CALL_FAIL_LIMIT fail-open."""
    def always_over(state, questions):
        raise jr._OverBudget("HTTP 400 max_tokens_exceeded")

    # build splitters that halve down to unsplittable: 3 nested levels
    def split_unit(unit):
        entries = unit["entries"]
        if len(entries) < 2:
            return None
        mid = len(entries) // 2

        def half(es):
            h = dict(unit)
            h["entries"] = es
            h["lines"] = ["x"] * len(es)
            return h
        return [half(entries[:mid]), half(entries[mid:])]

    units = []
    for i in range(4):
        u = _hunk(i + 1)
        u["entries"] = [(" ", j, "x", j) for j in range(4)]
        u["lines"] = ["x"] * 4
        units.append(u)
    # each unit costs 1+1+2+4 = 8 asks (3 splits) — 4 units = 32 asks;
    # if each ASK counted as a consecutive failure the run would
    # fail-open at the 2nd ask.
    findings, _lat, _meta = jr.judge(units, always_over,
                                     split_unit=split_unit)
    # each unit's chain: 4 entries -> 2+2 -> 1+1 leaves = 4 leaves/unit
    assert findings is not None, "chain counts once per unit"
    assert len(findings) == 16  # 4 units x 4 leaves each


# ---------- runtime-split counters through main() (r2-M2/r9-m1/r2-M4) ----

def _wire_runtime_split_main(jr, monkeypatch, tmp_path, records, usage):
    """Stage a main() run where the FIRST judged unit over-budgets and
    the injected split_unit splits it into two sub-units (both then
    judged OK)."""
    import json as _json
    diff = ("diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            "@@ -1,1 +1,2 @@\n x\n+x = 2\n")

    calls = {"n": 0}

    def fake_judge(kept, ask, errors=None, split_unit=None):
        # emulate the runtime split: first ask over-budget, split into
        # 2 leaves, second ask OK — through the REAL machinery:
        return jr.__dict__["_judge_impl"](kept, ask, errors=errors,
                                          split_unit=split_unit)

    # use the real judge; make the transport raise _OverBudget once
    transport_calls = []

    def transport(state, questions):
        transport_calls.append(state)
        calls["n"] += 1
        if calls["n"] == 1:
            raise jr._OverBudget("HTTP 400 max_tokens_exceeded")
        return _ok_payload(usage=usage), 1.0

    def split_unit(unit):
        if transport_calls:
            pass
        a = dict(unit)
        a["entries"] = [(" ", 1, "x", 1)]
        b = dict(unit)
        b["line"] = unit["line"] + 1
        b["entries"] = [(" ", 2, "x = 2", 1)]
        return [a, b]

    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: transport)
    monkeypatch.setattr(jr, "set_provider_name", lambda name: None)
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    monkeypatch.setattr(jr, "resolve_diff",
                        lambda r, a: (diff, "0" * 40, "staged"))
    monkeypatch.setattr(jr, "judge_pr_level",
                        lambda f, a, size_skipped_code=None:
                        {"overall_risk": 1.0, "needs_human_review": 0.5,
                         "latency_ms": 1.0})
    monkeypatch.setattr(jr, "log_run",
                        lambda rec: records.append(_json.loads(
                            _json.dumps(rec, default=str))))
    monkeypatch.setattr(jr.sys, "argv",
                        ["system-one-reviewer", "--repo", str(tmp_path),
                         "--staged", "--provider", "jev", "--json"])


def test_runtime_split_counts_consistent(jr, monkeypatch, tmp_path, capsys):
    """r2-M2/r9-m1: a run where one unit 400s then splits at runtime —
    len(judged) == n_analyzed on the LOGGED record, n_dropped == 0, and
    NO '(incomplete' suffix (a legal runtime split is complete).
    r20-M2 (round-6): the halving cut now emits only the CHANGED half
    (a context-only half is glue, never judged), so 1 unit -> 1 judged
    sub-unit; the counts stay consistent on that."""
    records = []
    _wire_runtime_split_main(jr, monkeypatch, tmp_path, records,
                             usage={"input_tokens": 900})
    jr.main()
    out = json.loads(capsys.readouterr().out)
    assert len(records) == 1
    rec = records[0]
    assert len(rec["judged"]) == rec["n_analyzed"], (
        "runtime-split run: judged entries == n_analyzed")
    assert rec["n_dropped"] == 0
    assert "(incomplete" not in rec["verdict"]
    assert out["meta"]["n_analyzed"] == 1  # 1 unit -> 1 changed-half sub


def test_input_tokens_logged(jr, monkeypatch, tmp_path, capsys):
    """r2-M4: usage.input_tokens from the payload reaches the ledger as
    avg_input_tokens via judge()'s meta; a laya-shaped payload (no
    usage) logs None."""
    records = []
    _wire_runtime_split_main(jr, monkeypatch, tmp_path, records,
                             usage={"input_tokens": 4242})
    jr.main()
    rec = records[0]
    assert rec.get("avg_input_tokens") == 4242.0
    assert "(incomplete" not in rec["verdict"]
