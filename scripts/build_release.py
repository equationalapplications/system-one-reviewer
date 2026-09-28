#!/usr/bin/env python3
"""Release build, run by semantic-release's prepare step (@semantic-release/exec).

    build_release.py <version> [--root DIR]

1. Stamps `__version__ = "<version>"` into system_one_reviewer.py; that
   file is committed back to main by @semantic-release/git.
2. Writes the release assets to dist/: `system-one-reviewer` (the stamped
   script, executable, ready to drop on PATH) and `SHA256SUMS` in
   `sha256sum -c` format.

Stdlib only, so it runs identically on macOS and the Linux runner.
"""

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys

SOURCE = "system_one_reviewer.py"
ASSET = "system-one-reviewer"
SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
VERSION_LINE = re.compile(r'^__version__ = "[^"]*"$', re.M)


def die(msg):
    sys.exit(f"build_release: {msg}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help="release version, e.g. 1.2.3 (no leading v)")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), help="repository root")
    args = ap.parse_args(argv)
    if not SEMVER.fullmatch(args.version):
        die(f"not a semver version: {args.version!r}")

    src_path = os.path.join(args.root, SOURCE)
    with open(src_path) as f:
        src = f.read()
    stamped, n = VERSION_LINE.subn(f'__version__ = "{args.version}"', src)
    if n != 1:
        die(f"expected exactly one __version__ line in {SOURCE}, found {n}")
    with open(src_path, "w") as f:
        f.write(stamped)

    dist = os.path.join(args.root, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(dist)
    asset = os.path.join(dist, ASSET)
    shutil.copyfile(src_path, asset)
    os.chmod(asset, os.stat(asset).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(asset, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(dist, "SHA256SUMS"), "w") as f:
        f.write(f"{digest}  {ASSET}\n")
    print(f"build_release: {ASSET} {args.version} sha256={digest}")


if __name__ == "__main__":
    main()
