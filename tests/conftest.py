"""Shared test harness: isolated, offline import of jev-review.py.

The `jr` fixture loads the single-file tool via spec_from_file_location with
JEV_REVIEW_METRICS and HOME pointed into a tmp dir and TYPESAFE_API_KEY unset,
so tests never touch real state, the network, or an API key. Import order
matters: env must be set before exec_module (METRICS_PATH is read at import
time), then METRICS_PATH is re-pointed defensively at the tmp path.
"""

import importlib.util
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_PATH = os.path.join(REPO_ROOT, "jev-review.py")


@pytest.fixture
def jr(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_REVIEW_METRICS",
                       str(tmp_path / "jev-review" / "metrics.jsonl"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.syspath_prepend(REPO_ROOT)
    spec = importlib.util.spec_from_file_location("jev-review-under-test",
                                                  TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    mod.METRICS_PATH = str(tmp_path / "jev-review" / "metrics.jsonl")
    return mod


@pytest.fixture
def no_metrics(jr, monkeypatch):
    """jr with the metrics append stubbed out (for tests that must not log)."""
    monkeypatch.setattr(jr, "log_run", lambda record: None)
    return jr
