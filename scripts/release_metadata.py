#!/usr/bin/env python3
"""Prepare the updates (OTA) and install (web installer) repos for a release.

The assets come from the published GitHub release of this repository, not from
a local build tree, and the metadata is rewritten the way
../docs/docs/other/release-checklist.md describes:

  updates/  releases/<target>/MicroPythonOS_<target>_<version>.ota, plus
            version/download_url/changelog in the three real
            osupdate_<target>.json files (every other board file is a symlink
            to one of them).
  install/  firmware_images/<target>/MicroPythonOS_<target>_<version>.bin,
            manifests/<target>/MicroPythonOS_<target>_<major.minor>.x.json,
            and index.html (current entries, old-release block, fallback).

Usage:
    scripts/release_metadata.py 0.22.0
    scripts/release_metadata.py 0.22.0 --dry-run
    scripts/release_metadata.py 0.22.0 --commit --push
    scripts/release_metadata.py 0.22.0 --install-only
    scripts/release_metadata.py 0.22.0 --assets-dir tmp/release_0220

--assets-dir skips the GitHub download and uses already-fetched files (handy
when the release is not public yet). Both repos default to siblings of this
checkout (../install and ../updates); override with --install-dir /
--updates-dir or MPOS_INSTALL_DIR / MPOS_UPDATES_DIR.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
TARGETS = ("esp32", "esp32s3", "esp32p4")
UPDATES_BASE_URL = "https://updates.micropythonos.com/releases"
OLD_RELEASES_LABEL = '<div class="old-releases-label">'


class ReleaseError(Exception):
    pass


def log(message):
    print(message, flush=True)


def changelog_section(version):
    text = CHANGELOG.read_text()
    heading = "%s\n%s\n" % (version, "=" * len(version))
    if heading not in text:
        raise ReleaseError("CHANGELOG.md has no '%s' section" % version)
    start = text.index(heading) + len(heading)
    next_heading = re.search(r"^\d+\.\d+\.\d+\n=+\n", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()


def json_changelog(version):
    section = changelog_section(version)
    return ('%s\n\n' % version + section).replace('"', "'").replace("\n", "\\n")


def release_assets(version):
    """Map asset name -> size (bytes) for a published release."""
    completed = subprocess.run(
        ["gh", "release", "view", version, "--json", "assets"],
        capture_output=True, text=True, check=True,
    )
    return {asset["name"]: asset["size"] for asset in json.loads(completed.stdout)["assets"]}


def needed_assets(version):
    names = []
    for target in TARGETS:
        for suffix in (".bin", ".ota"):
            names.append("MicroPythonOS_%s_%s%s" % (target, version, suffix))
    return names


def download_assets(version, destination):
    destination.mkdir(parents=True, exist_ok=True)
    sizes = release_assets(version)
    for name in needed_assets(version):
        path = destination / name
        if path.is_file() and path.stat().st_size == sizes.get(name):
            continue
        if path.is_file():
            log("  removing incomplete %s" % name)
            path.unlink()
        log("  downloading %s" % name)
        subprocess.run(
            ["gh", "release", "download", version, "--dir", str(destination),
             "--pattern", name, "--clobber"],
            check=True,
        )
    return destination


def verify_assets(assets_dir, version):
    try:
        sizes = release_assets(version)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sizes = {}
    for name in needed_assets(version):
        path = assets_dir / name
        if not path.is_file():
            raise ReleaseError("missing release asset: %s" % path)
        if sizes and path.stat().st_size != sizes[name]:
            raise ReleaseError(
                "incomplete release asset: %s is %d bytes, the release has %d"
                % (path, path.stat().st_size, sizes[name]))


def find_asset(assets_dir, name):
    path = assets_dir / name
    if not path.is_file():
        raise ReleaseError("missing release asset: %s" % name)
    return path


def run_git(repo, args):
    log("  git -C %s %s" % (repo.name, " ".join(args)))
    subprocess.run(["git", "-C", str(repo)] + args, check=True)


def commit(repo, version):
    if not subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                          capture_output=True, text=True).stdout.strip():
        log("  %s: nothing to commit" % repo.name)
        return
    run_git(repo, ["add", "-A"])
    run_git(repo, ["commit", "-q", "-m", "Release %s" % version])


def current_minor(install_dir):
    index = (install_dir / "index.html").read_text()
    marker = index.find(OLD_RELEASES_LABEL)
    current = index[:marker]
    match = re.search(r'value="/manifests/esp32s3/MicroPythonOS_esp32s3_(\d+\.\d+)\.x\.json"',
                      current)
    if not match:
        raise ReleaseError("cannot find the current ESP32-S3 manifest in index.html")
    return match.group(1)


def update_updates_repo(updates_dir, version, assets_dir):
    releases = updates_dir / "releases"
    changelog = json_changelog(version)
    for target in TARGETS:
        asset = find_asset(assets_dir, "MicroPythonOS_%s_%s.ota" % (target, version))
        destination = releases / target / asset.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, destination)
        log("  updates: %s" % destination.relative_to(updates_dir))

        json_path = updates_dir / ("osupdate_%s.json" % target)
        body = (
            "{\n"
            '"version": "%s",\n'
            '"download_url": "%s/%s/%s",\n'
            '"changelog": "%s"\n'
            "}\n"
        ) % (version, UPDATES_BASE_URL, target, asset.name, changelog)
        json_path.write_text(body)
        log("  updates: %s" % json_path.name)


def update_install_repo(install_dir, version, assets_dir):
    minor = ".".join(version.split(".")[:2])
    previous = current_minor(install_dir)
    index_path = install_dir / "index.html"
    index = index_path.read_text()

    for target in TARGETS:
        asset = find_asset(assets_dir, "MicroPythonOS_%s_%s.bin" % (target, version))
        destination = install_dir / "firmware_images" / target / asset.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, destination)
        log("  install: %s" % destination.relative_to(install_dir))

        manifest_path = (install_dir / "manifests" / target /
                         ("MicroPythonOS_%s_%s.x.json" % (target, minor)))
        previous_manifest = (install_dir / "manifests" / target /
                             ("MicroPythonOS_%s_%s.x.json" % (target, previous)))
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
        else:
            manifest = json.loads(previous_manifest.read_text())
        manifest["version"] = version
        for build in manifest["builds"]:
            for part in build["parts"]:
                part["path"] = "/firmware_images/%s/%s" % (target, asset.name)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        log("  install: %s" % manifest_path.relative_to(install_dir))

    if minor != previous:
        index = index.replace("MicroPythonOS_%s_%s.x.json" % ("esp32s3", previous),
                              "MicroPythonOS_%s_%s.x.json" % ("esp32s3", minor))
        index = index.replace("MicroPythonOS_esp32_%s.x.json" % previous,
                              "MicroPythonOS_esp32_%s.x.json" % minor)
        index = index.replace("MicroPythonOS_esp32p4_%s.x.json" % previous,
                              "MicroPythonOS_esp32p4_%s.x.json" % minor)

    marker = index.find(OLD_RELEASES_LABEL)
    if marker < 0:
        raise ReleaseError("index.html has no old-releases label")
    current_version = re.search(r"version (\d+\.\d+\.\d+)", index[:marker])
    if not current_version:
        raise ReleaseError("cannot find the current version in index.html")
    current_version = current_version.group(1)
    head, tail = index[:marker], index[marker:]
    head = head.replace("version %s" % current_version, "version %s" % version)

    if minor != previous and ("MicroPythonOS_esp32s3_%s.x.json" % previous) not in tail:
        block = (
            '\n\t\t\t\t<label><input type="radio" name="device" '
            'value="/manifests/esp32s3/MicroPythonOS_esp32s3_%s.x.json" onchange="updateManifest()">\n'
            "\t\t\t\t    <p>Unified build for all supported ESP32-S3 devices: "
            "version %s</p>\n"
            "\t\t\t\t</label>\n"
            '\t\t\t\t <label><input type="radio" name="device" '
            'value="/manifests/esp32/MicroPythonOS_esp32_%s.x.json" onchange="updateManifest()">\n'
            "\t\t\t\t    <p>Unified build for all supported ESP32 devices: "
            "version %s</p>\n"
            "\t\t\t\t</label>\n"
            '\t\t\t\t <label><input type="radio" name="device" '
            'value="/manifests/esp32p4/MicroPythonOS_esp32p4_%s.x.json" onchange="updateManifest()">\n'
            "\t\t\t\t    <p>Unified build for all supported ESP32-P4 devices: "
            "version %s</p>\n"
            "\t\t\t\t</label>\n"
        ) % (previous, current_version, previous, current_version,
             previous, current_version)
        block = block.rstrip("\n")
        label_end = tail.find("</div>", tail.find(OLD_RELEASES_LABEL)) + len("</div>")
        tail = tail[:label_end] + "\n" + block + tail[label_end:]

    index_path.write_text(head + tail)
    log("  install: index.html (%s -> %s, minor %s -> %s)"
        % (current_version, version, previous, minor))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version")
    parser.add_argument("--install-dir", default=os.environ.get(
        "MPOS_INSTALL_DIR", str(REPO_ROOT.parent / "install")))
    parser.add_argument("--updates-dir", default=os.environ.get(
        "MPOS_UPDATES_DIR", str(REPO_ROOT.parent / "updates")))
    parser.add_argument("--assets-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-only", action="store_true")
    group.add_argument("--updates-only", action="store_true")
    args = parser.parse_args()

    version = args.version
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseError("expected a version like 0.22.0, got %r" % version)

    if args.assets_dir is None:
        assets_dir = REPO_ROOT / "tmp" / ("release_%s" % version.replace(".", ""))
        log("Downloading %s release assets into %s" % (version, assets_dir))
        if not args.dry_run:
            download_assets(version, assets_dir)
    else:
        assets_dir = Path(args.assets_dir)
    log("Assets: %s" % assets_dir)

    for target in TARGETS:
        for suffix in (".bin", ".ota"):
            path = assets_dir / ("MicroPythonOS_%s_%s%s" % (target, version, suffix))
            if args.dry_run:
                continue
            if not path.is_file():
                raise ReleaseError("missing release asset: %s" % path)
    if not args.dry_run:
        verify_assets(assets_dir, version)

    updates_dir = Path(args.updates_dir)
    install_dir = Path(args.install_dir)
    if not args.install_only and not updates_dir.is_dir():
        raise ReleaseError("%s is not a checkout of the updates repo" % updates_dir)
    if not args.updates_only and not install_dir.is_dir():
        raise ReleaseError("%s is not a checkout of the install repo" % install_dir)

    if args.dry_run:
        log("Dry run: changelog for the JSON would be:")
        log("  " + json_changelog(version)[:200] + " ...")
        return 0

    if not args.updates_only:
        log("Updating %s" % install_dir)
        update_install_repo(install_dir, version, assets_dir)
    if not args.install_only:
        log("Updating %s" % updates_dir)
        update_updates_repo(updates_dir, version, assets_dir)

    if args.commit:
        if not args.updates_only:
            commit(install_dir, version)
        if not args.install_only:
            commit(updates_dir, version)
    if args.push:
        if not args.updates_only:
            run_git(install_dir, ["push"])
        if not args.install_only:
            run_git(updates_dir, ["push"])

    log("")
    log("Next: run ../upload_install.sh and ../upload_updates.sh from the parent")
    log("      folder (one level up), or check the results with")
    log("      curl -s https://updates.micropythonos.com/osupdate_esp32s3.json")
    log("      curl -s https://install.micropythonos.com/manifests/esp32s3/")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReleaseError as error:
        sys.stderr.write("release_metadata: %s\n" % error)
        sys.exit(1)
