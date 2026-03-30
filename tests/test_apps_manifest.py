import json
import unittest
from pathlib import Path

from packaging.version import Version

APPS_BASE_PATH = Path(__file__).parent.parent / "internal_filesystem" / "apps"


def iter_app_path():
    for app in APPS_BASE_PATH.iterdir():
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
                    parsed_version = Version(version)
                except Exception as e:
                    self.fail(f"Invalid version {version=} in {manifest=}: {e}")
                self.assertEqual(
                    str(parsed_version),
                    version,
                    f"{version=} in {manifest=} is not in canonical form",
                )

                # Test download_url:
                download_url = data.get("download_url")
                self.assertTrue(download_url, f"Missing download_url in {manifest=}")
                self.assertTrue(
                    download_url.startswith("https://apps.micropythonos.com/apps/"),
                    f"Invalid download_url in {manifest=}: {download_url}",
                )
                self.assertEqual(
                    download_url,
                    f"https://apps.micropythonos.com/apps/{fullname}/mpks/{fullname}_{version}.mpk",
                )

                # Test icon_url:
                icon_url = data.get("icon_url")
                self.assertTrue(icon_url, f"Missing icon_url in {manifest=}")
                self.assertTrue(
                    icon_url.startswith("https://apps.micropythonos.com/apps/"),
                    f"Invalid icon_url in {manifest=}: {icon_url}",
                )
                self.assertEqual(
                    icon_url,
                    f"https://apps.micropythonos.com/apps/{fullname}/icons/{fullname}_{version}_64x64.png",
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

                # Just reformat the JSON to keep changes minimal and avoid merge conflicts:
                content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
                manifest.write_text(content, encoding="utf-8")

if __name__ == "__main__":
    unittest.main()
