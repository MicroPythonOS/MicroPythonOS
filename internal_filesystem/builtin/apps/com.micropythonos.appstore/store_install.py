import gc
import hashlib
import json
import logging
import os
import shutil
import struct
import sys

from mpos import AppManager, BuildInfo, ConnectivityManager, TaskManager
from store_source import absolute_url, current_source, fetch_details, identity, request

logger = logging.getLogger(__name__)
MAX_PACKAGE_BYTES = 33554432
WORK_DIR = "cache/com.micropythonos.appstore/install"
RECEIPTS_DIR = "prefs/com.micropythonos.appstore/receipts"
LEGACY_RECEIPTS_DIR = "data/appstore/receipts"
_INSTALLING = False


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def mkdirs(path):
    current = "/" if path.startswith("/") else ""
    for part in path.split("/"):
        if not part:
            continue
        current = current.rstrip("/") + "/" + part if current else part
        if not exists(current):
            os.mkdir(current)


def remove_tree(path):
    if exists(path):
        if os.stat(path)[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)


def verify_package(path, expected_size, expected_sha):
    actual_size = os.stat(path)[6]
    if expected_size and actual_size != expected_size:
        raise ValueError("Package size mismatch")
    if actual_size < 4 or actual_size > MAX_PACKAGE_BYTES:
        raise ValueError("Package size is unsupported")
    sha = hashlib.sha256()
    with open(path, "rb") as source:
        if source.read(2) != b"PK":
            raise ValueError("Not an MPK ZIP package")
        source.seek(0)
        while True:
            chunk = source.read(4096)
            if not chunk:
                break
            sha.update(chunk)
    digest = "".join("%02x" % value for value in sha.digest())
    if not expected_sha or digest.lower() != expected_sha.lower():
        raise ValueError("Package SHA256 hash missing or mismatched")
    return digest


def check_archive(path, fullname, free_bytes):
    total = 0
    count = 0
    with open(path, "rb") as source:
        while True:
            header = source.read(30)
            if header[:4] in (b"PK\x01\x02", b"PK\x05\x06"):
                break
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise ValueError("Invalid MPK header")
            values = struct.unpack("<IHHHHHIIIHH", header)
            flags, method, compressed, expanded, name_size, extra_size = (
                values[2],
                values[3],
                values[7],
                values[8],
                values[9],
                values[10],
            )
            name = source.read(name_size).decode("utf-8")
            if count == 0 and name != fullname + "/":
                raise ValueError("MPK root does not match app identity")
            if not name.startswith(fullname + "/") or ".." in name.split("/") or "\\" in name:
                raise ValueError("Unsafe MPK path")
            if flags & 9 or method not in (0, 8):
                raise ValueError("Unsupported MPK compression or flags")
            count += 1
            total += expanded
            if count > 4096 or total > free_bytes - 65536:
                raise ValueError("Not enough free Flash or package too large")
            source.seek(extra_size + compressed, 1)
    if count == 0:
        raise ValueError("Empty MPK")
    return total


def validate_manifest(path, fullname, version):
    manifest_path = path + "/MANIFEST.JSON"
    if not exists(manifest_path):
        manifest_path = path + "/META-INF/MANIFEST.JSON"
    with open(manifest_path) as source:
        manifest = json.load(source)
    if manifest.get("fullname") != fullname or manifest.get("version") != version:
        raise ValueError("Installed manifest identity/version mismatch")
    activities = manifest.get("activities", [])
    if not activities:
        raise ValueError("No application Activity in package")
    for activity in activities + manifest.get("services", []):
        entry = activity.get("entrypoint", "")
        if entry.startswith("/") or ".." in entry.split("/") or "\\" in entry or not (entry.endswith(".py") or entry.endswith(".mpy")):
            raise ValueError("Invalid application entrypoint")
        base = entry[:-4] if entry.endswith(".mpy") else entry[:-3]
        source_path = path + "/" + base + ".py"
        compiled_path = path + "/" + base + ".mpy"
        if not activity.get("classname"):
            raise ValueError("Application entrypoint is missing")
        if exists(source_path):
            with open(source_path) as entry_file:
                compile(entry_file.read(), entry, "exec")
        elif exists(compiled_path):
            with open(compiled_path, "rb") as entry_file:
                header = entry_file.read(4)
            runtime_mpy = getattr(sys.implementation, "_mpy", None)
            if len(header) != 4 or header[0] != 77 or (runtime_mpy is not None and header[1] != runtime_mpy & 255):
                raise ValueError("Invalid or incompatible compiled entrypoint")
        else:
            raise ValueError("Application entrypoint is missing")
    launcher = any(
        any(f.get("action") == "main" and f.get("category") == "launcher" for f in activity.get("intent_filters", []))
        for activity in activities
    )
    if not launcher:
        raise ValueError("Missing main/launcher Activity")
    for activity in activities + manifest.get("services", []):
        classname = activity.get("classname", "")
        if (
            not classname
            or classname[0] not in "_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            or any(c not in "_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for c in classname)
        ):
            raise ValueError("Invalid Activity classname")
    return manifest


