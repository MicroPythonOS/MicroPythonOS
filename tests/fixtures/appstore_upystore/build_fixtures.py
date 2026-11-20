import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        for name, data in files:
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_STORED if name.endswith("/") else zipfile.ZIP_DEFLATED
            package.writestr(item, data)
    return output.getvalue()


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    bundles = []
    records = {}
    icon = (ROOT / "internal_filesystem/builtin/apps/com.micropythonos.appstore/icon_64x64.png").read_bytes()
    for key in ("upgrade", "peer"):
        fullname = "com.freakstudio.storetest_" + key
        module = "dshell_storetest_" + key + "_helper"
        source = """import lvgl as lv
from mpos import Activity
import MODULE as helper


class UpgradeProbe(Activity):
    def onCreate(self):
        self.helper_marker = helper.MARKER
        self.helper_result = helper.calculate(2, 3)
        self.helper_file = helper.__file__
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text("TEST helper %s / %s" % (self.helper_marker, self.helper_result))
        label.center()
        self.setContentView(screen)
        print("CONTROLLED_HELPER_STARTED", self.appFullName, self.helper_marker, self.helper_result)
""".replace("MODULE", module)
        records[key] = []
        for revision, version, launcher in ((1, "1.0.0", True), (2, "1.1.0", True), (3, "1.2.0", False)):
            selected_module = module + "_renamed" if key == "upgrade" and revision > 1 else module
            removed_module = module + "_removed"
            manifest = {
                "name": "TEST Helper " + key,
                "fullname": fullname,
                "publisher": "FreakStudio test fixtures - not published",
                "version": version,
                "category": "development",
                "activities": [
                    {
                        "entrypoint": "assets/main.py",
                        "classname": "UpgradeProbe",
                        "intent_filters": [{"action": "main", "category": "launcher"}] if launcher else [],
                    }
                ],
            }
            entries = [
                    (fullname + "/", b""),
                    (fullname + "/MANIFEST.JSON", json.dumps(manifest).encode()),
                    (fullname + "/icon_64x64.png", icon),
                    (fullname + "/assets/", b""),
                    (fullname + "/assets/main.py", source.replace(module, selected_module).encode()),
                    (
                        fullname + "/assets/" + selected_module + ".py",
                        (
                            ("import " + removed_module + "\n" if key == "upgrade" and revision == 1 else "")
                            + 'MARKER = "v%d"\ndef calculate(a, b):\n    return a + b + %d\n'
                            % (revision, (revision - 1) * 100)
                        ).encode(),
                    ),
                ]
            if key == "upgrade" and revision == 1:
                entries.append((fullname + "/assets/" + removed_module + ".py", b'VALUE = "old-only"\n'))
            data = archive(entries)
            name = "%s_r%d.mpk" % (fullname, revision)
            (output / name).write_bytes(data)
            bundles.append(("appstore-test/" + name, data))
            records[key].append(
                {
                    "fullname": fullname,
                    "name": "TEST Helper " + key,
                    "slug": fullname.replace(".", "-"),
                    "revision": revision,
                    "version": version,
                    "filename": name,
                    "file_size_bytes": len(data),
                    "file_sha256": hashlib.sha256(data).hexdigest(),
                    "manifest": manifest,
                    "helper_module": selected_module,
                    "removed_module": removed_module if key == "upgrade" else None,
                }
            )
    metadata = json.dumps(records, indent=2).encode()
    (output / "fixtures.json").write_bytes(metadata)
    bundles.insert(0, ("appstore-test/", b""))
    bundles.append(("appstore-test/fixtures.json", metadata))
    bundles.append(("appstore-test/device_transport.py", Path(__file__).with_name("device_transport.py").read_bytes()))
    (output / "fixture-bundle.zip").write_bytes(archive(bundles))
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/appstore-fixtures")
    args = parser.parse_args()
    records = build(args.output)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "packages": 6,
                "transport": "controlled local fixtures; not a public-store upgrade",
            },
            indent=2,
        )
    )
