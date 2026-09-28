#!/usr/bin/env python3
"""Repair a partial semantic-release draft release.

    recover_release.py --repo OWNER/REPO [--root DIR]

`@semantic-release/github` v12 uploads assets with `Promise.all` inside
its publish step; a single asset-upload failure rejects the promise and
leaves the GitHub release as a draft with only some assets attached.
The git tag was already pushed before publish ran, so a follow-up
`workflow_dispatch` is a semantic-release no-op (no new version) and
the missing assets are never re-attempted. This script performs that
recovery: for each draft release in the repo, rebuild the assets from
the source tree pinned by the draft's tag, upload any that are missing,
then publish the draft. Releases that are not drafts are left alone.

Runs in the release job after `npx semantic-release`, so the recovery
covers both "first run failed mid-upload" and "later dispatch retried
the same tag". Stdlib only, identical behavior on macOS and the Linux
runner.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

EXPECTED_ASSETS = ("system-one-reviewer", "SHA256SUMS")
API = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "system-one-reviewer-recovery"

SOURCE = "system_one_reviewer.py"
BUILD_SCRIPT = "scripts/build_release.py"


def die(msg):
    sys.stderr.write(f"recover_release: {msg}\n")
    sys.exit(1)


def http(method, url, token, body=None, content_type=None):
    """Single chokepoint for GitHub API calls (mockable from tests)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if content_type:
        headers["Content-Type"] = content_type
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        die(f"{method} {url} -> {e.code} {body_text}")


def list_drafts(owner_repo, token):
    """Yield every draft release in the repo, paginating."""
    page = 1
    while True:
        releases = http(
            "GET",
            f"{API}/repos/{owner_repo}/releases?per_page=100&page={page}",
            token,
        )
        if not releases:
            return
        for r in releases:
            if r.get("draft"):
                yield r
        if len(releases) < 100:
            return
        page += 1


def release_assets(owner_repo, release_id, token):
    return http(
        "GET",
        f"{API}/repos/{owner_repo}/releases/{release_id}/assets",
        token,
    )


def upload_asset(release, filename, content, token):
    upload_url = release["upload_url"]
    # upload_url is a template like
    # https://uploads.github.com/repos/.../releases/{id}/assets{?name,label}
    base, _, _ = upload_url.partition("{")
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}name={urllib.parse.quote(filename)}"
    http("POST", url, token, body=content, content_type="application/octet-stream")


def publish_release(owner_repo, release_id, token):
    http(
        "PATCH",
        f"{API}/repos/{owner_repo}/releases/{release_id}",
        token,
        body=json.dumps({"draft": False}),
    )


def build_assets_for_tag(tag, root):
    """Rebuild dist/ from the source pinned by `tag`; return {name: bytes}.

    Reads `system_one_reviewer.py` from the tag (via `git show`) so the
    assets always match what semantic-release intended to publish,
    even if the working tree has since moved on.
    """
    version = tag[1:] if tag.startswith("v") else tag
    src_bytes = subprocess.check_output(
        ["git", "show", f"{tag}:{SOURCE}"], cwd=root
    )
    with tempfile.TemporaryDirectory() as tmp:
        # Mirror the layout build_release.py expects: SOURCE at the root
        # and the script in scripts/. The build mutates SOURCE in place,
        # so this temp root keeps the real working tree clean.
        os.makedirs(os.path.join(tmp, "scripts"))
        shutil.copy(
            os.path.join(root, BUILD_SCRIPT),
            os.path.join(tmp, BUILD_SCRIPT),
        )
        with open(os.path.join(tmp, SOURCE), "wb") as f:
            f.write(src_bytes)
        subprocess.check_call(
            [
                sys.executable,
                os.path.join(tmp, BUILD_SCRIPT),
                version,
                "--root",
                tmp,
            ],
            cwd=tmp,
        )
        return {
            name: open(os.path.join(tmp, "dist", name), "rb").read()
            for name in EXPECTED_ASSETS
        }


def recover(owner_repo, root, token):
    drafts = list(list_drafts(owner_repo, token))
    if not drafts:
        print("recover_release: no draft releases, nothing to do")
        return
    for release in drafts:
        tag = release["tag_name"]
        release_id = release["id"]
        existing = {a["name"] for a in
                    release_assets(owner_repo, release_id, token)}
        missing = [n for n in EXPECTED_ASSETS if n not in existing]
        if missing:
            print(f"recover_release: tag={tag} missing={missing}; rebuilding from tag")
            assets = build_assets_for_tag(tag, root)
            for name in missing:
                print(f"recover_release: uploading {name}")
                upload_asset(release, name, assets[name], token)
        else:
            print(f"recover_release: tag={tag} has all assets; publishing")
        publish_release(owner_repo, release_id, token)
        print(f"recover_release: published {tag}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True,
                    help="owner/repo, e.g. equationalapplications/system-one-reviewer")
    ap.add_argument("--root", default=os.getcwd(),
                    help="repository root (default: cwd)")
    args = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        die("GITHUB_TOKEN env var is required")
    recover(args.repo, args.root, token)


if __name__ == "__main__":
    main()
