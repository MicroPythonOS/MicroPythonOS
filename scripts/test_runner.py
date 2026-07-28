#!/usr/bin/env python3
"""Run MicroPythonOS unit tests on desktop or physical/QEMU device.

Usage:
    python3 scripts/test_runner.py [test_file] [--ondevice] [--port PORT] [--coverage]

Examples:
    # Desktop — run all tests
    python3 scripts/test_runner.py

    # Desktop — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py

    # Desktop — run all tests with coverage (requires mpcov build variant)
    python3 scripts/test_runner.py --coverage

    # Desktop — single test with coverage
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --coverage

    # Physical device — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice

    Physical device — custom port
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --port /dev/pts/5

    MPOS_TEST_PORT env var sets the default serial port (default: /dev/ttyACM0).
"""

import argparse
import glob
import json
import os
import platform
import re
import sys
import tempfile


sys.path.insert(0, os.path.dirname(__file__))
from mpos_controller import ProcessBackend, SerialBackend


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
FS_DIR = os.path.join(REPO_ROOT, "internal_filesystem")
BUILD_DIR = os.path.join(REPO_ROOT, "lvgl_micropython", "build")

MAX_RETRIES = 3


def _resolve_binary():
    if platform.system() == "Darwin":
        name = "lvgl_micropy_macOS"
    else:
        name = "lvgl_micropy_unix"
    path = os.path.join(BUILD_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "Binary not found: {}. Run ./scripts/build_mpos.sh unix first.".format(path)
        )
    os.chmod(path, 0o755)
    return os.path.abspath(path)


def _cleanup_config():
    config = os.path.join(FS_DIR, "prefs", "com.micropythonos.settings", "config.json")
    try:
        os.remove(config)
    except OSError:
        pass


COVERAGE_RE = re.compile(
    r"=== COVERAGE_DATA ===\n(.*?)\n=== END_COVERAGE_DATA ===", re.DOTALL
)


def _extract_coverage(out_bytes):
    out_str = out_bytes.decode("utf-8", errors="replace")
    m = COVERAGE_RE.search(out_str)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return {}


def _merge_coverage(merged, new_data):
    for fn, info in new_data.items():
        if fn not in merged:
            merged[fn] = {"covered": set(info.get("covered", [])), "total_lines": info.get("total_lines", 0)}
        else:
            merged[fn]["covered"].update(info.get("covered", []))
            merged[fn]["total_lines"] = max(merged[fn]["total_lines"], info.get("total_lines", 0))
    return merged


def _report_coverage(merged, out_file=None):
    lines = []
    total_covered = 0
    total_lines = 0
    for fn in sorted(merged.keys()):
        info = merged[fn]
        covered = len(info["covered"])
        total = info["total_lines"]
        pct = (covered / total * 100) if total > 0 else 100
        total_covered += covered
        total_lines += total
        uncovered = sorted(set(range(1, total + 1)) - set(info["covered"]))
        lines.append("")
        lines.append("{}  {}/{} ({:.1f}%)".format(fn, covered, total, pct))
        if uncovered:
            lines.append("  uncovered: {}".format(_fmt_ranges(uncovered)))
    overall_pct = (total_covered / total_lines * 100) if total_lines > 0 else 0
    summary = "Total: {}/{} ({:.1f}%)".format(total_covered, total_lines, overall_pct)
    output = summary + "\n" + "\n".join(lines)
    if out_file:
        with open(out_file, "w") as f:
            f.write(output + "\n")
    print(output)
    return output


def _fmt_ranges(lines):
    ranges = []
    start = prev = lines[0]
    for n in lines[1:]:
        if n == prev + 1:
            prev = n
        else:
            ranges.append("{}-{}".format(start, prev) if start != prev else str(start))
            start = prev = n
    ranges.append("{}-{}".format(start, prev) if start != prev else str(start))
    return ", ".join(ranges)


