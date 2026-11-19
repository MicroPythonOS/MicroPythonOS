import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FULLNAME = "com.micropythonos.appstore"


def package(output_dir, revision):
    source = ROOT / "internal_filesystem/builtin/apps" / FULLNAME
    manifest = json.loads((source / "MANIFEST.JSON").read_text())
    if manifest.get("fullname") != FULLNAME or not manifest.get("publisher") or not manifest.get("version"):
        raise ValueError("Invalid AppStore release manifest")
    if revision < 1:
        raise ValueError("Revision must be positive; this is a local artifact, not a store publication")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (FULLNAME + "_r%d.mpk" % revision)
    files = {}
    with zipfile.ZipFile(target, "w") as archive:
        root = zipfile.ZipInfo(FULLNAME + "/", (2026, 1, 1, 0, 0, 0))
        archive.writestr(root, b"")
        for path in sorted(source.rglob("*")):
            parts = path.relative_to(source).parts
            if (
                not path.is_file()
                or any(part.startswith(".") or part in ("__pycache__", "__MACOSX") for part in parts)
                or path.suffix == ".pyc"
            ):
                continue
            data = path.read_bytes()
            relative = path.relative_to(source).as_posix()
            entry = zipfile.ZipInfo(FULLNAME + "/" + relative, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
            files[relative] = hashlib.sha256(data).hexdigest()
    record = {
        "fullname": FULLNAME,
        "version": manifest["version"],
        "local_revision": revision,
        "published": False,
        "path": str(target.resolve()),
        "size_bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "files": files,
    }
    (output_dir / "release.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp/appstore-release")
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(package(args.output_dir, args.revision), indent=2))
