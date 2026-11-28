import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "internal_filesystem/builtin/apps/com.micropythonos.appstore"


def streaming(get):
    async def download(url, chunk_callback=None, **kwargs):
        value = await get(url)
        if chunk_callback:
            await chunk_callback(value.encode() if isinstance(value, str) else value)
            return True
        return value

    return download


class EnvironmentMixin:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.before)
        self.prefs = {}

        class Prefs:
            def __init__(inner, name):
                pass

            def get_string(inner, key, default=None):
                return self.prefs.get(key, default)

            def put_string(inner, key, value):
                self.prefs[key] = value

        stat_patch = patch.object(
            os, "statvfs", return_value=(4096, 4096, 10000, 10000, 10000, 0, 0, 0, 0, 255), create=True
        )
        stat_patch.start()
        self.addCleanup(stat_patch.stop)
        self.cache_calls = []

        def purge(path):
            self.cache_calls.append(path)
            for name, mod in list(sys.modules.items()):
                file = (getattr(mod, "__file__", "") or "").replace("\\", "/")
                if file.startswith(path.rstrip("/") + "/"):
                    del sys.modules[name]

        self.manager = types.SimpleNamespace(
            _del_modules_from_dir=purge,
            refresh_apps=lambda: None,
            compare_versions=lambda a, b: tuple(map(int, a.split("."))) > tuple(map(int, b.split("."))),
            get=lambda name: None,
        )

        async def sleep_ms(ms):
            await asyncio.sleep(ms / 1000)

        mpos = types.ModuleType("mpos")
        mpos.AppManager = self.manager
        mpos.SharedPreferences = Prefs
        mpos.BuildInfo = types.SimpleNamespace(version=types.SimpleNamespace(release="0.21.2", api_level=0))
        mpos.ConnectivityManager = types.SimpleNamespace(is_online=lambda: True)
        mpos.DownloadManager = types.SimpleNamespace(download_url=None)
        mpos.TaskManager = types.SimpleNamespace(wait_for=asyncio.wait_for, sleep_ms=sleep_ms)
        self.mpos = mpos
        self.mods = patch.dict(sys.modules, {"mpos": mpos, "ujson": json})
        self.mods.start()
        self.addCleanup(self.mods.stop)
        self.modules = {}
        for name in ["store_source", "store_install"]:
            spec = importlib.util.spec_from_file_location(name, STORE / (name + ".py"))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            self.addCleanup(sys.modules.pop, name, None)
            spec.loader.exec_module(mod)
            self.modules[name] = mod
        self.source = self.modules["store_source"]
        self.install = self.modules["store_install"]

    def manifest(self, path, filters=None):
        path.mkdir(parents=True, exist_ok=True)
        (path / "main.py").write_text("class Demo: pass\n")
        data = {
            "fullname": "com.example.upgrade",
            "version": "1.0.0",
            "activities": [
                {
                    "entrypoint": "main.py",
                    "classname": "Demo",
                    "intent_filters": filters if filters is not None else [{"action": "main", "category": "launcher"}],
                }
            ],
        }
        (path / "MANIFEST.JSON").write_text(json.dumps(data))
        return data


