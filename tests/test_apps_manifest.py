import json
import logging
import os
import unittest
from pathlib import Path

try:
    APPS_BASE_PATH = Path(__file__).parent.parent / "internal_filesystem" / "apps"
except NameError:
    APPS_BASE_PATH = Path("apps")


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        # MicroPython reuses the LogRecord object, so snapshot the message now.
        self.records.append(record.message)


def iter_app_path():
    try:
        entries = os.listdir(str(APPS_BASE_PATH))
    except OSError:
        entries = []
    for app_name in entries:
        app = APPS_BASE_PATH / app_name
        if app.is_dir():
            yield app


class TestAppsManifest(unittest.TestCase):
    def test_all_apps_manifest(self):
        logger = logging.getLogger("mpos.app.app")
        handler = _ListHandler()
        logger.handlers.append(handler)
        try:
            for app_path in iter_app_path():
                with self.subTest(app=app_path.name):
                    manifest_root = app_path / "MANIFEST.JSON"
                    manifest_old = app_path / "META-INF" / "MANIFEST.JSON"
                    if manifest_root.is_file():
                        manifest = manifest_root
                    elif manifest_old.is_file():
                        manifest = manifest_old
                        warnings = [
                            r for r in handler.records
                            if "Deprecated manifest path" in r
                            and str(manifest_old) in r
                        ]
                        self.assertTrue(
                            warnings,
                            f"Old manifest path {manifest_old} used without deprecation warning",
                        )
                    else:
                        self.fail(f"Missing MANIFEST.JSON in {app_path}")

                    try:
                        with manifest.open("r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception as e:
                        self.fail(f"Invalid JSON in {manifest=}: {e}")

                    fullname = app_path.name
                    self.assertEqual(data.get("fullname"), fullname)

                    name = data.get("name")
                    self.assertTrue(name, f"Missing name in {manifest=}")

                    version = data.get("version")
                    self.assertTrue(version, f"Missing version in {manifest=}")
                    try:
                        version_tuple = tuple(int(x) for x in version.split("."))
                        version_str = ".".join(str(x) for x in version_tuple)
                    except Exception as e:
                        self.fail(f"Invalid version {version=} in {manifest=}: {e}")
                    self.assertEqual(
                        version_str,
                        version,
                        f"{version=} in {manifest=} is not in canonical form",
                    )

                    activities = data.get("activities", [])
                    for act in activities:
                        entrypoint = act.get("entrypoint")
                        self.assertTrue(
                            entrypoint, f"Missing entrypoint in activity of {manifest=}"
                        )
                        self.assertTrue(
                            entrypoint.endswith(".py"),
                            f"Invalid entrypoint in activity of {manifest=}: {entrypoint}",
                        )
                        entrypoint_path = app_path / entrypoint
                        self.assertTrue(
                            entrypoint_path.is_file(),
                            f"{entrypoint=} in {manifest=} does not exist as file",
                        )

                        classname = act.get("classname")
                        self.assertTrue(
                            classname, f"Missing classname in activity of {manifest=}"
                        )
                        entrypoint_code = entrypoint_path.read_text()
                        self.assertIn(
                            classname,
                            entrypoint_code,
                            f"{classname=} not found in {entrypoint=} of {manifest=}",
                        )

                    services = data.get("services", [])
                    for svc in services:
                        entrypoint = svc.get("entrypoint")
                        self.assertTrue(
                            entrypoint, f"Missing entrypoint in service of {manifest=}"
                        )
                        self.assertTrue(
                            entrypoint.endswith(".py"),
                            f"Invalid entrypoint in service of {manifest=}: {entrypoint}",
                        )
                        entrypoint_path = app_path / entrypoint
                        self.assertTrue(
                            entrypoint_path.is_file(),
                            f"{entrypoint=} in {manifest=} does not exist as file",
                        )

                        classname = svc.get("classname")
                        self.assertTrue(
                            classname, f"Missing classname in service of {manifest=}"
                        )
                        entrypoint_code = entrypoint_path.read_text()
                        self.assertIn(
                            classname,
                            entrypoint_code,
                            f"{classname=} not found in {entrypoint=} of {manifest=}",
                        )
        finally:
            try:
                logger.handlers.remove(handler)
            except ValueError:
                pass


if __name__ == "__main__":
    unittest.main()
