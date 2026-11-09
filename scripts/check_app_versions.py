#!/usr/bin/env python3
"""Report apps whose sources changed without a MANIFEST.JSON version bump.

An app only reaches users when its `version` changes: the curated index and
BadgeHub both key releases by version, so a rebuilt package with an unchanged
version is never offered as an update.

For every app under internal_filesystem/apps this script finds the commit that
last changed the `version` field and lists the commits (and uncommitted edits)
that came after it.

Usage:
    scripts/check_app_versions.py                  # audit every bundled app
    scripts/check_app_versions.py --changed        # only apps changed vs origin/main
    scripts/check_app_versions.py --changed --base upstream/main
    scripts/check_app_versions.py --app com.micropythonos.musicplayer

Symlinked (external repository) apps are skipped: their versions live in another
repository, so run the same check there.
"""

import argparse
import json
import os
import subprocess
import sys

APPS_DIR = "internal_filesystem/apps"


def git(*args):
    result = subprocess.run(["git"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def version_at(commit, path):
    raw = git("show", "%s:%s/MANIFEST.JSON" % (commit, path))
    if raw is None:
        return None
    try:
        return json.loads(raw).get("version")
    except ValueError:
        return None


def last_bump_commit(commits, path):
    for commit in commits:
        if version_at(commit, path) != version_at(commit + "^", path):
            return commit
    return None


def app_dirs():
    try:
        names = os.listdir(APPS_DIR)
    except OSError:
        return []
    return sorted(name for name in names if os.path.isdir(os.path.join(APPS_DIR, name)))


def changed_apps(base):
    merge_base = git("merge-base", base, "HEAD")
    if merge_base is None:
        raise SystemExit("Cannot find the merge base of %s and HEAD" % base)
    merge_base = merge_base.strip()
    names = set()
    tracked = git("diff", "--name-only", merge_base, "HEAD", "--", APPS_DIR) or ""
    status = git("status", "--porcelain", "--", APPS_DIR) or ""
    for line in tracked.splitlines() + [entry[3:] for entry in status.splitlines()]:
        parts = line.strip().split("/")
        if len(parts) >= 3 and parts[0] == "internal_filesystem" and parts[1] == "apps":
            names.add(parts[2])
    return sorted(names)


def describe(name):
    path = os.path.join(APPS_DIR, name)
    repo = "."
    if os.path.islink(path):
        return {
            "name": name,
            "external": True,
            "version": None,
            "pending": [],
        }
    commits = (git("log", "--no-merges", "--format=%H", "--", path) or "").split()
    bump = last_bump_commit(commits, path)
    pending = commits[: commits.index(bump)] if bump else commits
    status = git("status", "--porcelain", "--", path) or ""
    return {
        "name": name,
        "external": False,
        "tracked": bool(commits),
        "version": version_at("HEAD", path),
        "bump": bump,
        "pending": pending,
        "dirty": [line for line in status.splitlines() if line.strip()],
        "repo": repo,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--changed",
        action="store_true",
        help="only check apps changed since --base (including uncommitted edits)",
    )
    parser.add_argument("--base", default="origin/main", help="base ref for --changed (default: origin/main)")
    parser.add_argument("--app", action="append", default=[], help="only check this app (repeatable)")
    args = parser.parse_args()

    names = app_dirs()
    if args.changed:
        names = [name for name in names if name in changed_apps(args.base)]
    if args.app:
        wanted = set(args.app)
        names = [name for name in names if name in wanted]
        missing = wanted.difference(names)
        if missing:
            print("Unknown or unchanged app: %s" % ", ".join(sorted(missing)), file=sys.stderr)
            return 2

    if not names:
        print("No apps to check.")
        return 0

    problems = []
    for name in names:
        info = describe(name)
        if info["external"]:
            print("%-38s external repository (check it there)" % name)
            continue
        if not info["tracked"]:
            print("%-38s not tracked (skipped)" % name)
            continue
        if info["pending"] or info["dirty"]:
            problems.append(info)
            print(
                "%-38s %-8s NEEDS BUMP (%d commit(s), %d dirty file(s))"
                % (name, info["version"], len(info["pending"]), len(info["dirty"]))
            )
            for commit in info["pending"][:10]:
                subject = (git("show", "-s", "--format=%s", commit) or "").strip()
                print("    %s %s" % (commit[:8], subject))
            if len(info["pending"]) > 10:
                print("    ... and %d more" % (len(info["pending"]) - 10))
            for line in info["dirty"][:10]:
                print("    uncommitted: %s" % line)
        else:
            print("%-38s %-8s ok" % (name, info["version"]))

    if problems:
        print(
            "\n%d app(s) changed without a version bump. Bump MANIFEST.JSON "
            "before bundling." % len(problems),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
