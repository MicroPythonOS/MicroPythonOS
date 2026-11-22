#!/usr/bin/env python3
"""Build the preloaded filesystem that ships inside MicroPythonOS images.

The same staging code feeds two targets:

  * the web build, which preloads ``apps`` and ``data`` into the browser
    filesystem and seeds them into the persistent /apps and /data stores on
    first boot (see web/shell.html);
  * the ESP32-family full images, which pack the same tree into a littlefs2e
    image (with the third_party/mklittlefs submodule; every ``*.xip`` becomes
    a contiguous extent the badge maps from flash) and merge it into the vfs
    partition of the flash image.

Usage:
    preload_fs.py stage --out DIR [--march xtensawin|rv32imc]
    preload_fs.py pack  --source DIR --partitions CSV --image IMG
    preload_fs.py merge --build-dir DIR --partitions CSV --image IMG
    preload_fs.py all   --build-dir DIR --partitions CSV --march xtensawin

``stage`` reads scripts/preload_apps.txt. Entries marked ``repo`` come from
internal_filesystem/apps/; entries marked ``badgehub`` are downloaded from
badgehub.eu and cached under tmp/preload_cache/, so a release always ships the
latest published version unless a version/hash is pinned in the list.
"""

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_LIST = REPO_ROOT / "scripts" / "preload_apps.txt"
STAGE_TARGETS = ("device", "web")
REPO_APPS_DIR = REPO_ROOT / "internal_filesystem" / "apps"
DATA_DIR = REPO_ROOT / "internal_filesystem_data"
COMPILE_SCRIPT = REPO_ROOT / "scripts" / "compile_dir.sh"
DEFAULT_CACHE_DIR = REPO_ROOT / "tmp" / "preload_cache"
DEFAULT_WORK_DIR = REPO_ROOT / "tmp" / "preload"
MKLITTLEFS = REPO_ROOT / "third_party" / "mklittlefs" / "mklittlefs"

BADGEHUB_API = "https://badgehub.eu/api/v3"
USER_AGENT = "MicroPythonOS-preload/1.0"

# Match the badge firmware image (badge_firmware_MicroPythonOS) so the same
# filesystem layout is used everywhere.
BLOCK_SIZE = 4096
READ_SIZE = 256
PROG_SIZE = 256
CACHE_SIZE = 1024

# littlefs2e: a native core is packed as a contiguous extent so it can be
# mapped from flash without a first-launch conversion.
EXTENT_SUFFIX = ".xip"

JUNK_DIRS = {"__pycache__"}
JUNK_FILES = {".DS_Store"}
JUNK_SUFFIXES = {".pyc", ".bak", "~"}


class PreloadError(Exception):
    pass


def _log(message):
    print(message, flush=True)


def _format_size(num_bytes):
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB"):
        if value < 1024 or unit == "MiB":
            return "%.1f %s" % (value, unit)
        value /= 1024
    return "%.1f MiB" % value


