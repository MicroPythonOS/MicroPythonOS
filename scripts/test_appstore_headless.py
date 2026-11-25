import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from mpos_controller import _build_test_code

TESTS = (
    "test_appstore_update_flow.py",
    "test_appstore_async_refresh.py",
    "test_appstore_uninstall_refresh.py",
    "test_appstore_list_build.py",
    "test_appstore_ratings.py",
    "test_appstore_install_safety.py",
    "test_appstore_owner_lifecycle.py",
    "test_appstore_builtin_source.py",
    "test_graphical_appstore_install_button.py",
)
HEADER = """import micropython
micropython.opt_level(0)
import sys
sys.path.insert(0, "lib")
import lvgl as lv
lv.init()
_display = lv.display_create(320, 240)
_buffer = bytearray(320 * 24 * 2)
_display.set_buffers(_buffer, None, len(_buffer), lv.DISPLAY_RENDER_MODE.PARTIAL)
_display.set_flush_cb(lambda display, area, pixels: display.flush_ready())
from mpos import DownloadManager, DisplayMetrics
DisplayMetrics.set_resolution(320, 240)
DisplayMetrics.set_dpi(130)
async def _no_live_request(*args, **kwargs):
    raise RuntimeError("Unexpected live network in unit test")
DownloadManager.download_url = _no_live_request
"""


def run(binary, output):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for filename in TESTS:
        code = output / ("headless_" + filename)
        code.write_text(HEADER + _build_test_code(str(ROOT / "tests" / filename)), encoding="utf-8")
        try:
            process = subprocess.run(
                [str(binary), str(code.resolve())], cwd=ROOT / "internal_filesystem", capture_output=True, timeout=90
            )
            log = process.stdout + process.stderr
            passed = process.returncode == 0 and b"TEST WAS A SUCCESS" in log and b"TEST WAS A FAILURE" not in log
            (output / (filename + ".log")).write_bytes(log)
            results.append({"test": filename, "passed": passed, "returncode": process.returncode})
        except subprocess.TimeoutExpired:
            results.append({"test": filename, "passed": False, "error": "timeout"})
        print(filename, "PASS" if results[-1]["passed"] else "FAIL", flush=True)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return all(item["passed"] for item in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=ROOT / "lvgl_micropython/build/lvgl_micropy_unix")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp/appstore-native-regressions")
    args = parser.parse_args()
    sys.exit(0 if run(args.binary.resolve(), args.output_dir) else 1)
