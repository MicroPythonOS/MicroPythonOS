import argparse
from pathlib import Path


def prepare_boot(source):
    marker = "    import mpos.main  # noqa: F401\n"
    if source.count(marker) != 1:
        raise ValueError("Standard startup import must occur exactly once")
    return source.replace(marker, (
        "    from mpos.device_info import DeviceInfo\n"
        "    if DeviceInfo.hardware_id == \"missing-hardware-info\":\n"
        "        DeviceInfo.set_hardware_id(\"d_shell\")\n"
    ) + marker, 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = (root / "internal_filesystem/main.py").read_text(encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "main.py").write_text(prepare_boot(source), encoding="utf-8")