def _http_json(url):
    request = urllib.request.Request(
        url, headers={"accept": "application/json", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_download(url, destination):
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url, headers={"accept": "*/*", "User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response, open(temporary, "wb") as output:
        shutil.copyfileobj(response, output)
    temporary.replace(destination)


def parse_apps(apps_file):
    entries = []
    for line_number, raw_line in enumerate(apps_file.read_text().splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise PreloadError("%s:%d: expected '<repo|badgehub> <fullname>'" % (apps_file, line_number))
        source, fullname = parts[0], parts[1]
        if source not in ("repo", "badgehub"):
            raise PreloadError("%s:%d: unknown source %r" % (apps_file, line_number, source))
        options = {}
        for item in parts[2:]:
            if "=" not in item:
                raise PreloadError("%s:%d: expected key=value, got %r" % (apps_file, line_number, item))
            key, value = item.split("=", 1)
            options[key] = value
        target = options.get("target")
        if target is not None and target not in STAGE_TARGETS:
            raise PreloadError(
                "%s:%d: target must be one of %s, got %r"
                % (apps_file, line_number, ", ".join(STAGE_TARGETS), target))
        entries.append({"source": source, "fullname": fullname, "options": options})
    if not entries:
        raise PreloadError("%s does not list any apps" % apps_file)
    return entries


def _cached_mpk(fullname, version, cache_dir):
    if version:
        candidate = cache_dir / ("%s_%s.mpk" % (fullname, version))
        return candidate if candidate.is_file() else None
    cached = sorted(
        cache_dir.glob("%s_*.mpk" % fullname),
        key=lambda path: path.stat().st_mtime,
    )
    return cached[-1] if cached else None


def _verify_hash(path, fullname, version, options):
    expected_hash = options.get("sha256")
    if expected_hash:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.lower() != expected_hash.lower():
            raise PreloadError(
                "%s version %s: sha256 mismatch (expected %s, got %s)"
                % (fullname, version, expected_hash, digest)
            )


def _badgehub_mpk(fullname, options, cache_dir, offline):
    cache_dir.mkdir(parents=True, exist_ok=True)
    if offline:
        cached = _cached_mpk(fullname, options.get("version"), cache_dir)
        if cached is None:
            raise PreloadError(
                "%s is not cached under %s and --offline was given" % (fullname, cache_dir)
            )
        version = cached.stem[len(fullname) + 1:]
        _verify_hash(cached, fullname, version, options)
        return cached, version

    try:
        project = _http_json("%s/projects/%s" % (BADGEHUB_API, fullname))
    except Exception as error:
        raise PreloadError(
            "could not reach BadgeHub for %s (%s); check the network or build with --offline"
            % (fullname, error)
        )
    version_info = project.get("version") or {}
    app_metadata = version_info.get("app_metadata") or {}
    version = str(app_metadata.get("version") or "").strip()
    if not version:
        raise PreloadError("BadgeHub project %s has no published version" % fullname)

    files = version_info.get("files") or []
    mpks = [item for item in files if str(item.get("ext", "")).lower() == ".mpk"]
    if not mpks:
        raise PreloadError("BadgeHub project %s version %s has no .mpk file" % (fullname, version))

    expected_version = options.get("version")
    if expected_version and expected_version != version:
        raise PreloadError(
            "BadgeHub project %s is at version %s, but preload_apps.txt pins %s"
            % (fullname, version, expected_version)
        )

    chosen = None
    marker = "_%s.mpk" % version
    for item in mpks:
        candidates = (str(item.get("name", "")), str(item.get("full_path", "")))
        if any(name.endswith(marker) for name in candidates):
            chosen = item
            break
    if chosen is None:
        chosen = mpks[0]

    url = chosen.get("url")
    if not url:
        raise PreloadError("BadgeHub project %s has no download URL for its .mpk" % fullname)

    destination = cache_dir / ("%s_%s.mpk" % (fullname, version))
    if not destination.exists():
        _log("  downloading %s %s from BadgeHub..." % (fullname, version))
        try:
            _http_download(url, destination)
        except Exception as error:
            raise PreloadError("download of %s failed: %s" % (url, error))

    _verify_hash(destination, fullname, version, options)
    return destination, version
    return destination, version
    return destination, version


def _safe_extract(zip_path, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise PreloadError("%s contains an unsafe path: %r" % (zip_path, info.filename))
            target = (destination / member).resolve()
            if destination not in target.parents and target != destination:
                raise PreloadError("%s escapes the extraction directory" % zip_path)
        archive.extractall(destination)


def _unpack_mpk(mpk_path, fullname, destination):
    staging = destination.parent / (destination.name + ".unpack")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    _safe_extract(mpk_path, staging)

    root = staging / fullname
    if root.is_dir():
        source = root
    else:
        source = staging
    shutil.copytree(source, destination)
    shutil.rmtree(staging, ignore_errors=True)


def _strip_junk(directory):
    for path in list(directory.rglob("*")):
        if path.is_dir() and path.name in JUNK_DIRS:
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and (path.name in JUNK_FILES or path.suffix in JUNK_SUFFIXES or path.name.endswith("~")):
            path.unlink(missing_ok=True)


def _stage_apps(apps_file, repo_apps_dir, cache_dir, offline, options, destination):
    entries = parse_apps(apps_file)
    raw_dir = destination.parent / (destination.name + ".raw")
    shutil.rmtree(raw_dir, ignore_errors=True)
    raw_dir.mkdir(parents=True)

    for entry in entries:
        fullname = entry["fullname"]
        wanted = entry["options"].get("target")
        if wanted is not None and wanted != options["target"]:
            _log("  skipping %s (target %s)" % (fullname, wanted))
            continue
        target = raw_dir / fullname
        if entry["source"] == "repo":
            source = repo_apps_dir / fullname
            if not source.is_dir():
                raise PreloadError(
                    "%s: %s is neither a directory in %s nor a BadgeHub entry; "
                    "fix the list or check out the app" % (apps_file, fullname, repo_apps_dir)
                )
            shutil.copytree(source.resolve(), target)
            _log("  staged %s from the repository" % fullname)
        else:
            mpk_path, version = _badgehub_mpk(fullname, entry["options"], cache_dir, offline)
            _unpack_mpk(mpk_path, fullname, target)
            _log("  staged %s %s from BadgeHub" % (fullname, version))
        if not (target / "MANIFEST.JSON").is_file():
            raise PreloadError("%s: staged app has no MANIFEST.JSON" % fullname)

    shutil.rmtree(destination, ignore_errors=True)
    march = options.get("march")
    if march:
        subprocess.run(
            [str(COMPILE_SCRIPT), "-march", march, str(raw_dir), str(destination)],
            check=True,
            cwd=str(REPO_ROOT),
        )
    else:
        shutil.copytree(raw_dir, destination)
        _strip_junk(destination)
    shutil.rmtree(raw_dir, ignore_errors=True)


def stage(out_dir, apps_file=APPS_LIST, repo_apps_dir=REPO_APPS_DIR, data_dir=DATA_DIR,
          cache_dir=DEFAULT_CACHE_DIR, offline=False, march=None, target="device"):
    out_dir = Path(out_dir)
    if out_dir.resolve() in (Path("/"), REPO_ROOT):
        raise PreloadError("refusing to stage into %s" % out_dir)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    _log("Staging preloaded apps into %s ..." % out_dir)
    _stage_apps(
        Path(apps_file), Path(repo_apps_dir), Path(cache_dir), offline,
        {"march": march, "target": target}, out_dir / "apps",
    )

    if not Path(data_dir).is_dir():
        raise PreloadError("sample data directory not found: %s" % data_dir)
    shutil.copytree(Path(data_dir), out_dir / "data")
    _log("  staged sample data from %s" % data_dir)
    _log("Staged tree is %s" % _format_size(_tree_size(out_dir)))
    return out_dir


def _tree_size(directory):
    return sum(path.stat().st_size for path in Path(directory).rglob("*") if path.is_file())


def _partition_row(partitions_csv, name):
    for raw_line in Path(partitions_csv).read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 5:
            continue
        if fields[0] == name:
            return {"name": fields[0], "type": fields[1], "subtype": fields[2],
                    "offset": int(fields[3], 0), "size": int(fields[4], 0)}
    raise PreloadError("%s has no %r partition" % (partitions_csv, name))


def _app_partition(partitions_csv):
    for raw_line in Path(partitions_csv).read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 5 or fields[1] != "app":
            continue
        if fields[2] in ("ota_0", "factory"):
            return int(fields[3], 0)
    raise PreloadError("%s has no ota_0/factory app partition" % partitions_csv)


def _find_mklittlefs(explicit=None):
    for candidate in (explicit, os.environ.get("MPOS_MKLITTLEFS"), MKLITTLEFS):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise PreloadError(
        "mklittlefs is not built; run scripts/build_mklittlefs.sh "
        "or pass --mklittlefs")


def pack(source_dir, partitions_csv, image_path, mklittlefs=None):
    """Pack the staged tree into a littlefs2e image.

    Files ending in ``.xip`` are written as extents: one contiguous, 64 KiB
    aligned run that the device maps straight out of flash. A native core then
    needs no defragmentation or conversion on first launch.
    """
    source_dir = Path(source_dir)
    vfs = _partition_row(partitions_csv, "vfs")
    if vfs["size"] % BLOCK_SIZE:
        raise PreloadError("vfs size 0x%X is not a multiple of %d" % (vfs["size"], BLOCK_SIZE))
    tool = _find_mklittlefs(mklittlefs)
    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.unlink(missing_ok=True)

    extents = sorted(path.relative_to(source_dir) for path in source_dir.rglob("*" + EXTENT_SUFFIX))
    command = [
        str(tool),
        "-b", str(BLOCK_SIZE),
        "-p", str(PROG_SIZE),
        "-r", str(READ_SIZE),
        "-m", str(CACHE_SIZE),
        "-N",
        "-s", str(vfs["size"]),
        "-c", str(source_dir),
    ]
    for extent in extents:
        command.extend(["-x", str(extent)])
    command.append(str(image_path))

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "full" in detail.lower():
            raise PreloadError(
                "preloaded tree (%s) does not fit in the %s vfs partition"
                % (_format_size(_tree_size(source_dir)), _format_size(vfs["size"]))
            )
        raise PreloadError("mklittlefs failed: %s" % (detail or "exit %d" % result.returncode))

    written = image_path.stat().st_size
    if written != vfs["size"]:
        raise PreloadError(
            "mklittlefs wrote %d bytes, expected the %s vfs partition"
            % (written, _format_size(vfs["size"])))
    _log("Packed %s into %s (vfs at 0x%X, %s%s)"
         % (_format_size(_tree_size(source_dir)), image_path.name, vfs["offset"],
            _format_size(vfs["size"]),
            ", %d extent(s)" % len(extents) if extents else ""))
    return vfs


def _find_idf_python():
    candidates = sorted(glob.glob(os.path.expanduser("~/.espressif/python_env/*/bin/python")))
    if candidates:
        return candidates[-1]
    return sys.executable


def _firmware_output(build_dir, flash_size):
    name = build_dir.name
    if not name.startswith("build-"):
        raise PreloadError("unexpected ESP-IDF build directory name: %s" % build_dir)
    board = name[len("build-"):]
    size = flash_size.replace("MB", "").replace("mb", "")
    build_root = REPO_ROOT / "lvgl_micropython" / "build"
    candidates = sorted(
        build_root.glob("lvgl_micropy_%s-%s*.bin" % (board, size)),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise PreloadError("could not find the merged firmware image in %s" % build_root)
    return candidates[-1]


def merge(build_dir, partitions_csv, image_path):
    build_dir = Path(build_dir)
    flasher_args = json.loads((build_dir / "flasher_args.json").read_text())
    bootloader = build_dir / flasher_args["bootloader"]["file"]
    bootloader_offset = flasher_args["bootloader"]["offset"]
    partition_table_offset = flasher_args["partition-table"]["offset"]
    app = build_dir / flasher_args["app"]["file"]
    settings = flasher_args["flash_settings"]
    chip = flasher_args["extra_esptool_args"]["chip"]

    vfs = _partition_row(partitions_csv, "vfs")
    app_offset = _app_partition(partitions_csv)

    image_path = Path(image_path)
    if image_path.stat().st_size != vfs["size"]:
        raise PreloadError(
            "%s is %d bytes, expected the full vfs size %d" % (image_path, image_path.stat().st_size, vfs["size"])
        )

    partition_table_tool = (
        REPO_ROOT / "lvgl_micropython" / "lib" / "esp-idf" / "components" / "partition_table" / "gen_esp32part.py"
    )
    if not partition_table_tool.is_file():
        raise PreloadError("gen_esp32part.py not found at %s" % partition_table_tool)
    partition_table_bin = build_dir / "preload-partition-table.bin"
    subprocess.run(
        [sys.executable, str(partition_table_tool), "--flash-size", settings["flash_size"],
         str(partitions_csv), str(partition_table_bin)],
        check=True,
    )

    output = _firmware_output(build_dir, settings["flash_size"])
    esptool_python = _find_idf_python()
    command = [
        esptool_python, "-m", "esptool", "--chip", chip, "merge_bin", "-o", str(output),
        "--flash_mode", settings["flash_mode"], "--flash_freq", settings["flash_freq"],
        "--flash_size", settings["flash_size"],
        bootloader_offset, str(bootloader),
        partition_table_offset, str(partition_table_bin),
        hex(app_offset), str(app),
        hex(vfs["offset"]), str(image_path),
    ]
    _log("Merging %s with the partition table and preloaded filesystem..." % output.name)
    subprocess.run(command, check=True)
    expected = vfs["offset"] + vfs["size"]
    actual = output.stat().st_size
    if actual != expected:
        raise PreloadError(
            "merged image is %d bytes, expected %d (vfs end); refusing to ship it" % (actual, expected)
        )
    _log("Merged image: %s (%s)" % (output, _format_size(actual)))
    return output


def all_command(args):
    work_dir = Path(args.work_dir)
    stage_dir = work_dir / "staged"
    image_path = work_dir / "preload.img"
    stage(
        stage_dir,
        apps_file=args.apps_file,
        repo_apps_dir=args.repo_apps_dir,
        data_dir=args.data_dir,
        cache_dir=args.cache_dir,
        offline=args.offline,
        march=args.march,
        target=args.target,
    )
    pack(stage_dir, args.partitions, image_path, mklittlefs=args.mklittlefs)
    return merge(args.build_dir, args.partitions, image_path)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--apps-file", default=str(APPS_LIST))
    common.add_argument("--repo-apps-dir", default=str(REPO_APPS_DIR))
    common.add_argument("--data-dir", default=str(DATA_DIR))
    common.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    common.add_argument("--offline", action="store_true",
                        help="use the BadgeHub cache; never download")
    common.add_argument("--target", choices=STAGE_TARGETS, default="device",
                        help="stage only apps for this target (default: device)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    stage_parser = subparsers.add_parser("stage", parents=[common], help="assemble apps/ and data/")
    stage_parser.add_argument("--out", required=True)
    stage_parser.add_argument("--march", default=None,
                              help="precompile apps for this mpy-cross arch (e.g. xtensawin)")

    pack_parser = subparsers.add_parser("pack", help="pack a staged tree into a littlefs2 image")
    pack_parser.add_argument("--source", required=True)
    pack_parser.add_argument("--partitions", required=True)
    pack_parser.add_argument("--image", required=True)
    pack_parser.add_argument("--mklittlefs", default=None,
                             help="mklittlefs binary (default: third_party/mklittlefs)")

    merge_parser = subparsers.add_parser("merge", help="merge a filesystem image into the firmware")
    merge_parser.add_argument("--build-dir", required=True)
    merge_parser.add_argument("--partitions", required=True)
    merge_parser.add_argument("--image", required=True)

    all_parser = subparsers.add_parser("all", parents=[common], help="stage, pack and merge")
    all_parser.add_argument("--build-dir", required=True)
    all_parser.add_argument("--partitions", required=True)
    all_parser.add_argument("--march", default=None)
    all_parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    all_parser.add_argument("--mklittlefs", default=None,
                            help="mklittlefs binary (default: third_party/mklittlefs)")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            stage(args.out, apps_file=args.apps_file, repo_apps_dir=args.repo_apps_dir,
                  data_dir=args.data_dir, cache_dir=args.cache_dir, offline=args.offline,
                  march=args.march, target=args.target)
        elif args.command == "pack":
            pack(args.source, args.partitions, args.image, mklittlefs=args.mklittlefs)
        elif args.command == "merge":
            merge(args.build_dir, args.partitions, args.image)
        else:
            all_command(args)
    except PreloadError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
