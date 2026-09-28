"""Task 12 (E8): provider facade — hosted (jev) or local (laya) models.

Contract: ask(state, questions) -> (payload, latency_ms) with
payload["answers"][name] carrying score/noul/choice. jev is the existing
client behind the facade; laya is imported lazily with an injected fake
router in tests. No network, no laya install, no API key (conftest).
"""

import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _questions():
    return {"q1": "...", "q2": "..."}


# ---------- selection ----------

def test_default_provider_is_jev(jr, monkeypatch):
    monkeypatch.delenv("SOR_PROVIDER", raising=False)
    assert jr.provider_from(None, None) == ("jev", None)


def test_sor_provider_env_is_the_default(jr, monkeypatch):
    monkeypatch.setenv("SOR_PROVIDER", "laya")
    assert jr.provider_from(None, None) == ("laya", "convaiinnovations/rl-agent")


def test_flag_beats_env(jr, monkeypatch):
    monkeypatch.setenv("SOR_PROVIDER", "laya")
    assert jr.provider_from("jev", None) == ("jev", None)


def test_unknown_provider_exits_cleanly(jr):
    with pytest.raises(SystemExit, match="unknown provider"):
        jr.provider_from("gpt4", None)


# ---------- facade dispatch ----------

def test_jev_facade_uses_injected_transport(jr):
    calls = []

    def fake_transport(state, questions):
        calls.append((state, questions))
        return {"answers": {"q1": {"score": 0.9}}}, 12

    jr.set_transport(fake_transport)
    payload, ms = jr.ask({"hunk": "x"}, _questions())
    assert payload["answers"]["q1"]["score"] == 0.9
    assert ms == 12
    assert calls and calls[0][1] == _questions()


def test_laya_facade_uses_injected_router(jr):
    calls = []

    class FakeRouter:
        def predict(self, state, questions):
            calls.append((state, questions))
            return {"answers": {"q1": {"noul": True}}}

    router = FakeRouter()
    payload, ms = jr.laya_ask(router, {"hunk": "x"}, _questions())
    assert payload["answers"]["q1"]["noul"] is True
    assert ms >= 0
    assert calls and calls[0][1] == _questions()


def test_same_router_instance_reused_per_process(jr):
    made = []

    class FakeRouter:
        def predict(self, state, questions):
            return {"answers": {}}

    def fake_import(name):
        class mod:
            @staticmethod
            def Router():
                made.append(1)
                return FakeRouter()

        return mod

    r1 = jr.get_laya_router(loader=fake_import)
    r2 = jr.get_laya_router(loader=fake_import)
    assert r1 is r2 and len(made) == 1


def test_laya_missing_package_is_a_clean_error(jr, monkeypatch):
    monkeypatch.setattr(jr, "_LAYA_ROUTER", None)

    def no_laya(name):
        raise ImportError("No module named 'laya'")

    with pytest.raises(SystemExit, match="pip install laya"):
        jr.laya_ask_or_die(model=None, loader=no_laya)


def test_make_provider_returns_bound_ask(jr, monkeypatch):
    calls = []

    def fake_jev_ask(state, questions, api_key):
        calls.append((state, questions, api_key))
        return {"answers": {}}, 5

    monkeypatch.setattr(jr, "jev_ask", fake_jev_ask)
    ask = jr.make_provider("jev", None, api_key="test-key")
    # the provider closure is registered as the module dispatch target...
    assert jr._TRANSPORT is ask
    # ...and dispatches to jev_ask with the bound key (E8 contract)
    payload, ms = jr.ask({"s": 1}, {"q": "?"})
    assert payload == {"answers": {}} and ms == 5
    assert calls == [({"s": 1}, {"q": "?", }, "test-key")]


