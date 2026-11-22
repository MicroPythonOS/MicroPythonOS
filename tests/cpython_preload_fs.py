#!/usr/bin/env python3
"""Tests for scripts/preload_fs.py (host-side, not run by test_runner.py).

Run with:
    python3 tests/cpython_preload_fs.py

The image checks need mklittlefs built (scripts/build_mklittlefs.sh) and, for
the read-back assertions, littlefs-python:
    python3 -m pip install littlefs-python==0.19.0
"""

import hashlib
import importlib.util
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("preload_fs", REPO_ROOT / "scripts" / "preload_fs.py")
preload_fs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preload_fs)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class ParseAppsTest(unittest.TestCase):
    def test_comments_blank_lines_and_options(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps.txt"
            _write(
                apps,
                "\n".join(
                    [
                        "# comment",
                        "",
                        "repo com.example.one",
                        "badgehub com.example.two",
                        "badgehub com.example.three version=1.2.3 sha256=abcd",
                    ]
                ),
            )
            entries = preload_fs.parse_apps(apps)
            self.assertEqual([entry["fullname"] for entry in entries],
                             ["com.example.one", "com.example.two", "com.example.three"])
            self.assertEqual(entries[2]["options"], {"version": "1.2.3", "sha256": "abcd"})

    def test_target_option_is_parsed_and_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps.txt"
            _write(apps, "repo com.example.one target=device\n")
            entries = preload_fs.parse_apps(apps)
            self.assertEqual(entries[0]["options"], {"target": "device"})
            _write(apps, "repo com.example.one target=watch\n")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.parse_apps(apps)

    def test_unknown_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps.txt"
            _write(apps, "github com.example.one\n")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.parse_apps(apps)


class BadgeHubCacheTest(unittest.TestCase):
    def test_offline_uses_cache_and_verifies_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            payload = b"mpk-bytes"
            cached = cache / "com.example.app_1.2.3.mpk"
            cached.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            path, version = preload_fs._badgehub_mpk(
                "com.example.app", {"sha256": digest}, cache, offline=True
            )
            self.assertEqual(path, cached)
            self.assertEqual(version, "1.2.3")

    def test_offline_without_cache_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._badgehub_mpk("com.example.app", {}, Path(temp), offline=True)

    def test_hash_mismatch_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            (cache / "com.example.app_1.2.3.mpk").write_bytes(b"mpk-bytes")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._badgehub_mpk(
                    "com.example.app", {"sha256": "0" * 64}, cache, offline=True
                )


class SafeExtractTest(unittest.TestCase):
    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.mpk"
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("../escape.txt", "nope")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._safe_extract(archive, Path(temp) / "out")

    def test_mpk_top_level_directory_is_stripped(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "app.mpk"
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("com.example.app/MANIFEST.JSON", '{"name": "App"}')
                zip_file.writestr("com.example.app/assets/main.py", "print('hi')\n")
            destination = Path(temp) / "apps" / "com.example.app"
            preload_fs._unpack_mpk(archive, "com.example.app", destination)
            self.assertTrue((destination / "MANIFEST.JSON").is_file())
            self.assertTrue((destination / "assets" / "main.py").is_file())
            self.assertFalse((destination / "com.example.app").exists())


class StageTest(unittest.TestCase):
    def _fixture(self, root):
        repo_apps = root / "apps"
        _write(repo_apps / "com.example.app" / "MANIFEST.JSON", '{"name": "App"}')
        _write(repo_apps / "com.example.app" / "main.py", "print('hi')\n")
        data_dir = root / "data"
        _write(data_dir / "images" / "sample.txt", "sample")
        apps_file = root / "apps.txt"
        _write(apps_file, "repo com.example.app\n")
        return repo_apps, data_dir, apps_file

    def test_stage_copies_apps_and_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_apps, data_dir, apps_file = self._fixture(root)
            out = root / "out"
            preload_fs.stage(out, apps_file=apps_file, repo_apps_dir=repo_apps, data_dir=data_dir)
            self.assertTrue((out / "apps" / "com.example.app" / "MANIFEST.JSON").is_file())
            self.assertTrue((out / "apps" / "com.example.app" / "main.py").is_file())
            self.assertTrue((out / "data" / "images" / "sample.txt").is_file())

    def test_stage_filters_by_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_apps, data_dir, apps_file = self._fixture(root)
            for name in ("com.example.device", "com.example.web"):
                _write(repo_apps / name / "MANIFEST.JSON", '{"name": "App"}')
                _write(repo_apps / name / "main.py", "print('hi')\n")
            _write(
                apps_file,
                "repo com.example.device target=device\n"
                "repo com.example.web target=web\n"
                "repo com.example.both\n",
            )
            _write(repo_apps / "com.example.both" / "MANIFEST.JSON", '{"name": "App"}')
            device_out = root / "device"
            web_out = root / "web"
            preload_fs.stage(device_out, apps_file=apps_file, repo_apps_dir=repo_apps,
                             data_dir=data_dir, target="device")
            preload_fs.stage(web_out, apps_file=apps_file, repo_apps_dir=repo_apps,
                             data_dir=data_dir, target="web")
            self.assertEqual(sorted(os.listdir(device_out / "apps")),
                             ["com.example.both", "com.example.device"])
            self.assertEqual(sorted(os.listdir(web_out / "apps")),
                             ["com.example.both", "com.example.web"])

    def test_missing_repo_app_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_apps, data_dir, _ = self._fixture(root)
            apps_file = root / "apps.txt"
            _write(apps_file, "repo com.example.missing\n")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.stage(root / "out", apps_file=apps_file,
                                 repo_apps_dir=repo_apps, data_dir=data_dir)


class PackTest(unittest.TestCase):
    def setUp(self):
        try:
            self.tool = preload_fs._find_mklittlefs()
        except preload_fs.PreloadError:
            self.skipTest("mklittlefs is not built; run scripts/build_mklittlefs.sh")

    def test_vfs_row(self):
        row = preload_fs._partition_row(REPO_ROOT / "partitions" / "esp32s3_16mb_badge.csv", "vfs")
        self.assertEqual(row["offset"], 0x900000)
        self.assertEqual(row["size"], 0x700000)

    def test_image_round_trip_and_padding(self):
        try:
            import littlefs
        except ImportError:
            self.skipTest("littlefs-python is not installed")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            _write(source / "apps" / "com.example.app" / "MANIFEST.JSON", '{"name": "App"}')
            _write(source / "data" / "hello.txt", "hello")
            partitions = root / "partitions.csv"
            _write(
                partitions,
                "# Name, Type, SubType, Offset, Size, Flags\n"
                "nvs,data,nvs,0x9000,0x6000,\n"
                "factory,app,factory,0x10000,0x20000,\n"
                "vfs,data,fat,0x30000,0x10000,\n",
            )
            image = root / "fs.img"
            vfs = preload_fs.pack(source, partitions, image)
            self.assertEqual(vfs["offset"], 0x30000)
            self.assertEqual(image.stat().st_size, 0x10000)

            fs = littlefs.LittleFS(
                context=littlefs.UserContextFile(str(image)),
                block_size=preload_fs.BLOCK_SIZE,
                block_count=0x10000 // preload_fs.BLOCK_SIZE,
                read_size=preload_fs.READ_SIZE,
                prog_size=preload_fs.PROG_SIZE,
                cache_size=preload_fs.CACHE_SIZE,
            )
            try:
                with fs.open("/data/hello.txt") as handle:
                    self.assertEqual(handle.read(), "hello")
            finally:
                fs.unmount()

    def test_too_large_tree_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "big.bin").write_bytes(os.urandom(0x20000))
            partitions = root / "partitions.csv"
            _write(
                partitions,
                "factory,app,factory,0x10000,0x10000,\n"
                "vfs,data,fat,0x20000,0x10000,\n",
            )
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.pack(source, partitions, root / "fs.img")


class ExtentPackTest(unittest.TestCase):
    def setUp(self):
        try:
            self.tool = preload_fs._find_mklittlefs()
        except preload_fs.PreloadError:
            self.skipTest("mklittlefs is not built; run scripts/build_mklittlefs.sh")

    def test_native_core_is_packed_as_extent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            payload = bytes((index * 7 + 3) & 0xFF for index in range(20000))
            app = source / "apps" / "com.example.app"
            app.mkdir(parents=True)
            (app / "engine.xip").write_bytes(payload)
            _write(app / "main.py", "print('hi')\n")
            partitions = root / "partitions.csv"
            # 64 blocks, so the default 16-block extent alignment has room.
            _write(
                partitions,
                "factory,app,factory,0x10000,0x10000,\n"
                "vfs,data,fat,0x20000,0x40000,\n",
            )
            image = root / "fs.img"
            preload_fs.pack(source, partitions, image)

            # The packer writes the payload into one contiguous run, and its
            # own reader (littlefs2e) returns it intact.
            unpacked = root / "unpacked"
            subprocess.run(
                [str(self.tool), "-u", str(unpacked), str(image)],
                check=True, capture_output=True,
            )
            self.assertEqual((unpacked / "apps" / "com.example.app" / "engine.xip").read_bytes(),
                             payload)

            # A stock littlefs cannot see an extent: it mounts the image and
            # reads the inode as empty, which is what makes the file an extent
            # rather than ordinary CTZ data.
            try:
                import littlefs
            except ImportError:
                return
            fs = littlefs.LittleFS(
                context=littlefs.UserContextFile(str(image)),
                block_size=preload_fs.BLOCK_SIZE,
                block_count=0x40000 // preload_fs.BLOCK_SIZE,
                read_size=preload_fs.READ_SIZE,
                prog_size=preload_fs.PROG_SIZE,
                cache_size=preload_fs.CACHE_SIZE,
            )
            try:
                self.assertEqual(fs.stat("/apps/com.example.app/engine.xip").size, 0)
            finally:
                fs.unmount()


if __name__ == "__main__":
    unittest.main()
