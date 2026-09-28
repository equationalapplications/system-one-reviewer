"""Versioning + the release build (scripts/build_release.py).

semantic-release's prepare step runs build_release.py with the next
version: it stamps __version__ in the source (committed back by
@semantic-release/git) and writes the release assets — the runnable
script and its SHA256SUMS — to dist/.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(REPO_ROOT, "scripts", "build_release.py")


def test_version_constant_is_semver_like(jr):
    import re
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", jr.__version__)


def test_version_flag_prints_version(jr, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["system-one-reviewer", "--version"])
    with pytest.raises(SystemExit) as exc:
        jr.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"system-one-reviewer {jr.__version__}"


def test_metrics_record_carries_tool_version(jr, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(jr, "make_provider", lambda *a, **k: None)
    monkeypatch.setattr(jr, "set_provider_name", lambda name: None)
    monkeypatch.setattr(jr, "resolve_diff", lambda r, a: ("", "0" * 40, "m"))
    monkeypatch.setattr(jr, "load_api_key", lambda: "k")
    metrics = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(jr, "METRICS_PATH", str(metrics))
    monkeypatch.setattr("sys.argv", ["system-one-reviewer", "--repo",
                                     str(tmp_path), "--range", "A..B"])
    jr.main()
    rec = json.loads(metrics.read_text().splitlines()[-1])
    assert rec["tool_version"] == jr.__version__


@pytest.fixture
def src_copy(tmp_path):
    """build_release.py mutates the source it is pointed at — use a copy."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(os.path.join(REPO_ROOT, "system_one_reviewer.py"), root)
    return root


def _build(root, version):
    return subprocess.run([sys.executable, BUILD, version, "--root", str(root)],
                          capture_output=True, text=True)


def test_build_stamps_version_and_writes_assets(src_copy):
    r = _build(src_copy, "1.2.3")
    assert r.returncode == 0, r.stderr
    src = (src_copy / "system_one_reviewer.py").read_text()
    assert '__version__ = "1.2.3"' in src
    asset = src_copy / "dist" / "system-one-reviewer"
    assert asset.read_text() == src
    assert os.access(asset, os.X_OK), "the asset must be directly runnable"
    out = subprocess.run([str(asset), "--version"], capture_output=True, text=True)
    assert out.stdout.strip() == "system-one-reviewer 1.2.3"
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    sums = (src_copy / "dist" / "SHA256SUMS").read_text()
    assert sums == f"{digest}  system-one-reviewer\n"  # `sha256sum -c` format


def test_build_rejects_non_semver(src_copy):
    r = _build(src_copy, "v1.2")
    assert r.returncode != 0
    assert "version" in r.stderr


def test_build_is_idempotent(src_copy):
    assert _build(src_copy, "1.2.3").returncode == 0
    assert _build(src_copy, "1.2.4").returncode == 0
    src = (src_copy / "system_one_reviewer.py").read_text()
    assert src.count("__version__ = ") == 1
    assert '__version__ = "1.2.4"' in src


def test_build_fails_loudly_without_version_line(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "system_one_reviewer.py").write_text("print('no version here')\n")
    r = _build(root, "1.0.0")
    assert r.returncode != 0
    assert "__version__" in r.stderr