class HostTests(EnvironmentMixin, unittest.TestCase):
    def test_missing_launcher_rejected(self):
        self.manifest(Path("stage"), [])
        with self.assertRaisesRegex(ValueError, "launcher"):
            self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_split_filters_do_not_make_launcher(self):
        self.manifest(Path("stage"), [{"action": "main"}, {"category": "launcher"}])
        with self.assertRaisesRegex(ValueError, "launcher"):
            self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_launcher_and_safe_entry_accepted(self):
        self.manifest(Path("stage"))
        self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_helper_cache_evicted_after_promotion(self):
        dest = Path("apps/com.example.upgrade")
        self.manifest(dest)
        stage = Path("stage/com.example.upgrade")
        self.manifest(stage)
        stale = types.ModuleType("upgrade_helper")
        stale.__file__ = "/apps/com.example.upgrade/helper.py"
        stale.MARKER = "v1"
        sys.modules["upgrade_helper"] = stale
        self.addCleanup(sys.modules.pop, "upgrade_helper", None)
        (stage / "helper.py").write_text('MARKER="v2"\n')
        Path("backup").mkdir()
        self.install.promote("stage/com.example.upgrade", str(dest), "backup/com.example.upgrade")
        self.assertNotIn("upgrade_helper", sys.modules)
        self.assertTrue((dest / "helper.py").exists())

    def test_failed_promotion_restores_old_app(self):
        dest = Path("apps/com.example.upgrade")
        self.manifest(dest)
        stage = Path("stage/com.example.upgrade")
        self.manifest(stage)
        Path("backup").mkdir()
        (dest / "saved").write_text("old")
        rename = os.rename

        def fail(a, b):
            if a == str(stage):
                raise OSError("promotion failed")
            return rename(a, b)

        with patch.object(self.install.os, "rename", side_effect=fail):
            with self.assertRaises(OSError):
                self.install.promote(str(stage), str(dest), "backup/com.example.upgrade")
        self.assertEqual((dest / "saved").read_text(), "old")

    def test_reject_outside_macosx(self):
        with zipfile.ZipFile("x.mpk", "w") as z:
            z.writestr("com.example.upgrade/", b"")
            z.writestr("__MACOSX/garbage", b"x")
        with self.assertRaises(ValueError):
            self.install.check_archive("x.mpk", "com.example.upgrade", 1000000)

    def test_missing_root_rejected(self):
        with zipfile.ZipFile("x.mpk", "w") as z:
            z.writestr("MANIFEST.JSON", b"{}")
        with self.assertRaises(ValueError):
            self.install.check_archive("x.mpk", "com.example.upgrade", 1000000)

    def test_default_source_preserves_badgehub(self):
        self.assertEqual(self.source.current_source(), "badgehub")

    def test_identity_slug_and_relative_icon_mapping(self):
        value = self.source.normalize(
            {
                "fullname": "com.example.upgrade",
                "slug": "com-example-upgrade",
                "name": "Upgrade",
                "category": "utilities",
                "icon_url": "/icon.png",
                "download_url": "/api/v1/apps/com-example-upgrade/download?revision=2",
                "version": "1.1.0",
                "revision": 2,
            },
            "upystore",
        )
        self.assertEqual(value["slug"], "com.example.upgrade")
        self.assertEqual(value["_store_slug"], "com-example-upgrade")
        self.assertEqual(value["icon_map"]["64x64"]["url"], "https://upystore.io/icon.png")

    def test_detail_selects_matching_revision_and_hash(self):
        async def get(url, **kwargs):
            return json.dumps(
                {
                    "app": {
                        "fullname": "com.example.upgrade",
                        "slug": "com-example-upgrade",
                        "version": "1.1.0",
                        "revision": 2,
                    },
                    "versions": [
                        {"revision": 1, "file_sha256": "1" * 64},
                        {
                            "revision": 2,
                            "file_sha256": "2" * 64,
                            "file_size_bytes": 100,
                            "download_url": "/api/v1/apps/com-example-upgrade/download?revision=2",
                        },
                    ],
                }
            ).encode()

        self.mpos.DownloadManager.download_url = streaming(get)
        value = asyncio.run(self.source.fetch_details("com.example.upgrade", "com-example-upgrade", "upystore"))
        self.assertEqual(value["file_sha256"], "2" * 64)
        self.assertEqual(value["revision"], 2)

    def test_background_updates_ignore_search_and_keep_revisions(self):
        self.prefs["store_source"] = "upystore"
        self.prefs["store_query"] = "calculator"
        requests = []

        async def get(url):
            requests.append(url)
            page = 1 if "page=1" in url else 2
            return json.dumps(
                {
                    "apps": [
                        {
                            "fullname": "com.test.app%d" % page,
                            "slug": "com-test-app%d" % page,
                            "version": "1.0.0",
                            "revision": 2,
                        }
                    ],
                    "pagination": {"total_pages": 2},
                }
            )

        self.mpos.DownloadManager.download_url = streaming(get)
        result = asyncio.run(self.source.fetch_updates())
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["revision"], 2)
        self.assertTrue(all("calculator" not in url for url in requests))

    def test_badgehub_background_updates_ignore_search(self):
        self.prefs.update(store_source="badgehub", store_query="calculator")

        async def get(url):
            return json.dumps([{"slug": "com.test.other", "name": "Other", "version": "2.0.0"}])

        self.mpos.DownloadManager.download_url = streaming(get)
        result = asyncio.run(self.source.fetch_updates())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["slug"], "com.test.other")

    def test_json_response_rejected_while_streaming_over_limit(self):
        async def download(url, chunk_callback=None):
            await chunk_callback(b"12345")
            await chunk_callback(b"67890")
            self.fail("Oversized response must stop collection")

        self.mpos.DownloadManager.download_url = download
        with self.assertRaisesRegex(ValueError, "oversized"):
            asyncio.run(self.source.json_get("https://upystore.io/test", limit=8))

    def test_concurrent_store_requests_are_serialized(self):
        active = 0
        peak = 0

        async def download(url):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return b"ok"

        self.mpos.DownloadManager.download_url = download

        async def run():
            return await asyncio.gather(
                self.source.request("https://upystore.io/a"), self.source.request("https://upystore.io/b")
            )

        self.assertEqual(asyncio.run(run()), [b"ok", b"ok"])
        self.assertEqual(peak, 1)
        self.assertEqual(self.source._REQUESTS, [])

    def test_cancelled_queued_request_releases_its_place(self):
        async def download(url):
            await asyncio.sleep(0.03)
            return b"ok"

        self.mpos.DownloadManager.download_url = download

        async def run():
            first = asyncio.create_task(self.source.request("https://upystore.io/a"))
            second = asyncio.create_task(self.source.request("https://upystore.io/b"))
            await asyncio.sleep(0.005)
            second.cancel()
            try:
                await second
            except asyncio.CancelledError:
                pass
            await first
            return await self.source.request("https://upystore.io/c")

        self.assertEqual(asyncio.run(run()), b"ok")
        self.assertEqual(self.source._REQUESTS, [])

    def test_empty_exception_has_actionable_type(self):
        self.assertEqual(self.source.error_text(TimeoutError()), "TimeoutError")

    def test_invalid_http_response_has_a_retryable_message(self):
        self.assertEqual(self.source.error_text(IndexError("list index out of range")), "Invalid response from store")

    def test_reject_cross_origin_download(self):
        with self.assertRaises(ValueError):
            self.source.absolute_url("https://evil.example/pkg.mpk")

    def test_checksum_failure(self):
        Path("x.mpk").write_bytes(b"PK00")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.install.verify_package("x.mpk", 4, "0" * 64)