def clear_app_cache(destination):
    destination = destination.replace("\\", "/")
    AppManager._del_modules_from_dir(destination.lstrip("/"))
    AppManager._del_modules_from_dir("/" + destination.lstrip("/"))
    if not destination.startswith("/"):
        AppManager._del_modules_from_dir(os.getcwd().replace("\\", "/").rstrip("/") + "/" + destination)


def promote(stage, destination, backup):
    had_old = exists(destination)
    if exists(backup):
        raise RuntimeError("Previous install backup exists; recovery required")
    if had_old:
        os.rename(destination, backup)
    try:
        os.rename(stage, destination)
        clear_app_cache(destination)
        AppManager.refresh_apps()
    except Exception:
        remove_tree(destination)
        if had_old:
            os.rename(backup, destination)
        clear_app_cache(destination)
        AppManager.refresh_apps()
        raise
    return had_old


def read_receipt(fullname):
    filename = identity(fullname) + ".json"
    for directory in (RECEIPTS_DIR, LEGACY_RECEIPTS_DIR):
        try:
            with open(directory + "/" + filename) as f:
                value = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        if directory == LEGACY_RECEIPTS_DIR:
            try:
                write_receipt(fullname, value)
            except OSError as error:
                logger.warning("APPSTORE_RECEIPT_MIGRATION_PENDING %s %s", fullname, error)
        return value
    return None


def write_receipt(fullname, value):
    mkdirs(RECEIPTS_DIR)
    path = RECEIPTS_DIR + "/" + identity(fullname) + ".json"
    with open(path + ".tmp", "w") as f:
        json.dump(value, f)
    os.rename(path + ".tmp", path)


def forget_receipt(fullname):
    filename = identity(fullname) + ".json"
    for directory in (RECEIPTS_DIR, LEGACY_RECEIPTS_DIR):
        remove_tree(directory + "/" + filename)


def update_available(fullname, version, revision=None, source=None):
    receipt = read_receipt(fullname)
    if receipt and receipt.get("source") != (source or current_source()):
        return False
    if AppManager.is_update_available(fullname, version):
        return True
    return bool(
        receipt
        and receipt.get("source") == (source or current_source())
        and receipt.get("version") == version
        and isinstance(revision, int)
        and revision > receipt.get("revision", 0)
    )


async def extract_package(archive, destination, fullname, space_callback=None):
    try:
        from mpos import extent as extent_files
        from mpos.content.streaming_unzip import StreamingUnzip
    except ImportError:
        AppManager.install_mpk(archive, destination)
        return
    if not hasattr(StreamingUnzip, "feed_async"):
        AppManager.install_mpk(archive, destination)
        return
    extractor = StreamingUnzip(
        destination,
        expected_app_name=fullname,
        free_space_limit=lambda required: AppManager._check_free_space(".", required),
    )
    source = open(archive, "rb")

    async def reserve_space(length, align):
        nonlocal source
        position = source.tell()
        source.close()
        try:
            return await extent_files.open_writer(length, align, defrag_first=True, progress=space_callback)
        finally:
            source = open(archive, "rb")
            source.seek(position)

    try:
        while True:
            chunk = source.read(4096)
            if not chunk:
                break
            await extractor.feed_async(chunk, reserve_space)
            await TaskManager.sleep_ms(0)
        extractor.finish()
    finally:
        source.close()


async def install_package(app, progress_callback=None, space_callback=None):
    global _INSTALLING
    if _INSTALLING:
        raise RuntimeError("Another package install is running")
    _INSTALLING = True
    try:
        return await _install_package(app, progress_callback, space_callback)
    finally:
        _INSTALLING = False


