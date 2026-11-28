import asyncio
import json
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import cpython_appstore_upystore as previous


class ReviewTests(previous.EnvironmentMixin, unittest.TestCase):
    def prepare_archive(self, **kwargs):
        return previous.InstallationTests.prepare_archive(self, **kwargs)

    def test_default_preserves_official_badgehub(self):
        self.assertEqual(self.source.current_source(), "badgehub")

    def test_invalid_saved_source_falls_back_to_official_default(self):
        self.prefs["store_source"] = "removed-provider"
        self.assertEqual(self.source.current_source(), "badgehub")

    def test_explicit_upystore_choice_is_preserved(self):
        self.prefs["store_source"] = "upystore"
        self.assertEqual(self.source.current_source(), "upystore")

    def test_builtin_manifest_uses_categories_list(self):
        manifest = json.loads((previous.STORE / "MANIFEST.JSON").read_text())
        self.assertNotIn("category", manifest)
        self.assertEqual(manifest["categories"], ["Appstore"])

    def test_installer_uses_app_cache_and_preferences(self):
        app = self.prepare_archive()
        asyncio.run(self.install.install_package(app))
        base = Path("cache/com.micropythonos.appstore/install")
        self.assertEqual(list((base / "stage").iterdir()), [])
        self.assertEqual(list((base / "backup").iterdir()), [])
        self.assertTrue(Path("prefs/com.micropythonos.appstore/receipts/" + app.fullname + ".json").is_file())
        self.assertFalse(Path("data/appstore").exists())

    def test_legacy_receipt_migrates_without_losing_revision(self):
        directory = Path("data/appstore/receipts")
        directory.mkdir(parents=True)
        value = {"version": "1.0.0", "revision": 3, "source": "upystore"}
        (directory / "com.example.upgrade.json").write_text(json.dumps(value))
        self.assertEqual(self.install.read_receipt("com.example.upgrade"), value)
        self.assertTrue(Path("prefs/com.micropythonos.appstore/receipts/com.example.upgrade.json").is_file())
        self.manager.is_update_available = lambda *args: False
        self.assertTrue(self.install.update_available("com.example.upgrade", "1.0.0", 4, "upystore"))

    def test_forgetting_receipt_cannot_resurrect_legacy_copy(self):
        directory = Path("data/appstore/receipts")
        directory.mkdir(parents=True)
        (directory / "com.example.upgrade.json").write_text('{"revision": 1, "source": "upystore"}')
        self.install.read_receipt("com.example.upgrade")
        self.install.forget_receipt("com.example.upgrade")
        self.assertIsNone(self.install.read_receipt("com.example.upgrade"))

    def test_legacy_backup_requires_recovery_before_new_install(self):
        app = self.prepare_archive()
        backup = Path("data/appstore/install/backup") / app.fullname
        backup.mkdir(parents=True)
        (backup / "saved").write_text("old")
        with self.assertRaisesRegex(RuntimeError, "recovery"):
            asyncio.run(self.install.install_package(app))
        self.assertEqual((backup / "saved").read_text(), "old")

    def test_compiled_entrypoint_remains_supported(self):
        self.manifest(Path("stage"))
        Path("stage/main.py").unlink()
        Path("stage/main.mpy").write_bytes(b"M\x06\x00\x1f")
        value = self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")
        self.assertEqual(value["activities"][0]["entrypoint"], "main.py")

    def test_explicit_mpy_entrypoint_is_supported(self):
        self.manifest(Path("stage"))
        manifest = json.loads(Path("stage/MANIFEST.JSON").read_text())
        manifest["activities"][0]["entrypoint"] = "main.mpy"
        Path("stage/MANIFEST.JSON").write_text(json.dumps(manifest))
        Path("stage/main.py").unlink()
        Path("stage/main.mpy").write_bytes(b"M\x06\x00\x1f")
        self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_invalid_compiled_header_is_rejected(self):
        self.manifest(Path("stage"))
        Path("stage/main.py").unlink()
        Path("stage/main.mpy").write_bytes(b"not-mpy")
        with self.assertRaises(ValueError):
            self.install.validate_manifest("stage", "com.example.upgrade", "1.0.0")

    def test_unknown_provider_cannot_bypass_integrity_checks(self):
        app = self.prepare_archive()
        app._store_source = "unknown"
        with self.assertRaisesRegex(ValueError, "source"):
            asyncio.run(self.install.install_package(app))
        self.assertFalse(Path("apps/com.example.upgrade").exists())

    def test_cleanup_failure_does_not_turn_committed_install_into_failure(self):
        app = self.prepare_archive()
        original = self.install.remove_tree

        def cleanup(path):
            if path.endswith("/stage/" + app.fullname) and self.install.read_receipt(app.fullname):
                raise OSError("cleanup temporarily unavailable")
            return original(path)

        with patch.object(self.install, "remove_tree", side_effect=cleanup):
            result = asyncio.run(self.install.install_package(app))
        self.assertEqual(result["version"], "1.1.0")
        self.assertTrue(Path("apps/com.example.upgrade/main.py").is_file())

    def test_removed_helper_file_and_cache_do_not_survive_upgrade(self):
        destination = Path("apps/com.example.upgrade")
        self.manifest(destination)
        old_name = "dshell_obsolete_helper"
        new_name = "dshell_renamed_helper"
        (destination / (old_name + ".py")).write_text("MARKER = 'old'\n")
        before = sys.path[:]
        self.addCleanup(setattr, sys, "path", before)
        self.addCleanup(sys.modules.pop, old_name, None)
        self.addCleanup(sys.modules.pop, new_name, None)
        sys.path.insert(0, str(destination.resolve()))
        self.assertEqual(importlib.import_module(old_name).MARKER, "old")
        stage = Path("stage/com.example.upgrade")
        self.manifest(stage)
        (stage / (new_name + ".py")).write_text("MARKER = 'new'\n")
        Path("backup").mkdir()
        self.install.promote(str(stage), str(destination), "backup/com.example.upgrade")
        self.assertFalse((destination / (old_name + ".py")).exists())
        self.assertNotIn(old_name, sys.modules)
        with self.assertRaises(ImportError):
            importlib.import_module(old_name)
        self.assertEqual(importlib.import_module(new_name).MARKER, "new")

    def test_explicit_badgehub_source_remains_selectable(self):
        self.prefs["store_source"] = "badgehub"
        self.assertEqual(self.source.current_source(), "badgehub")

    def test_legacy_runtime_uses_framework_install(self):
        calls = []
        self.manager.install_mpk = lambda *args: calls.append(args)
        asyncio.run(self.install.extract_package("archive.mpk", "stage/com.example.upgrade", "com.example.upgrade"))
        self.assertEqual(calls, [("archive.mpk", "stage/com.example.upgrade")])

    def test_extent_extraction_preserves_bytes_and_reports_progress(self):
        payload = b"test" * 3000
        Path("archive.mpk").write_bytes(payload)
        streams = []
        progress = []
        events = []
        real_open = open

        def tracked_open(path, *args, **kwargs):
            value = real_open(path, *args, **kwargs)
            if path == "archive.mpk":
                streams.append(value)
            return value

        async def report(phase, percent):
            progress.append((phase, percent))

        async def reserve(length, align, defrag_first, progress):
            self.assertTrue(all(stream.closed for stream in streams))
            self.assertTrue(defrag_first)
            await progress(0, 0)
            return (length, align)

        class Extractor:
            def __init__(inner, destination, expected_app_name, free_space_limit):
                self.assertEqual(expected_app_name, "com.example.upgrade")
                inner.chunks = []
                events.append(inner)

            async def feed_async(inner, chunk, handler):
                inner.chunks.append(chunk)
                if len(inner.chunks) == 1:
                    self.assertEqual(await handler(64, 1), (64, 1))

            def finish(inner):
                self.assertEqual(b"".join(inner.chunks), payload)

        extent = types.SimpleNamespace(open_writer=reserve)
        module = types.ModuleType("mpos.content.streaming_unzip")
        module.StreamingUnzip = Extractor
        with patch.object(self.mpos, "extent", extent, create=True), patch.dict(sys.modules, {module.__name__: module}), patch.object(self.install, "open", tracked_open, create=True):
            asyncio.run(self.install.extract_package("archive.mpk", "stage/com.example.upgrade", "com.example.upgrade", report))
        self.assertEqual(progress, [(0, 0)])
        self.assertTrue(all(stream.closed for stream in streams))
        self.assertEqual(len(events), 1)

    def test_failed_async_extraction_closes_archive(self):
        Path("archive.mpk").write_bytes(b"bytes")
        streams = []
        real_open = open

        def tracked_open(*args):
            value = real_open(*args)
            streams.append(value)
            return value

        class Extractor:
            def __init__(inner, *args, **kwargs):
                pass

            async def feed_async(inner, *args):
                raise OSError("No contiguous flash space")

        module = types.ModuleType("mpos.content.streaming_unzip")
        module.StreamingUnzip = Extractor
        with patch.object(self.mpos, "extent", object(), create=True), patch.dict(sys.modules, {module.__name__: module}), patch.object(self.install, "open", tracked_open, create=True):
            with self.assertRaisesRegex(OSError, "contiguous"):
                asyncio.run(self.install.extract_package("archive.mpk", "stage/com.example.upgrade", "com.example.upgrade"))
        self.assertTrue(streams)
        self.assertTrue(all(stream.closed for stream in streams))


if __name__ == "__main__":
    unittest.main()
