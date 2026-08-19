#!/usr/bin/env python3
"""Run MicroPythonOS unit tests on desktop or physical/QEMU device.

Usage:
    python3 scripts/test_runner.py [test_file ...] [--ondevice] [--port PORT] [--reset] [--relayport PORT] [--coverage]

Examples:
    # Desktop — run all tests
    python3 scripts/test_runner.py

    # Desktop — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py

    # Desktop — multiple tests
    python3 scripts/test_runner.py tests/test_a.py tests/test_b.py

    # Desktop — with coverage (requires mpcov build variant)
    python3 scripts/test_runner.py --coverage tests/test_adpcm_ima.py tests/test_number_format.py

    # Desktop — save coverage data for later merging or HTML report
    python3 scripts/test_runner.py --coverage --coverage-save cov.json tests/test_*.py

    # Desktop — merge into existing coverage data
    python3 scripts/test_runner.py --coverage --coverage-load cov.json --coverage-save cov.json tests/test_extra.py

    # Generate HTML report from saved coverage data
    python3 scripts/coverage_report.py cov.json -o coverage_report.html

    # Physical device — single test
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice

    # Physical device — custom port
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --port /dev/pts/5

    # Physical device — power-cycle reset via USB relay
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --reset --relayport /dev/ttyUSB0

    # Physical device — log serial traffic to a file (watch with: tail -f serial.log)
    python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --logserial /tmp/serial.log

    MPOS_TEST_PORT env var sets the default serial port (default: /dev/ttyACM0).
"""

import argparse
import glob
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time


sys.path.insert(0, os.path.dirname(__file__))
from mpos_controller import ProcessBackend, SerialBackend


REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
TESTS_DIR = os.path.join(REPO_ROOT, "tests")
FS_ROOT = os.path.join(REPO_ROOT, "internal_filesystem")
BUILD_DIR = os.path.join(REPO_ROOT, "lvgl_micropython", "build")

MAX_RETRIES = 3

ONDEVICE_SKIP = {
    "test_apps_manifest.py",
    "test_connectivity_manager.py",
    "test_connectivity_manager_reconnect.py",
    "test_graphical_appstore_scanqr.py",
    "test_osupdate.py",
    "test_wifi_service.py",
}

COVERAGE_RE = re.compile(
    r"=== COVERAGE_DATA ===\n(.*?)\n=== END_COVERAGE_DATA ===", re.DOTALL
)


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
    import shutil
    prefs = os.path.join(FS_ROOT, "prefs")
    try:
        shutil.rmtree(prefs)
    except OSError:
        pass


def _extract_coverage(out_bytes):
    out_str = out_bytes.decode("utf-8", errors="replace")
    m = COVERAGE_RE.search(out_str)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return {}


def _count_code_lines(relpath):
    path = os.path.join(FS_ROOT, relpath)
    try:
        with open(path) as f:
            lines = f.readlines()
    except (OSError, IOError):
        return 0
    count = 0
    in_docstring = None
    for line in lines:
        stripped = line.lstrip()
        if in_docstring:
            if in_docstring in line:
                in_docstring = None
            continue
        if not stripped or stripped.startswith("#"):
            continue
        for delim in ('"""', "'''"):
            idx = line.find(delim)
            if idx == -1:
                continue
            rest = line[idx + 3:]
            if delim in rest:
                before = line[:idx].strip()
                if before and not before.startswith("#"):
                    count += 1
                break
            in_docstring = delim
            before = line[:idx].strip()
            if before and not before.startswith("#"):
                count += 1
            break
        else:
            count += 1
    return count


