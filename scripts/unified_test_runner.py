#!/usr/bin/env python3
"""Run a MicroPython unittest file on desktop or physical/QEMU device.

Usage:
    # Desktop (process backend)
    python3 scripts/unified_test_runner.py --backend process \\
        --binary /path/to/lvgl_micropy_unix --test-file /path/to/test.py \\
        --tests-dir /path/to/tests

    # Physical device
    python3 scripts/unified_test_runner.py --backend serial \\
        --port /dev/ttyACM0 --test-file /path/to/test.py

    # QEMU
    python3 scripts/unified_test_runner.py --backend serial \\
        --port /dev/pts/5 --test-file /path/to/test.py
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from mpos_controller import ProcessBackend, SerialBackend


def main():
    parser = argparse.ArgumentParser(
        description="Run a MicroPython unittest file on desktop or device"
    )
    parser.add_argument(
        "--backend", choices=["process", "serial"], default="process",
        help="Backend: process (desktop) or serial (device/QEMU)",
    )
    parser.add_argument("--binary", help="Path to lvgl_micropy_unix (process backend)")
    parser.add_argument("--heapsize", default="32M", help="Heap size (process backend)")
    parser.add_argument(
        "--port", default="/dev/ttyACM0",
        help="Serial port (serial backend, e.g. /dev/ttyACM0 or /dev/pts/5)",
    )
    parser.add_argument(
        "--baudrate", type=int, default=115200, help="Baud rate (serial backend)",
    )
    parser.add_argument("--test-file", required=True, help="Path to test .py file")
    parser.add_argument(
        "--tests-dir", help="Directory to add to sys.path for test helpers",
    )
    parser.add_argument(
        "--timeout", type=int, default=300, help="Test execution timeout in seconds",
    )
    args = parser.parse_args()

    if args.backend == "serial":
        backend = SerialBackend(
            port=args.port, baudrate=args.baudrate, reset=False,
        )
    else:
        kwargs = {"heapsize": args.heapsize}
        if args.binary:
            kwargs["binary"] = args.binary
        backend = ProcessBackend(**kwargs)

    backend.start()
    try:
        passed, out = backend.run_test_file(
            args.test_file,
            tests_dir=args.tests_dir,
            timeout=args.timeout,
        )
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.write(b"\n")
        sys.exit(0 if passed else 1)
    finally:
        backend.stop()


if __name__ == "__main__":
    main()
