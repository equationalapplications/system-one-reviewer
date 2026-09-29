"""The committed corpus stays valid.

Schema/split validation always runs (offline). Line verification against
the pinned SHAs needs the git cache and network, so it runs only with
SOR_CORPUS_VERIFY=1 (locally, before committing corpus changes).
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import corpus_lib as cl  # noqa: E402

CORPUS = os.path.join(REPO_ROOT, "corpus")


def test_committed_corpus_schema_and_split():
    c = cl.load_corpus(CORPUS)
    cl.check_holdout_share(c["prs"])


@pytest.mark.skipif(os.environ.get("SOR_CORPUS_VERIFY") != "1",
                    reason="set SOR_CORPUS_VERIFY=1 to check lines against pinned SHAs")
def test_committed_corpus_lines_verify():
    c = cl.load_corpus(CORPUS)
    errors = []
    for row in c["issues"] + c["dismissed"]:
        s = c["prs"][row["sample_id"]]
        _, pr, _ = cl.parse_sample_id(s["sample_id"])
        d = cl.ensure_clone(s["repo"])
        cl.ensure_commit(d, s["head_sha"], pr)
        err = cl.verify_row(d, s["head_sha"], row["file"], int(row["line"]),
                            row["verify_substring"])
        if err:
            errors.append(f"{row['sample_id']}: {err}")
    assert errors == []