class InstallationTests(EnvironmentMixin, unittest.TestCase):
    def prepare_archive(self, version="1.1.0", launcher=True):
        name = "com.example.upgrade"
        manifest = {
            "fullname": name,
            "name": "Upgrade",
            "version": version,
            "activities": [
                {
                    "entrypoint": "main.py",
                    "classname": "Demo",
                    "intent_filters": [{"action": "main", "category": "launcher"}] if launcher else [],
                }
            ],
        }
        import io

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr(name + "/", "")
            z.writestr(name + "/MANIFEST.JSON", json.dumps(manifest))
            z.writestr(name + "/main.py", "class Demo: pass\n")
            z.writestr(name + "/upgrade_helper.py", 'MARKER = "v2"\n')
        data = out.getvalue()

        async def details(*args):
            return {
                "fullname": name,
                "version": version,
                "revision": 2,
                "_store_source": "upystore",
                "_store_slug": "com-example-upgrade",
                "download_url": "https://upystore.io/api/v1/apps/com-example-upgrade/download?revision=2",
                "download_url_size": len(data),
                "file_sha256": hashlib.sha256(data).hexdigest(),
            }

        async def download(url, chunk_callback):
            for offset in range(0, len(data), 128):
                await chunk_callback(data[offset : offset + 128])
            return True

        def extract(archive, stage):
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    rel = name.split("/", 1)[1]
                    target = Path(stage) / rel
                    if name.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(z.read(name))
            os.remove(archive)

        self.install.fetch_details = details
        self.mpos.DownloadManager.download_url = download
        self.manager.install_mpk = extract
        return types.SimpleNamespace(fullname=name, _store_source="upystore", _store_slug="com-example-upgrade")

    def test_install_records_identity_and_receipt(self):
        app = self.prepare_archive()
        result = asyncio.run(self.install.install_package(app))
        self.assertEqual(result["version"], "1.1.0")
        self.assertEqual(self.install.read_receipt(app.fullname)["revision"], 2)
        self.assertTrue(Path("apps/com.example.upgrade/main.py").is_file())
        self.assertFalse(Path("cache/com.micropythonos.appstore/install/download.mpk").exists())

    def test_real_import_old_helper_then_upgrade_then_import_new(self):
        app = self.prepare_archive()
        dest = Path("apps/com.example.upgrade")
        self.manifest(dest)
        oldfile = dest / "upgrade_helper.py"
        oldfile.write_text('MARKER = "v1"\n')
        spec = importlib.util.spec_from_file_location("upgrade_helper", oldfile.as_posix())
        old = importlib.util.module_from_spec(spec)
        sys.modules["upgrade_helper"] = old
        self.addCleanup(sys.modules.pop, "upgrade_helper", None)
        spec.loader.exec_module(old)
        self.assertEqual(old.MARKER, "v1")
        asyncio.run(self.install.install_package(app))
        self.assertNotIn("upgrade_helper", sys.modules)
        spec = importlib.util.spec_from_file_location("upgrade_helper", oldfile.as_posix())
        new = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(new)
        self.assertEqual(new.MARKER, "v2")

    def test_no_launcher_preserves_old_and_cleans_stage(self):
        app = self.prepare_archive(launcher=False)
        dest = Path("apps/com.example.upgrade")
        self.manifest(dest)
        (dest / "saved").write_text("old")
        with self.assertRaisesRegex(ValueError, "launcher"):
            asyncio.run(self.install.install_package(app))
        self.assertEqual((dest / "saved").read_text(), "old")
        self.assertEqual(list(Path("cache/com.micropythonos.appstore/install/stage").iterdir()), [])

    def test_invalid_entry_syntax_rejected(self):
        self.manifest(Path("stage"))
        Path("stage/main.py").write_text("class Demo(:\n")
        with self.assertRaises(SyntaxError):
            self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_final_progress_failure_does_not_undo_success(self):
        app = self.prepare_archive()

        async def progress(percent):
            if percent == 100:
                raise ValueError("UI was closed")

        result = asyncio.run(self.install.install_package(app, progress))
        self.assertEqual(result["version"], "1.1.0")
        self.assertEqual(self.install.read_receipt(app.fullname)["version"], "1.1.0")

    def test_same_version_new_revision_update(self):
        self.manager.is_update_available = lambda *args: False
        self.install.write_receipt("com.example.upgrade", {"version": "1.0.0", "revision": 1, "source": "upystore"})
        self.assertTrue(self.install.update_available("com.example.upgrade", "1.0.0", 2, "upystore"))
        self.assertFalse(self.install.update_available("com.example.upgrade", "1.0.0", 1, "upystore"))
        self.assertFalse(self.install.update_available("com.example.upgrade", "1.0.0", 2, "badgehub"))

    def test_no_cross_source_background_update(self):
        self.manager.is_update_available = lambda *args: True
        self.install.write_receipt("com.example.upgrade", {"version": "1.0.0", "revision": 1, "source": "badgehub"})
        self.assertFalse(self.install.update_available("com.example.upgrade", "2.0.0", 2, "upystore"))

    def test_receipt_write_failure_rolls_back_and_releases_lock(self):
        app = self.prepare_archive()
        dest = Path("apps/com.example.upgrade")
        self.manifest(dest)
        (dest / "saved").write_text("old")
        with patch.object(self.install, "write_receipt", side_effect=OSError("disk write")):
            with self.assertRaises(OSError):
                asyncio.run(self.install.install_package(app))
        self.assertEqual((dest / "saved").read_text(), "old")
        self.assertFalse(self.install._INSTALLING)


if __name__ == "__main__":
    unittest.main()
