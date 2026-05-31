import json
import os
import unittest
from pathlib import Path

try:
    APPS_BASE_PATH = Path(__file__).parent.parent / "internal_filesystem" / "apps"
except NameError:
    APPS_BASE_PATH = Path("apps")


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
        for app_path in iter_app_path():
            with self.subTest(app=app_path.name):
                manifest = app_path / "META-INF" / "MANIFEST.JSON"
                self.assertTrue(manifest.is_file(), f"Missing {manifest=}")
                try:
                    with manifest.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    self.fail(f"Invalid JSON in {manifest=}: {e}")

                fullname = app_path.name
                self.assertEqual(data.get("fullname"), fullname)

                # Check name:
                name = data.get("name")
                self.assertTrue(name, f"Missing name in {manifest=}")

                # Check version is a valid Version
                version = data.get("version")
                self.assertTrue(version, f"Missing version in {manifest=}")
                try:
                    # Until we can use packaging.version.Version check canonical version manually:
                    version_tuple = tuple(int(x) for x in version.split("."))
                    version_str = ".".join(str(x) for x in version_tuple)
                except Exception as e:
                    self.fail(f"Invalid version {version=} in {manifest=}: {e}")
                self.assertEqual(
                    version_str,
                    version,
                    f"{version=} in {manifest=} is not in canonical form",
                )

                # Test activities.entrypoint
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

                # Test services.entrypoint
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


if __name__ == "__main__":
    unittest.main()
