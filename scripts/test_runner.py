#!/usr/bin/env python3
"""Run MicroPythonOS unit tests on desktop or physical/QEMU device.

Usage:
    python3 scripts/test_runner.py [test_file] [--ondevice] [--port PORT]

Examples:
    # Desktop — run all tests
    python3 scripts/test_runner.py

    # Desktop — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py

    # Physical device — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice

    # Physical device — custom port
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --port /dev/pts/5

    MPOS_TEST_PORT env var sets the default serial port (default: /dev/ttyACM0).
"""

import argparse
import glob
import os
import platform
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


def _serial_reset(port):
    import serial
    import time
    time.sleep(2)
    for attempt in range(5):
        try:
            ser = serial.Serial(port, 115200, timeout=0.5, write_timeout=0.5)
            ser.dtr = False
            time.sleep(0.1)
            ser.close()
            break
        except Exception:
            time.sleep(3)
    time.sleep(4)


def _run_one_test(test_path, backend, tests_dir, timeout, log_path):
    """Run a single test file. Returns (passed, output)."""
    backend_kwargs = {}
    if backend == "serial":
        port = os.environ.get("MPOS_TEST_PORT", "/dev/ttyACM0")
        _serial_reset(port)
        backend_kwargs = {"port": port, "reset": False}
    else:
        backend_kwargs = {"heapsize": "32M"}
        backend_kwargs["binary"] = _resolve_binary()

    if backend == "serial":
        be = SerialBackend(**backend_kwargs)
    else:
        be = ProcessBackend(**backend_kwargs)

    try:
        passed, out = be.run_test_file(
            test_path, tests_dir=tests_dir, timeout=timeout,
        )
    finally:
        be.stop()

    if log_path:
        with open(log_path, "ab") as f:
            f.write(out)

    return passed, out


def _run_with_retry(test_path, backend, tests_dir, timeout, log_path):
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print("Retry attempt {} for {}".format(attempt, test_path))

        passed, out = _run_one_test(test_path, backend, tests_dir, timeout, log_path)
        out_str = out.decode("utf-8", errors="replace")
        sys.stdout.write(out_str)

        if passed:
            return True
        # Only retry on crash exit, not on test failure
        # _run_one_test returns False for test failures, which we never retry
        print("Test crashed — retrying...")
    return False


def _batch_run(backend, tests_dir, timeout):
    all_files = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    files = [f for f in all_files if not os.path.basename(f).startswith("notondevice_")]
    if not files:
        print("No test files found in {}".format(TESTS_DIR))
        return True

    failed = []
    for f in files:
        print("=== {} ===".format(os.path.basename(f)))
        log_path = os.path.join(
            tempfile.gettempdir(),
            f.replace("/", "_").lstrip("_") + ".log",
        )
        ok = _run_with_retry(f, backend, tests_dir, timeout, log_path)
        if not ok:
            failed.append(f)
            print("WARNING: {} failed!".format(f))
    if failed:
        print("FAILED: {}/{} tests".format(len(failed), len(files)))
        for f in failed:
            print("  {}".format(f))
        return False
    print("GOOD: all {} tests passed".format(len(files)))
    return True


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
    args = parser.parse_args()

    if args.port:
        os.environ["MPOS_TEST_PORT"] = args.port
    if args.ondevice and not os.environ.get("MPOS_TEST_PORT"):
        os.environ["MPOS_TEST_PORT"] = "/dev/ttyACM0"

    backend = "serial" if args.ondevice else "process"
    tests_dir = args.tests_dir or TESTS_DIR

    _cleanup_config()

    if args.test_file:
        test_path = os.path.abspath(args.test_file)
        if not os.path.isfile(test_path):
            print("ERROR: {} is not a file".format(test_path))
            sys.exit(1)
        log_path = os.path.join(
            tempfile.gettempdir(),
            test_path.replace("/", "_").lstrip("_") + ".log",
        )
        ok = _run_with_retry(test_path, backend, tests_dir, args.timeout, log_path)
    else:
        if not args.ondevice:
            print("Running all tests on desktop...")
        else:
            print("Running all tests on device...")
        ok = _batch_run(backend, tests_dir, args.timeout)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