def test_make_provider_laya_uses_router(jr, monkeypatch):
    """m7: the LAZY-LOAD path through make_provider must be exercised —
    get_laya_router is called with an injected fake loader (never a
    pre-seeded _LAYA_ROUTER), and the returned closure dispatches to it."""
    calls = []

    class FakeRouter:
        def predict(self, state, questions):
            calls.append((state, questions))
            return {"answers": {"q": {"choice": "bug-risk"}}}

    def fake_loader(name):
        assert name == "laya"
        class laya_mod:
            @staticmethod
            def load(model=None):
                assert model == "ckp-1"
                return FakeRouter()
        return laya_mod

    monkeypatch.setattr(jr, "_LAYA_ROUTER", None)  # force the lazy load
    ask = jr.make_provider("laya", "ckp-1")
    # first call loads the router through get_laya_router's lazy import;
    # only the "laya" import is faked, everything else imports normally
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "laya":
            return fake_loader(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    payload, ms = ask({"s": 1}, {"q": "?"})
    assert payload["answers"]["q"]["choice"] == "bug-risk" and ms >= 0
    assert calls == [({"s": 1}, {"q": "?"})]
    # router is cached for the process: second call does NOT reload
    payload2, _ = ask({"s": 2}, {"q": "??"})
    assert calls == [({"s": 1}, {"q": "?"}), ({"s": 2}, {"q": "??"})]


# ---------- metrics fields ----------

def test_metrics_carry_provider_and_model(jr, tmp_path):
    """m7: call the REAL log_run and assert on the actual record it wrote —
    provider/model must reach the committed jsonl, not a monkeypatched stub."""
    metrics = tmp_path / "m" / "metrics.jsonl"
    jr.METRICS_PATH = str(metrics)
    jr.log_run({"provider": "jev", "model": None, "label": "m7"})
    line = metrics.read_text().strip().splitlines()[-1]
    import json
    rec = json.loads(line)
    assert rec["provider"] == "jev" and rec["model"] is None
    assert rec["label"] == "m7" and "ts" in rec


# ---------- sweep grouping is already tested in test_sweep.py ----------

def test_sweep_rejects_mixed_providers_end_to_end(jr, tmp_path, capsys):
    """m7: a metrics.jsonl whose SELECTED runs mix providers must make the
    sweep script's main() die with a hard provider error (end to end).
    m3 (r2): the check runs after the stale-run gate, so the fixture needs
    the full 3+3 run complement — a stale stray alone is skipped, not fatal."""
    import json
    golden = tmp_path / "g.tsv"
    golden.write_text("a.py\t10\tx\n")

    def pos(i):
        return {"label": f"v03b-mix-baseline-{i}", "fixture": "positive",
                "fixture_head": "a" * 40, "head": "a" * 10,
                "packaging_version": "v03b", "provider": "jev", "model": None,
                "judged": []}

    def neg(i, provider="laya"):
        return {"label": f"v03b-mix-negative-{i}", "fixture": "negative",
                "fixture_head": "b" * 40, "head": "b" * 10,
                "packaging_version": "v03b", "provider": provider,
                "model": "convaiinnovations/rl-agent", "judged": []}

    # 3 positive (jev) + 3 negative, one of which is laya -> mixed survivors.
    recs = [pos(1), pos(2), pos(3), neg(1), neg(2), neg(3, provider="jev"),
            neg(4, provider="laya")]
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text("".join(json.dumps(r) + "\n" for r in recs))
    shas = tmp_path / "shas.txt"
    shas.write_text(f"positive={'a' * 40}\nnegative={'b' * 40}\n")
    sw_path = os.path.join(REPO_ROOT, "scripts", "sweep-thresholds.py")
    r = subprocess.run([sys.executable, sw_path, "--metrics", str(metrics),
                        "--label", "v03b-mix-", "--golden", str(golden),
                        "--negative-golden", str(golden),
                        "--shas", str(shas)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "provider" in (r.stderr + r.stdout).lower()


def test_sweep_skips_stale_mixed_provider_run(jr, tmp_path):
    """m3 (r2): a stale run whose provider differs is EXCLUDED by the
    stale-run gate, not a hard mixed-provider error."""
    import json
    golden = tmp_path / "g.tsv"
    golden.write_text("a.py\t10\tx\n")

    def rec(label, fixture, sha, provider, model=None):
        # 5-char seed x 8 = a full 40-char SHA (the shas-file gate requires
        # the full length even for synthetic runs).
        return {"label": label, "fixture": fixture,
                "fixture_head": sha * 8, "head": (sha * 8)[:10],
                "packaging_version": "v03b",
                "provider": provider, "model": model, "judged": []}

    # negative-3 is stale (wrong fixture SHA) AND laya: must be skipped.
    recs = [rec("v03b-stale-baseline-1", "positive", "a", "jev"),
            rec("v03b-stale-baseline-2", "positive", "a", "jev"),
            rec("v03b-stale-baseline-3", "positive", "a", "jev"),
            rec("v03b-stale-negative-1", "negative", "b", "jev"),
            rec("v03b-stale-negative-2", "negative", "b", "jev"),
            rec("v03b-stale-negative-3", "negative", "c", "laya",
                "convaiinnovations/rl-agent")]
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text("".join(json.dumps(r) + "\n" for r in recs))
    shas = tmp_path / "shas.txt"
    shas.write_text(f"positive={'a' * 40}\nnegative={'b' * 40}\n")
    sw_path = os.path.join(REPO_ROOT, "scripts", "sweep-thresholds.py")
    r = subprocess.run([sys.executable, sw_path, "--metrics", str(metrics),
                        "--label", "v03b-stale-", "--golden", str(golden),
                        "--negative-golden", str(golden),
                        "--shas", str(shas)],
                       capture_output=True, text=True)
    # The laya run is skipped by the SHA gate; survivors are all jev, so the
    # failure must be the >=3 bar (2 negatives), never a provider error.
    combined = (r.stderr + r.stdout).lower()
    assert "provider" not in combined
    assert "3 runs per fixture" in combined
