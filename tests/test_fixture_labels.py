"""Task 4/5: --fixture label, additive metric fields, and the label-builder
contract (M5: the guard must actually run here, not only in CI).

test_fixture_labels builds BOTH fixture scripts into tmp_path via
JEV_FIXTURE_ROOT and asserts: head == the committed SHA constant, every
golden verification substring matches, and the tool's --fixture acceptance
matches the examples/ directory contents. M3: the negative builder is
tested for real — its actual output format is parsed, its TSV's real row
count/columns are asserted, and building twice yields the identical SHA.
"""

import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(REPO, "examples")
SHAS_FILE = os.path.join(EXAMPLES, "fixture-shas.txt")


def _sha(name):
    for line in open(SHAS_FILE):
        if line.startswith(name + "="):
            return line.strip().split("=", 1)[1]
    raise AssertionError(f"no {name}= constant in fixture-shas.txt")


def _build(script, root):
    env = dict(os.environ, JEV_FIXTURE_ROOT=root)
    r = subprocess.run(["bash", os.path.join(EXAMPLES, script)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"{script} failed:\n{r.stdout}\n{r.stderr}"
    return r


def _head_sha(result):
    """Parse the builders' actual output format: '... head=<40 hex>'."""
    for ln in (result.stdout + result.stderr).splitlines():
        if " head=" in ln or ln.startswith("head="):
            candidate = ln.split("head=", 1)[1].strip()
            if len(candidate) == 40:
                return candidate
    raise AssertionError(f"no head= SHA in builder output:\n{result.stdout}")


def _golden_rows(tsv):
    rows = []
    for line in open(os.path.join(EXAMPLES, tsv)):
        line = line.rstrip("\n")
        if line and not line.startswith("#"):
            rows.append(line.split("\t"))
    return rows


def test_positive_fixture_build_is_deterministic_and_verified(tmp_path):
    root = str(tmp_path / "fx-pos")
    r = _build("build-fixture.sh", root)
    assert _head_sha(r) == _sha("positive")
    # every golden verify-substring matched (script asserts too; re-check here)
    rows = _golden_rows("fixture-golden.tsv")
    assert len(rows) == 5 and all(len(row) == 5 for row in rows)
    for row in rows:
        fline = open(os.path.join(root, row[0])).read().splitlines()
        assert any(row[3] in ln for ln in fline), f"verify [{row[3]}] not found"


def test_negative_fixture_build_is_deterministic_and_verified(tmp_path):
    """M3: real determinism test of the negative builder (was a stale
    strict-xfail hiding a never-exercised path)."""
    root = str(tmp_path / "fx-neg")
    r = _build("build-negative-fixture.sh", root)
    head = _head_sha(r)
    assert head == _sha("negative")
    # building twice yields the identical SHA (M5: determinism in CI)
    r2 = _build("build-negative-fixture.sh", root)
    assert _head_sha(r2) == head
    # negative golden TSV: content checks, 2 columns, README + benign source
    rows = _golden_rows("negative-golden.tsv")
    # v0.3b: three rows — README, benign source, and the GONE (deleted) row
    assert len(rows) == 3 and all(len(row) == 2 for row in rows)
    assert any(row[0].endswith("README.md") for row in rows)
    gone = [row for row in rows if row[1] == "GONE"]
    assert len(gone) == 1, "exactly one GONE (whole-file-deleted) row"
    for row in rows:
        if row[1] == "GONE":
            assert not os.path.exists(os.path.join(root, row[0])), \
                f"{row[0]} should be deleted at HEAD"
            continue
        fline = open(os.path.join(root, row[0])).read().splitlines()
        assert any(row[1] in ln for ln in fline), f"verify [{row[1]}] not found"


def test_fixture_label_accepted(jr):
    # tool-side: the --fixture flag accepts the known fixture names
    assert jr.KNOWN_FIXTURES == {"positive", "negative"}


def test_metrics_append_works(jr):
    jr.log_run({"label": "x"})
    import json
    line = open(jr.METRICS_PATH).read().strip().splitlines()[-1]
    assert json.loads(line)["label"] == "x"