def _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False):
    """Run a single test file. Returns (passed, output)."""
    backend_kwargs = {}
    if backend == "serial":
        port = os.environ.get("MPOS_TEST_PORT", "/dev/ttyACM0")
        backend_kwargs = {"port": port, "reset": False}
    else:
        backend_kwargs = {"heapsize": "32M"}
        backend_kwargs["binary"] = _resolve_binary()

    if backend == "serial":
        be = SerialBackend(**backend_kwargs)
    else:
        be = ProcessBackend(**backend_kwargs)

    try:
        if reset and backend == "serial":
            print("Hard-resetting device...")
            be.hard_reset()
        passed, out = be.run_test_file(
            test_path, tests_dir=tests_dir, timeout=timeout, coverage=coverage,
        )
    finally:
        be.stop()

    if log_path:
        with open(log_path, "ab") as f:
            f.write(out)

    return passed, out


def _run_with_retry(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False):
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print("Retry attempt {} for {}".format(attempt, test_path))

        passed, out = _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset, coverage)
        out_str = out.decode("utf-8", errors="replace")
        sys.stdout.write(out_str)

        if passed:
            return True, out
        print("Test crashed — retrying...")
    return False, out


def _batch_run(backend, tests_dir, timeout, reset=False, coverage=False):
    all_files = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    files = [f for f in all_files if not os.path.basename(f).startswith("notondevice_")]
    if not files:
        print("No test files found in {}".format(TESTS_DIR))
        return True, {}

    failed = []
    merged = {}
    for f in files:
        print("=== {} ===".format(os.path.basename(f)))
        log_path = os.path.join(
            tempfile.gettempdir(),
            f.replace("/", "_").lstrip("_") + ".log",
        )
        ok, out = _run_with_retry(f, backend, tests_dir, timeout, log_path, reset, coverage)
        if not ok:
            failed.append(f)
            print("WARNING: {} failed!".format(f))
        if coverage and out:
            cov = _extract_coverage(out)
            merged = _merge_coverage(merged, cov)
    if failed:
        print("FAILED: {}/{} tests".format(len(failed), len(files)))
        for f in failed:
            print("  {}".format(f))
        return False, merged
    print("GOOD: all {} tests passed".format(len(files)))
    return True, merged


def main():
    parser = argparse.ArgumentParser(
        description="Run MicroPythonOS unit tests on desktop or device",
    )
    parser.add_argument(
        "test_file", nargs="?", default=None,
        help="Path to a single test file (omit to run all)",
    )
    parser.add_argument(
        "--ondevice", action="store_true",
        help="Run on a connected device instead of desktop",
    )
    parser.add_argument(
        "--port", default=None,
        help="Serial port for device (overrides MPOS_TEST_PORT env var)",
    )
    parser.add_argument(
        "--tests-dir", default=None,
        help="Directory to add to sys.path for test helpers",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Test execution timeout in seconds",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Hard-reset the device before each test (--ondevice only)",
    )
    parser.add_argument(
        "--coverage", action="store_true",
        help="Collect line coverage (desktop only, requires mpcov build variant)",
    )
    parser.add_argument(
        "--coverage-file", default=None,
        help="Write coverage report to file",
    )
    args = parser.parse_args()

    if args.coverage and args.ondevice:
        print("ERROR: --coverage only works with desktop backend")
        sys.exit(1)
    if args.reset and not args.ondevice:
        print("WARNING: --reset has no effect without --ondevice, ignoring")

    if args.port:
        os.environ["MPOS_TEST_PORT"] = args.port
    if args.ondevice and not os.environ.get("MPOS_TEST_PORT"):
        os.environ["MPOS_TEST_PORT"] = "/dev/ttyACM0"

    backend = "serial" if args.ondevice else "process"
    tests_dir = args.tests_dir or TESTS_DIR
    do_reset = args.reset and args.ondevice

    _cleanup_config()

    coverage = args.coverage
    merged = {}

    if args.test_file:
        test_path = os.path.abspath(args.test_file)
        if not os.path.isfile(test_path):
            print("ERROR: {} is not a file".format(test_path))
            sys.exit(1)
        log_path = os.path.join(
            tempfile.gettempdir(),
            test_path.replace("/", "_").lstrip("_") + ".log",
        )
        ok, out = _run_with_retry(test_path, backend, tests_dir, args.timeout, log_path, do_reset, coverage)
        if coverage and out:
            merged = _extract_coverage(out)
    else:
        if not args.ondevice:
            print("Running all tests on desktop...")
        else:
            print("Running all tests on device...")
        ok, merged = _batch_run(backend, tests_dir, args.timeout, do_reset, coverage)

    if coverage:
        _report_coverage(merged, out_file=args.coverage_file)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