def _load_coverage(path):
    if not path or not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save_coverage(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _merge_coverage(merged, new_data):
    """Merge new_data into merged. Both have format: {"files": {fn: {"lines": {str(line): count}}}}."""
    if not new_data:
        return merged
    for fn, info in new_data.get("files", {}).items():
        if fn not in merged.get("files", {}):
            merged.setdefault("files", {})[fn] = {"lines": {}}
        merged_lines = merged["files"][fn]["lines"]
        for lineno, count in info.get("lines", {}).items():
            merged_lines[lineno] = merged_lines.get(lineno, 0) + count
    return merged


def _compute_stats(data):
    """Compute total_lines, covered_lines per file and globally. Adds total_lines to each file."""
    total_files = 0
    total_lines = 0
    total_covered = 0
    files = data.get("files", {})
    for fn, info in files.items():
        real_lines = _count_code_lines(fn)
        if real_lines == 0:
            continue
        info["total_lines"] = real_lines
        covered = len(info.get("lines", {}))
        total_files += 1
        total_lines += real_lines
        total_covered += covered
    data["summary"] = {
        "files": total_files,
        "total_lines": total_lines,
        "covered_lines": total_covered,
        "pct": round(total_covered / total_lines * 100, 1) if total_lines else 0.0,
    }
    return data


def _print_inline_report(data):
    summary = data.get("summary", {})
    print(
        "\n{} files  {} / {} lines  ({:.1f}%)".format(
            summary.get("files", 0),
            summary.get("covered_lines", 0),
            summary.get("total_lines", 0),
            summary.get("pct", 0.0),
        )
    )
    for fn in sorted(data.get("files", {}).keys()):
        info = data["files"][fn]
        total = info.get("total_lines", 0)
        covered = len(info.get("lines", {}))
        pct = (covered / total * 100) if total > 0 else 100
        uncovered = sorted(set(range(1, total + 1)) - {int(k) for k in info.get("lines", {}).keys()})
        print("  {:3d}/{:3d} ({:5.1f}%)  {}".format(covered, total, pct, fn))
        if uncovered:
            print("    uncovered: {}".format(_fmt_ranges(uncovered)))


def _fmt_ranges(lines):
    if not lines:
        return ""
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


def _serial_log_open(path):
    try:
        return open(path, "a", encoding="utf-8", errors="replace")
    except OSError as e:
        print("WARNING: cannot open --logserial file {}: {}".format(path, e))
        return None


def _serial_log_write(log_f, direction, data):
    if log_f is None or not data:
        return
    try:
        log_f.write(
            "[{:3s}] {:10.3f} {}\n".format(
                direction, time.monotonic(),
                data.decode("utf-8", errors="replace"),
            )
        )
        log_f.flush()
    except OSError:
        pass


def _relay_write(relay_port, data):
    try:
        import serial as _serial
    except ImportError:
        raise SystemExit(
            "pyserial is required for --relayport: pip install pyserial"
        )
    #with _serial.Serial(relay_port, 115200, timeout=1) as ser:
    with _serial.Serial(relay_port, 9600, timeout=1) as ser:
        ser.write(data)


def _relay_reset(relay_port, device_port, boot_timeout=60, log_f=None):
    """Power-cycle the device via a USB relay.

    The relay controls the device's power supply. Power off, wait for the
    board to drop, power back on, then poll the device serial port until it
    reappears and "Starting asyncio REPL..." confirms main.py ran to
    completion (same sentinel used by SerialBackend.hard_reset).
    """
    print("Power-cycling device via relay on {}...".format(relay_port))
    _serial_log_write(log_f, "REL", b"\xA0\x01\x00\xA1")
    _relay_write(relay_port, b"\xA0\x01\x00\xA1")
    time.sleep(2)
    _serial_log_write(log_f, "REL", b"\xA0\x01\x01\xA2")
    _relay_write(relay_port, b"\xA0\x01\x01\xA2")

    try:
        import serial as _serial
    except ImportError:
        raise SystemExit(
            "pyserial is required for --relayport: pip install pyserial"
        )

    print("waiting for device at {} to boot...".format(device_port))
    last_err = None
    for _ in range(20):
        if not os.path.exists(device_port):
            time.sleep(3)
            continue
        try:
            ser = _serial.Serial(
                device_port, 115200, timeout=0.5, write_timeout=2,
            )
            try:
                t0 = time.monotonic()
                data = b""
                while time.monotonic() - t0 < min(boot_timeout, 60):
                    chunk = ser.read(4096)
                    if chunk:
                        data += chunk
                        _serial_log_write(log_f, "RX", chunk)
                        if b"Starting asyncio REPL..." in data:
                            _serial_log_write(
                                log_f, "RX",
                                b"<detected 'Starting asyncio REPL...'>\n",
                            )
                            return True
                    time.sleep(0.1)
            finally:
                ser.close()
        except (OSError, _serial.SerialException) as e:
            last_err = e
            time.sleep(3)
    raise RuntimeError(
        "Device at {} not reachable after relay reset: {}".format(
            device_port, last_err
        )
    )


def _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False, relay_port=None, log_f=None):
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
            if relay_port:
                _relay_reset(relay_port, port, log_f=log_f)
            else:
                print("Hard-resetting device...")
                be.hard_reset()
        _serial_log_write(
            log_f, "TST",
            b"--- " + os.path.basename(test_path).encode() + b" ---\n",
        )
        passed, out = be.run_test_file(
            test_path, tests_dir=tests_dir, timeout=timeout,
            **({"coverage": coverage} if backend == "process" else {})
        )
        _serial_log_write(log_f, "RX", out)
    finally:
        be.stop()

    if log_path:
        with open(log_path, "ab") as f:
            f.write(out)

    return passed, out


def _run_with_retry(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False, relay_port=None, log_f=None):
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print("Retry attempt {} for {}".format(attempt, test_path))

        passed, out = _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset, coverage, relay_port, log_f)
        out_str = out.decode("utf-8", errors="replace")
        sys.stdout.write(out_str)

        if passed:
            return True, out
        if "TEST WAS A FAILURE" in out_str:
            return False, out
        print("Test crashed — retrying...")
    return False, out


