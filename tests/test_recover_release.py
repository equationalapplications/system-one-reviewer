"""Recovery script (scripts/recover_release.py).

The HTTP layer is mocked via urllib.request.urlopen: the recovery
script only knows how to call the GitHub REST API, so we record what
it called and feed it canned responses.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOVER = os.path.join(REPO_ROOT, "scripts", "recover_release.py")
BUILD = os.path.join(REPO_ROOT, "scripts", "build_release.py")

sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
import recover_release  # noqa: E402


class FakeResponse:
    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _draft(id_, tag):
    return {
        "id": id_,
        "tag_name": tag,
        "upload_url": (
            f"https://uploads.github.com/repos/o/r/releases/{id_}/assets"
            "{?name,label}"
        ),
        "draft": True,
    }


def _make_http(drafts_page, assets_by_release):
    """Return a fake urlopen + lists to inspect calls."""
    calls = []

    def fake(req):
        url = req.full_url
        method = req.method
        calls.append((method, url, req.data))
        if method == "GET" and "/releases?" in url:
            return FakeResponse(json.dumps(drafts_page).encode())
        if method == "GET" and "/releases/" in url and url.endswith("/assets"):
            # /repos/o/r/releases/{id}/assets
            parts = url.rsplit("/releases/", 1)[1].split("/")
            release_id = int(parts[0])
            return FakeResponse(
                json.dumps(assets_by_release.get(release_id, [])).encode()
            )
        if method == "POST":
            return FakeResponse(b"{}")
        if method == "PATCH":
            return FakeResponse(b"{}")
        raise AssertionError(f"unexpected call: {method} {url}")

    return fake, calls


def test_no_drafts_is_noop(tmp_path, monkeypatch, capsys):
    fake, calls = _make_http([], {})
    monkeypatch.setattr("urllib.request.urlopen", fake)
    recover_release.recover("o/r", str(tmp_path), "token")
    # Only the list-releases call; nothing to publish or upload.
    assert [c[0] for c in calls] == ["GET"]
    assert "nothing to do" in capsys.readouterr().out


def test_draft_with_all_assets_is_just_published(tmp_path, monkeypatch):
    drafts = [_draft(7, "v1.2.3")]
    assets = [{"name": "system-one-reviewer"}, {"name": "SHA256SUMS"}]
    fake, calls = _make_http(drafts, {7: assets})
    monkeypatch.setattr("urllib.request.urlopen", fake)
    recover_release.recover("o/r", str(tmp_path), "token")
    methods = [c[0] for c in calls]
    # list, assets GET, then PATCH to publish — no POST (no upload).
    assert methods == ["GET", "GET", "PATCH"]
    patch_url = calls[-1][1]
    assert patch_url.endswith("/releases/7")
    assert json.loads(calls[-1][2]) == {"draft": False}


def test_draft_missing_assets_uploads_then_publishes(tmp_path, monkeypatch):
    drafts = [_draft(9, "v1.2.3")]
    assets = [{"name": "SHA256SUMS"}]  # system-one-reviewer missing
    fake, calls = _make_http(drafts, {9: assets})
    monkeypatch.setattr("urllib.request.urlopen", fake)
    # Stub the git+build dance; that path has its own integration test.
    monkeypatch.setattr(
        recover_release,
        "build_assets_for_tag",
        lambda tag, root: {
            "system-one-reviewer": b"# rebuilt script\n",
            "SHA256SUMS": b"deadbeef  system-one-reviewer\n",
        },
    )
    recover_release.recover("o/r", str(tmp_path), "token")
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    upload_url = posts[0][1]
    assert "name=system-one-reviewer" in upload_url
    assert upload_url.startswith(
        "https://uploads.github.com/repos/o/r/releases/9/assets?"
    )
    # And finally a publish PATCH.
    assert calls[-1][0] == "PATCH"
    assert json.loads(calls[-1][2]) == {"draft": False}


def test_pagination_walks_pages(tmp_path, monkeypatch):
    page1 = [_draft(1, "v0.0.1")] + [{"draft": False}] * 99  # full page, mix
    page2 = [_draft(2, "v0.0.2")]
    responses = iter([page1, page2])

    calls = []

    def fake(req):
        url = req.full_url
        method = req.method
        calls.append((method, url))
        if method == "GET" and "/releases?" in url:
            page = next(responses)
            return FakeResponse(json.dumps(page).encode())
        if method == "GET" and url.endswith("/assets"):
            return FakeResponse(b"[]")
        if method == "POST":
            return FakeResponse(b"{}")
        if method == "PATCH":
            return FakeResponse(b"{}")
        raise AssertionError(f"unexpected call: {method} {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    monkeypatch.setattr(
        recover_release,
        "build_assets_for_tag",
        lambda tag, root: {
            "system-one-reviewer": b"# rebuilt\n",
            "SHA256SUMS": b"deadbeef  system-one-reviewer\n",
        },
    )
    recover_release.recover("o/r", str(tmp_path), "token")
    list_calls = [c[1] for c in calls if "/releases?" in c[1]]
    assert any("page=1" in u for u in list_calls)
    assert any("page=2" in u for u in list_calls)
    # Two publish PATCHes, one per draft.
    patches = [c for c in calls if c[0] == "PATCH"]
    assert len(patches) == 2


def test_build_assets_for_tag_uses_tagged_source():
    """Integration: `git show` plus build_release.py produces the right assets.

    Uses a fresh git repo with a tag we create on the fly so the
    `system_one_reviewer.py` at that commit is a known version.
    """
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.check_call(["git", "init", "-q", "-b", "main"], cwd=tmp)
        subprocess.check_call(
            ["git", "config", "user.email", "test@example.com"], cwd=tmp
        )
        subprocess.check_call(["git", "config", "user.name", "t"], cwd=tmp)
        # Stage a known source so the tag pins it.
        os.makedirs(os.path.join(tmp, "scripts"))
        shutil.copy(BUILD, os.path.join(tmp, "scripts", "build_release.py"))
        shutil.copy(
            os.path.join(REPO_ROOT, "system_one_reviewer.py"),
            os.path.join(tmp, "system_one_reviewer.py"),
        )
        subprocess.check_call(["git", "add", "-A"], cwd=tmp)
        subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=tmp)
        subprocess.check_call(["git", "tag", "v9.9.9"], cwd=tmp)

        # Now mutate HEAD's source so the tag-pinned source differs.
        with open(os.path.join(tmp, "system_one_reviewer.py"), "a") as f:
            f.write("# HEAD-only churn\n")
        subprocess.check_call(["git", "add", "-A"], cwd=tmp)
        subprocess.check_call(["git", "commit", "-q", "-m", "head churn"], cwd=tmp)

        assets = recover_release.build_assets_for_tag("v9.9.9", tmp)
        assert set(assets) == {"system-one-reviewer", "SHA256SUMS"}
        # The script is rebuilt from the tag, so its content must NOT include
        # the HEAD-only churn line.
        assert b"# HEAD-only churn" not in assets["system-one-reviewer"]
        # SHA256SUMS is `sha256sum -c` format for the rebuilt script.
        digest = hashlib.sha256(assets["system-one-reviewer"]).hexdigest()
        assert assets["SHA256SUMS"].decode() == f"{digest}  system-one-reviewer\n"


def test_missing_token_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv",
                        ["recover_release.py", "--repo", "o/r",
                         "--root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        recover_release.main()
    assert exc.value.code != 0
    assert "GITHUB_TOKEN" in capsys.readouterr().err