async def _install_package(app, progress_callback, space_callback):
    fullname = identity(app.get("fullname") if isinstance(app, dict) else app.fullname)
    source = (
        app.get("_store_source", current_source())
        if isinstance(app, dict)
        else getattr(app, "_store_source", current_source())
    )
    if source not in ("upystore", "badgehub"):
        raise ValueError("Unknown store source")
    slug = app.get("_store_slug") if isinstance(app, dict) else getattr(app, "_store_slug", None)
    if not ConnectivityManager.is_online():
        raise RuntimeError("Offline: connect WiFi and retry")
    detail = await fetch_details(fullname, slug, source)
    version = detail.get("version")
    if not version:
        raise ValueError("Published app version unavailable")
    minimum = detail.get("min_os_version")
    if minimum and AppManager.compare_versions(minimum, BuildInfo.version.release):
        raise ValueError("Requires OS " + minimum)
    if (detail.get("min_api_level") or 0) > BuildInfo.version.api_level:
        raise ValueError("Requires a newer OS API")
    size = detail.get("download_url_size")
    digest = detail.get("file_sha256")
    if source == "upystore" and (
        not isinstance(size, int)
        or size < 4
        or size > MAX_PACKAGE_BYTES
        or not isinstance(digest, str)
        or len(digest) != 64
    ):
        raise ValueError("Published package size or SHA256 unavailable")
    url = absolute_url(detail["download_url"]) if source == "upystore" else detail["download_url"]
    work = WORK_DIR
    mkdirs("apps")
    mkdirs(work + "/stage")
    mkdirs(work + "/backup")
    stage = work + "/stage/" + fullname
    backup = work + "/backup/" + fullname
    destination = "apps/" + fullname
    archive = work + "/download.mpk"
    if exists(backup) or exists("data/appstore/install/backup/" + fullname):
        raise RuntimeError("Previous install backup exists; recovery required")
    remove_tree(stage)
    remove_tree(archive)
    received = 0
    previous_receipt = read_receipt(fullname)
    promoted = False
    had_old = False
    if __debug__: logger.debug("APPSTORE_PACKAGE_REQUEST %s", url)
    try:
        with open(archive, "wb") as output:

            async def consume(chunk):
                nonlocal received
                received += len(chunk)
                if received > (size or MAX_PACKAGE_BYTES):
                    raise ValueError("Package size mismatch")
                output.write(chunk)
                if progress_callback:
                    await progress_callback(min(95, received * 95 // size) if size else 0)

            ok = await request(url, timeout=120, chunk_callback=consume)
        if not ok:
            raise RuntimeError("Package download failed")
        actual_hash = verify_package(archive, size, digest) if source == "upystore" else None
        if source != "upystore" and size and os.stat(archive)[6] != size:
            raise ValueError("Package size mismatch")
        logger.info("APPSTORE_PACKAGE_CHECKED %s %s %s %s", fullname, source, os.stat(archive)[6], actual_hash)
        gc.collect()
        stats = os.statvfs(".")
        check_archive(archive, fullname, stats[0] * stats[4])
        await extract_package(archive, stage, fullname, space_callback)
        validate_manifest(stage, fullname, version)
        had_old = promote(stage, destination, backup)
        promoted = True
        receipt = {
            "fullname": fullname,
            "version": version,
            "revision": detail.get("revision") or 0,
            "source": source,
            "slug": detail.get("_store_slug"),
            "sha256": actual_hash,
        }
        write_receipt(fullname, receipt)
        promoted = False
        if had_old:
            try:
                remove_tree(backup)
            except Exception as error:
                logger.warning("APPSTORE_BACKUP_CLEANUP_PENDING %s %s", fullname, error)
        if progress_callback:
            try:
                await progress_callback(100)
            except Exception as error:
                logger.warning("APPSTORE_PROGRESS_UNAVAILABLE %s", error)
        logger.info("APPSTORE_INSTALL_SUCCESS %s", fullname)
        return receipt
    except Exception:
        if promoted:
            remove_tree(destination)
            if had_old:
                os.rename(backup, destination)
            if previous_receipt:
                write_receipt(fullname, previous_receipt)
            else:
                forget_receipt(fullname)
            clear_app_cache(destination)
            AppManager.refresh_apps()
        raise
    finally:
        for temporary in (archive, stage):
            try:
                remove_tree(temporary)
            except OSError as error:
                logger.warning("APPSTORE_TEMP_CLEANUP_PENDING %s %s", temporary, error)
        gc.collect()