def _run_tests(test_files, backend, tests_dir, timeout, reset=False, coverage=False, relay_port=None, logserial=None):
    failed = []
    merged = {}
    log_f = _serial_log_open(logserial) if logserial else None
    try:
        for f in test_files:
            print("=== {} ===".format(os.path.basename(f)))
            log_path = os.path.join(
                tempfile.gettempdir(),
                f.replace("/", "_").lstrip("_") + ".log",
            )
            ok, out = _run_with_retry(f, backend, tests_dir, timeout, log_path, reset, coverage, relay_port, log_f)
            if not ok:
                failed.append(f)
                print("WARNING: {} failed!".format(f))
            if coverage and out:
                cov = _extract_coverage(out)
                merged = _merge_coverage(merged, cov)
    finally:
        if log_f is not None:
            log_f.close()
    if failed:
        print("FAILED: {}/{} tests".format(len(failed), len(test_files)))
        for f in failed:
            print("  {}".format(f))
        return False, merged
    print("GOOD: all {} tests passed".format(len(test_files)))
    return True, merged


def _install_test_apps(port=None):
    install_script = os.path.join(REPO_ROOT, "scripts", "install_test_apps.sh")
    if not os.path.isfile(install_script):
        print("WARNING: install_test_apps.sh not found, skipping app install")
        return
    cmd = ["bash", install_script]
    if port:
        cmd.extend(["--serial-port", port])
    print("Installing test apps (use --no-install-test-apps to skip)...")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print("ERROR: test app installation failed")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Run MicroPythonOS unit tests on desktop or device",
    )
    parser.add_argument(
        "test_files", nargs="*", default=None,
        help="Test file(s) to run (omit to run all)",
    )
    parser.add_argument(
        "--ondevice", action="store_true",
        help="Run on a connected device instead of desktop",
    )
    parser.add_argument(
        "--no-install-test-apps", action="store_true",
        help="Skip automatic install of test apps when --ondevice is used",
    )
    parser.add_argument(
        "--port", default=None,
        help="Serial port for device (overrides MPOS_TEST_PORT env var)",
    )
    parser.add_argument(
        "--relayport", default=None,
        help="Serial port of a USB power relay for the device (e.g. /dev/ttyUSB0). "
             "When given with --reset, power-cycles the device instead of machine.reset(). "
             "Requires --ondevice.",
    )
    parser.add_argument(
        "--logserial", default=None,
        help="Log serial traffic (device output and relay/boot polling) to FILE. "
             "Requires --ondevice. Watch in realtime with: tail -f FILE",
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
        "--coverage-save", default=None,
        help="Save merged coverage JSON to FILE (use with --coverage-load to merge runs)",
    )
    parser.add_argument(
        "--coverage-load", default=None,
        help="Load existing coverage JSON from FILE and merge with this run's results",
    )
    args = parser.parse_args()

    _warned = False
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(line_buffering=True)
        elif not _warned:
            _warned = True
            sys.stderr.write(
                "WARNING: stream lacks reconfigure(); piped output may be "
                "buffered until the process exits\n"
            )

    if args.coverage and args.ondevice:
        print("ERROR: --coverage only works with desktop backend")
        sys.exit(1)
    if args.reset and not args.ondevice:
        print("WARNING: --reset has no effect without --ondevice, ignoring")
    if args.relayport and not args.ondevice:
        print("WARNING: --relayport has no effect without --ondevice, ignoring")
    if args.relayport and not args.reset:
        print("WARNING: --relayport has no effect without --reset, ignoring")
    if args.logserial and not args.ondevice:
        print("WARNING: --logserial has no effect without --ondevice, ignoring")

    if args.port:
        os.environ["MPOS_TEST_PORT"] = args.port
    if args.ondevice and not os.environ.get("MPOS_TEST_PORT"):
        os.environ["MPOS_TEST_PORT"] = "/dev/ttyACM0"

    if args.ondevice and not args.no_install_test_apps:
        _install_test_apps(args.port)

    backend = "serial" if args.ondevice else "process"
    tests_dir = args.tests_dir or TESTS_DIR
    do_reset = args.reset and args.ondevice

    _cleanup_config()

    if args.test_files:
        test_files = [os.path.abspath(f) for f in args.test_files]
        for f in test_files:
            if not os.path.isfile(f):
                print("ERROR: {} is not a file".format(f))
                sys.exit(1)
    else:
        all_files = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
        test_files = [f for f in all_files if not os.path.basename(f).startswith("notondevice_")]
        if args.ondevice:
            test_files = [f for f in test_files if os.path.basename(f) not in ONDEVICE_SKIP]
        if not test_files:
            print("No test files found in {}".format(TESTS_DIR))
            sys.exit(1)

    ok, coverage_data = _run_tests(
        test_files, backend, tests_dir, args.timeout, do_reset, args.coverage,
        args.relayport, args.logserial,
    )

    if args.coverage:
        if args.coverage_load:
            existing = _load_coverage(args.coverage_load)
            coverage_data = _merge_coverage(existing, coverage_data)

        _compute_stats(coverage_data)

        if args.coverage_save:
            _save_coverage(args.coverage_save, coverage_data)
            s = coverage_data.get("summary", {})
            print("Coverage saved to {}  ({} files, {:.1f}%)".format(
                args.coverage_save, s.get("files", 0), s.get("pct", 0.0),
            ))
        else:
            _print_inline_report(coverage_data)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
