#!/usr/bin/env python3
"""Run MicroPythonOS unit tests on desktop or physical/QEMU device.

Usage:
    python3 scripts/test_runner.py [test_file ...] [--ondevice] [--port PORT] [--reset] [--relayport PORT] [--coverage] [--resume]

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

    # Resume full test suite from a given test
    python3 scripts/test_runner.py --resume tests/test_notification_manager.py --ondevice --reset --relayport /dev/ttyUSB0

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
    "test_retrogo_launcher.py",
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


def _find_usb_device_info(port):
    """Find sysfs info for a /dev/tty* port: returns (tty_name, usb_dev, driver, sysfs_tty_path) or None."""
    try:
        tty = os.path.basename(port)
        sys_tty = "/sys/class/tty/{}".format(tty)
        if not os.path.islink(sys_tty) and not os.path.exists(sys_tty):
            return None
        real = os.path.realpath(sys_tty)
        # real is like /sys/devices/pci0000:00/0000:01:00.0/usb6/6-1/6-1.2/6-1.2:1.0/tty/ttyACM0
        parts = real.split("/")
        # find the usb device (e.g. 6-1.2) — the component that is like "6-1.2" or "6-1.3"
        usb_dev = None
        for p in parts:
            # usb device names are like "6-1", "6-1.2", "6-1.3", "usb6"
            if "-" in p and p[0].isdigit():
                # prefer the most specific (with dot)
                if "." in p:
                    usb_dev = p
                elif usb_dev is None:
                    usb_dev = p
        driver = None
        # driver is the directory's parent's driver link, e.g. .../6-1.2:1.0/driver -> cdc_acm or ch341
        try:
            drv_link = os.path.join(os.path.dirname(real), "driver")
            if os.path.islink(drv_link):
                driver = os.path.basename(os.path.realpath(drv_link))
        except Exception:
            pass
        return (tty, usb_dev, driver, real)
    except Exception:
        return None


def _usb_authorized_path(usb_dev):
    return "/sys/bus/usb/devices/{}/authorized".format(usb_dev)


def _usb_driver_unbind_path(driver, usb_dev):
    # driver unbind path is /sys/bus/usb/drivers/<driver>/unbind
    # usb_dev for ttyACM0 is like 6-1.2, but driver bind needs 6-1.2:1.0
    return "/sys/bus/usb/drivers/{}/unbind".format(driver), "/sys/bus/usb/drivers/{}/bind".format(driver)


def _usb_unbind_device(port, log_f=None, settle=5):
    """Cleanly unbind the USB device for port before relay power-off. Returns True if attempted."""
    info = _find_usb_device_info(port)
    if not info:
        return False
    tty, usb_dev, driver, real = info
    _serial_log_write(log_f, "USB", "unbind {} ({} driver={} real={}) settle={}s".format(port, usb_dev, driver, real, settle).encode())
    try:
        # Try authorized 0 first (clean disconnect)
        auth = _usb_authorized_path(usb_dev)
        if os.path.exists(auth):
            try:
                with open(auth, "w") as f:
                    f.write("0")
                _serial_log_write(log_f, "USB", "authorized 0 {} ok".format(usb_dev).encode())
                time.sleep(settle)
                return True
            except PermissionError as e:
                _serial_log_write(log_f, "USB", "authorized 0 failed {}: {}".format(usb_dev, e).encode())
                print("WARNING: cannot unbind USB device {} ({}): --usb-unbind needs root; run with sudo or the USB CDC may wedge after repeated relay cycles.".format(usb_dev, e), file=sys.stderr)
            except Exception as e:
                _serial_log_write(log_f, "USB", "authorized 0 failed {}: {}".format(usb_dev, e).encode())
        # Fallback: driver unbind
        if driver:
            # need the interface name, e.g. 6-1.2:1.0
            iface = None
            # derive from real path: .../6-1.2:1.0/tty/...
            for p in real.split("/"):
                if ":" in p and p.startswith(usb_dev):
                    iface = p
                    break
            if iface:
                unbind = "/sys/bus/usb/drivers/{}/unbind".format(driver)
                try:
                    with open(unbind, "w") as f:
                        f.write(iface)
                    _serial_log_write(log_f, "USB", "driver unbind {}:{} ok".format(driver, iface).encode())
                    time.sleep(settle)
                    return True
                except Exception as e:
                    _serial_log_write(log_f, "USB", "driver unbind failed {}:{} {}".format(driver, iface, e).encode())
    except Exception as e:
        _serial_log_write(log_f, "USB", "unbind exception {}: {}".format(port, e).encode())
    return False


def _usb_bind_device(port, log_f=None, settle=5):
    """Re-bind the USB device for port after relay power-on. Returns True if attempted."""
    info = _find_usb_device_info(port)
    # If info is None, device not yet enumerated — try to re-authorize via hub
    if not info:
        # Try to find hub and re-authorize children
        # The ESP32 hub is 6-1, children are 6-1.2 and 6-1.3
        _serial_log_write(log_f, "USB", "bind: no info for {} (not enumerated yet)".format(port).encode())
        return False
    tty, usb_dev, driver, real = info
    _serial_log_write(log_f, "USB", "bind {} ({} driver={}) settle={}s".format(port, usb_dev, driver, settle).encode())
    try:
        auth = _usb_authorized_path(usb_dev)
        if os.path.exists(auth):
            try:
                # check current value
                with open(auth, "r") as f:
                    cur = f.read().strip()
                if cur == "0":
                    with open(auth, "w") as f:
                        f.write("1")
                    _serial_log_write(log_f, "USB", "authorized 1 {} ok".format(usb_dev).encode())
                    time.sleep(settle)
                    return True
            except Exception as e:
                _serial_log_write(log_f, "USB", "authorized 1 failed {}: {}".format(usb_dev, e).encode())
        if driver:
            iface = None
            for p in real.split("/"):
                if ":" in p and p.startswith(usb_dev):
                    iface = p
                    break
            if iface:
                bind = "/sys/bus/usb/drivers/{}/bind".format(driver)
                try:
                    with open(bind, "w") as f:
                        f.write(iface)
                    _serial_log_write(log_f, "USB", "driver bind {}:{} ok".format(driver, iface).encode())
                    time.sleep(settle)
                    return True
                except Exception as e:
                    _serial_log_write(log_f, "USB", "driver bind failed {}:{} {}".format(driver, iface, e).encode())
    except Exception as e:
        _serial_log_write(log_f, "USB", "bind exception {}: {}".format(port, e).encode())
    return False


def _usb_reset_hub(log_f=None, settle=5):
    """Reset the VIA hub (6-1) and xhci host if devices are wedged. Returns True if attempted."""
    _serial_log_write(log_f, "USB", "hub reset settle={}s".format(settle).encode())
    try:
        # Find xhci PCI device
        import glob as _glob
        xhci = None
        for p in _glob.glob("/sys/bus/pci/drivers/xhci_hcd/*"):
            b = os.path.basename(p)
            if ":" in b and "." in b:
                xhci = b
                break
        if xhci:
            _serial_log_write(log_f, "USB", "xhci unbind {}".format(xhci).encode())
            try:
                with open("/sys/bus/pci/drivers/xhci_hcd/unbind", "w") as f:
                    f.write(xhci)
                time.sleep(settle)
            except Exception as e:
                _serial_log_write(log_f, "USB", "xhci unbind failed {}: {}".format(xhci, e).encode())
            _serial_log_write(log_f, "USB", "xhci bind {}".format(xhci).encode())
            try:
                with open("/sys/bus/pci/drivers/xhci_hcd/bind", "w") as f:
                    f.write(xhci)
                time.sleep(settle)
                return True
            except Exception as e:
                _serial_log_write(log_f, "USB", "xhci bind failed {}: {}".format(xhci, e).encode())
        # Fallback: hub authorized toggle
        hub_auth = "/sys/bus/usb/devices/6-1/authorized"
        if os.path.exists(hub_auth):
            try:
                with open(hub_auth, "w") as f:
                    f.write("0")
                time.sleep(settle)
                with open(hub_auth, "w") as f:
                    f.write("1")
                time.sleep(settle)
                return True
            except Exception as e:
                _serial_log_write(log_f, "USB", "hub authorized toggle failed: {}".format(e).encode())
    except Exception as e:
        _serial_log_write(log_f, "USB", "hub reset exception: {}".format(e).encode())
    return False


def _usb_recovery(relay_port=None, device_port="/dev/ttyACM0", log_f=None, settle=5):
    """Automatic USB recovery when /dev/tty* returns Input/output error."""
    _serial_log_write(log_f, "USB", "recovery attempt relay={} dev={}".format(relay_port, device_port).encode())
    # Try relay power cycle if available
    if relay_port and os.path.exists(relay_port):
        try:
            _relay_write(relay_port, b"\xA0\x01\x00\xA1")
            time.sleep(2)
            _relay_write(relay_port, b"\xA0\x01\x01\xA2")
            time.sleep(settle)
            _serial_log_write(log_f, "USB", "relay recovery cycle done".encode())
        except Exception as e:
            _serial_log_write(log_f, "USB", "relay recovery failed: {}".format(e).encode())
    # Try hub/xhci reset
    _usb_reset_hub(log_f=log_f, settle=settle)
    time.sleep(settle)
    # Wait for ports to reappear
    for _ in range(10):
        if os.path.exists(device_port) and (relay_port is None or os.path.exists(relay_port)):
            _serial_log_write(log_f, "USB", "recovery ports reappeared".encode())
            return True
        time.sleep(1)
    return False


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


def _relay_reset(relay_port, device_port, boot_timeout=60, log_f=None, usb_unbind=False, usb_settle=5, usb_reset_hub=False, usb_recovery=True):
    """Power-cycle the device via a USB relay.

    The relay controls the device's power supply. Power off, wait for the
    board to drop, power back on, then poll the device serial port until it
    reappears and "Starting asyncio REPL..." confirms main.py ran to
    completion (same sentinel used by SerialBackend.hard_reset).

    The ESP32-S3 briefly enumerates as 303a:1001 (USB JTAG) before
    re-enumerating as 303a:4001 (CDC). Opening /dev/ttyACM0 during the
    1001 window wedges the port (SerialException: device reports readiness
    but returned no data) and, if we sleep 20s after the first appearance,
    we miss the boot sentinel entirely (it prints ~8s after the 4001
    appears). So we poll for the CDC PID 0x4001 specifically and settle
    only ~1s after it appears.
    """
    print("Power-cycling device via relay on {}...".format(relay_port))
    # Optional: cleanly unbind ttyACM0 before cutting power, so host xhci
    # doesn't wedge with -110 / unable to enumerate after many cycles.
    # Do NOT unbind the relay's own ttyUSB0 before OFF — we need it to send
    # the relay command. The relay and ESP32 share the VIA hub 6-1, but the
    # relay stays powered, so only the ESP32 needs pre-unbind.
    if usb_unbind:
        _serial_log_write(log_f, "USB", "pre-relay unbind {}".format(device_port).encode())
        _usb_unbind_device(device_port, log_f=log_f, settle=usb_settle)
    _serial_log_write(log_f, "REL", b"\xA0\x01\x00\xA1")
    try:
        _relay_write(relay_port, b"\xA0\x01\x00\xA1")
    except Exception as e:
        _serial_log_write(log_f, "REL", "relay write OFF failed: {}".format(e).encode())
        if "Input/output error" in str(e) or "Errno 5" in str(e):
            _serial_log_write(log_f, "USB", b"relay I/O error -> USB recovery")
            _usb_recovery(relay_port, device_port, log_f=log_f, settle=usb_settle)
            # retry once
            _relay_write(relay_port, b"\xA0\x01\x00\xA1")
    time.sleep(2)
    _serial_log_write(log_f, "REL", b"\xA0\x01\x01\xA2")
    try:
        _relay_write(relay_port, b"\xA0\x01\x01\xA2")
    except Exception as e:
        _serial_log_write(log_f, "REL", "relay write ON failed: {}".format(e).encode())
        if "Input/output error" in str(e) or "Errno 5" in str(e):
            _serial_log_write(log_f, "USB", b"relay I/O error -> USB recovery")
            _usb_recovery(relay_port, device_port, log_f=log_f, settle=usb_settle)
            _relay_write(relay_port, b"\xA0\x01\x01\xA2")
    if usb_unbind:
        _serial_log_write(log_f, "USB", "post-relay bind settle {}s".format(usb_settle).encode())
        time.sleep(usb_settle)
        # Re-bind is implicit via hub re-enumeration, but try explicit bind if still missing
        if not os.path.exists(device_port):
            _usb_bind_device(device_port, log_f=log_f, settle=usb_settle)
        if relay_port != device_port and not os.path.exists(relay_port):
            _usb_bind_device(relay_port, log_f=log_f, settle=1)
    if usb_reset_hub:
        _serial_log_write(log_f, "USB", "hub reset after relay".encode())
        _usb_reset_hub(log_f=log_f, settle=usb_settle)

    try:
        import serial as _serial
    except ImportError:
        raise SystemExit(
            "pyserial is required for --relayport: pip install pyserial"
        )

    print("waiting for device at {} to boot...".format(device_port))
    last_err = None

    # ── Phase 1: wait for CDC (0x4001) to appear, skip transient JTAG (0x1001) ─
    try:
        import serial.tools.list_ports as _list_ports
        _has_list_ports = True
    except ImportError:
        _has_list_ports = False

    def _pid_for_port():
        if not _has_list_ports:
            return None
        try:
            for p in _list_ports.comports():
                if p.device == device_port:
                    return p.pid
        except Exception:
            return None
        return None

    if _has_list_ports:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            pid = _pid_for_port()
            exists = os.path.exists(device_port)
            print(f"  [Phase 1] PID: {pid}, exists: {exists}, deadline in {deadline - time.monotonic():.1f}s")
            if pid == 0x4001:
                # CDC appeared — brief settle for USB stack, not 20s
                time.sleep(1.0)
                break
            if pid == 0x1001:
                # JTAG bootloader, will disappear and reappear as 4001
                time.sleep(0.2)
                continue
            if pid is None and exists:
                # list_ports hasn't caught up yet, or non-ESP device
                # If port exists but pid unknown, wait a bit and retry;
                # treat as potential 4001 after a short delay.
                time.sleep(0.2)
                # Check again — if still no pid after 1s, assume it's CDC
                # (fallback for kernels that don't report pid)
                pid2 = _pid_for_port()
                if pid2 is None and os.path.exists(device_port):
                    # Give the re-enumeration gap (1001 -> gap -> 4001) time
                    # to finish: peek a few times for 1001 before settling.
                    time.sleep(0.8)
                    pid3 = _pid_for_port()
                    if pid3 == 0x1001:
                        continue
                    if pid3 == 0x4001 or pid3 is None:
                        time.sleep(1.0)
                        break
                continue
            time.sleep(0.2)
        else:
            print(f"  [Phase 1] Timeout after 30s, falling back")
        # If we timed out waiting for 4001, fall through to the generic
        # outer retry loop below which will also wait for the port.

    else:
        # Fallback without list_ports: original settle but shorter (3s, not 20)
        for _ in range(10):
            if os.path.exists(device_port):
                time.sleep(3)
                break
            time.sleep(0.5)

    for _ in range(20):
        if not os.path.exists(device_port):
            time.sleep(1)
            continue
        # If we still see JTAG PID, skip this iteration
        if _has_list_ports:
            pid = _pid_for_port()
            if pid == 0x1001:
                time.sleep(0.3)
                continue
        try:
            ser = _serial.Serial(
                device_port, 115200, timeout=0.5, write_timeout=2,
            )
            try:
                t0 = time.monotonic()
                data = b""
                while time.monotonic() - t0 < min(boot_timeout, 60):
                    try:
                        chunk = ser.read(4096)
                    except _serial.SerialException as e:
                        # Disconnected during re-enumeration (1001->4001 gap)
                        last_err = e
                        break
                    if chunk:
                        data += chunk
                        _serial_log_write(log_f, "RX", chunk)
                        if b"Starting asyncio REPL..." in data:
                            _serial_log_write(
                                log_f, "RX",
                                b"<detected 'Starting asyncio REPL...'>\n",
                            )
                            time.sleep(10)
                            return True
                    time.sleep(0.1)
                # Inner timeout without marker — will retry outer loop
                # Keep last data tail for debugging if log_f set
                if data:
                    _serial_log_write(log_f, "RX", b"<no marker in this window, retry>\n")
            finally:
                ser.close()
        except (OSError, _serial.SerialException) as e:
            last_err = e
            # Automatic recovery on Input/output error (hub wedged)
            if usb_recovery and ("Input/output error" in str(e) or "Errno 5" in str(e) or "could not open port" in str(e)):
                _serial_log_write(log_f, "USB", "device not reachable I/O error -> recovery".encode())
                _usb_recovery(relay_port, device_port, log_f=log_f, settle=usb_settle)
                time.sleep(usb_settle)
            else:
                time.sleep(1)
    # Final recovery attempt before giving up
    if usb_recovery:
        _serial_log_write(log_f, "USB", b"device not reachable -> final recovery attempt")
        _usb_recovery(relay_port, device_port, log_f=log_f, settle=usb_settle)
        time.sleep(usb_settle)
        # One more quick poll for the device
        for _ in range(10):
            if os.path.exists(device_port):
                _serial_log_write(log_f, "USB", b"device reappeared after recovery, retrying boot poll")
                # Try one more boot poll
                try:
                    ser = _serial.Serial(device_port, 115200, timeout=0.5, write_timeout=2)
                    try:
                        t0 = time.monotonic()
                        data = b""
                        while time.monotonic() - t0 < 20:
                            try:
                                chunk = ser.read(4096)
                            except _serial.SerialException:
                                break
                            if chunk:
                                data += chunk
                                if b"Starting asyncio REPL..." in data:
                                    time.sleep(5)
                                    return True
                            time.sleep(0.1)
                    finally:
                        ser.close()
                except Exception:
                    pass
    raise RuntimeError(
        "Device at {} not reachable after relay reset: {}".format(
            device_port, last_err
        )
    )


def _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False, relay_port=None, log_f=None, usb_unbind=False, usb_reset_hub=False, usb_settle=5, usb_recovery=True):
    backend_kwargs = {}
    be = None
    if backend == "serial":
        port = os.environ.get("MPOS_TEST_PORT", "/dev/ttyACM0")
        backend_kwargs = {"port": port, "reset": False}
    else:
        backend_kwargs = {"heapsize": "32M"}
        backend_kwargs["binary"] = _resolve_binary()

    def _line_cb(line_bytes):
        sys.stdout.write(line_bytes.decode("utf-8", errors="replace"))
        sys.stdout.flush()

    try:
        if reset and backend == "serial":
            if relay_port:
                _relay_reset(relay_port, port, log_f=log_f, usb_unbind=usb_unbind, usb_settle=usb_settle, usb_reset_hub=usb_reset_hub, usb_recovery=usb_recovery)
            else:
                if usb_unbind:
                    _serial_log_write(log_f, "USB", "reset without relay: unbind/bind {}".format(port).encode())
                    _usb_unbind_device(port, log_f=log_f, settle=usb_settle)
                    time.sleep(usb_settle)
                    _usb_bind_device(port, log_f=log_f, settle=usb_settle)
                    # Wait for re-enumeration
                    for _ in range(10):
                        if os.path.exists(port):
                            break
                        time.sleep(1)
                    time.sleep(usb_settle)
                if usb_reset_hub:
                    _usb_reset_hub(log_f=log_f, settle=usb_settle)
                print("Hard-resetting device...")
                try:
                    be.hard_reset()
                except Exception as e:
                    _serial_log_write(log_f, "USB", "hard_reset failed: {}".format(e).encode())
                    if usb_recovery and ("Input/output error" in str(e) or "Errno 5" in str(e) or "could not open port" in str(e)):
                        _serial_log_write(log_f, "USB", b"hard_reset I/O error -> recovery")
                        _usb_recovery(relay_port, port, log_f=log_f, settle=usb_settle)
                        be.hard_reset()
        # Create backend AFTER relay reset to avoid stale serial connection
        if backend == "serial":
            port = os.environ.get("MPOS_TEST_PORT", "/dev/ttyACM0")
            backend_kwargs = {"port": port, "reset": False}
            be = SerialBackend(**backend_kwargs)
        else:
            backend_kwargs = {"heapsize": "32M"}
            backend_kwargs["binary"] = _resolve_binary()
            be = ProcessBackend(**backend_kwargs)
        # Ensure backend is started (initializes repl for serial backend)
        be.start()
        # Give the serial connection time to stabilize after reset/start
        # ESP32-S3 USB CDC can be unstable after power-on; wait longer
        time.sleep(10)
        _serial_log_write(
            log_f, "TST",
            b"--- " + os.path.basename(test_path).encode() + b" ---\n",
        )
        passed, out = be.run_test_file(
            test_path, tests_dir=tests_dir, timeout=timeout,
            line_callback=_line_cb,
            **({"coverage": coverage} if backend == "process" else {})
        )
        _serial_log_write(log_f, "RX", out)
    finally:
        if be is not None:
            be.stop()

    if log_path:
        with open(log_path, "ab") as f:
            f.write(out)

    return passed, out


def _is_usb_wedge(err):
    """Recognise the ESP32-S3 USB CDC "wedge": the port is still present and
    openable but the device has stopped consuming writes, so the next write
    times out. This is NOT a test crash — a relay power-cycle recovers it."""
    txt = str(err)
    if ("Write timeout" in txt
            or "Input/output error" in txt
            or "Errno 5" in txt
            or "could not open port" in txt
            or "device reports readiness" in txt
            or "No such device" in txt):
        return True
    try:
        import serial as _serial
        return isinstance(err, _serial.SerialException)
    except ImportError:
        return False


def _run_with_retry(test_path, backend, tests_dir, timeout, log_path, reset=False, coverage=False, relay_port=None, log_f=None, usb_unbind=False, usb_reset_hub=False, usb_settle=5, usb_recovery=True):
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print("Retry attempt {} for {}".format(attempt, test_path))

        try:
            passed, out = _run_one_test(test_path, backend, tests_dir, timeout, log_path, reset, coverage, relay_port, log_f, usb_unbind, usb_reset_hub, usb_settle, usb_recovery)
        except Exception as e:
            if _is_usb_wedge(e):
                # Not a crash — the CDC link wedged. Power-cycling via relay
                # (the next _run_one_test re-runs _relay_reset) recovers it.
                _serial_log_write(log_f, "USB", "wedge on {}: {}".format(os.path.basename(test_path), e).encode())
                print("WARNING: USB CDC wedged ({}) — power-cycling and retrying...".format(e))
                if attempt < MAX_RETRIES:
                    continue
                out = "<USB CDC wedged after {} attempts: {}>\n".format(MAX_RETRIES, e).encode()
                return False, out
            raise

        out_str = out.decode("utf-8", errors="replace")

        if passed:
            return True, out
        if "TEST WAS A FAILURE" in out_str:
            return False, out
        print("Test crashed — retrying...")
    return False, out


def _run_tests(test_files, backend, tests_dir, timeout, reset=False, coverage=False, relay_port=None, logserial=None, usb_unbind=False, usb_reset_hub=False, usb_settle=5, usb_recovery=True):
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
            ok, out = _run_with_retry(f, backend, tests_dir, timeout, log_path, reset, coverage, relay_port, log_f, usb_unbind, usb_reset_hub, usb_settle, usb_recovery)
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
    effective_port = port or os.environ.get("MPOS_TEST_PORT")
    if effective_port:
        cmd.extend(["--serial-port", effective_port])
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
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume the full test suite from the provided test file(s). "
             "Discovers all test files alphabetically and runs from the "
             "alphabetically first provided test onward.",
    )
    parser.add_argument(
        "--usb-unbind", action="store_true",
        help="Before relay power-off, cleanly unbind /dev/ttyACM0 (and relay) via sysfs authorized 0, then re-bind after power-on. Reduces xhci -110 wedging after many relay cycles. 5s settle by default (see --usb-settle). Works with --reset even without --relayport (re-enumerates USB between tests).",
    )
    parser.add_argument(
        "--usb-reset-hub", action="store_true",
        help="After relay power-on, reset the VIA hub / xhci host (unbind/bind 0000:01:00.0) to recover from wedged hub after many cycles.",
    )
    parser.add_argument(
        "--usb-settle", type=int, default=5,
        help="Seconds to wait after each USB unbind/bind (default: 5). Less aggressive timing stabilizes re-enumeration.",
    )
    parser.add_argument(
        "--no-usb-recovery", dest="usb_recovery", action="store_false",
        help="Disable automatic USB recovery on Input/output error (relay I/O error -> xhci reset + relay retry). Enabled by default.",
    )
    parser.set_defaults(usb_recovery=True)
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

    if args.resume:
        if not args.test_files:
            print("ERROR: --resume requires at least one test file to resume from")
            sys.exit(1)
        provided = {}
        for f in args.test_files:
            path = os.path.abspath(f)
            if not os.path.isfile(path):
                print("ERROR: {} is not a file".format(path))
                sys.exit(1)
            provided[os.path.basename(path)] = True
        all_files = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
        all_files = [f for f in all_files if not os.path.basename(f).startswith("notondevice_")]
        if args.ondevice:
            all_files = [f for f in all_files if os.path.basename(f) not in ONDEVICE_SKIP]
        start_idx = None
        for i, f in enumerate(all_files):
            if os.path.basename(f) in provided:
                start_idx = i
                break
        if start_idx is None:
            print("ERROR: provided test file(s) not found in discovered test suite")
            sys.exit(1)
        test_files = all_files[start_idx:]
        print("Resuming from {} ({} test(s) remaining)".format(
            os.path.basename(test_files[0]), len(test_files),
        ))
    elif args.test_files:
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
        usb_unbind=args.usb_unbind, usb_reset_hub=args.usb_reset_hub,
        usb_settle=args.usb_settle, usb_recovery=args.usb_recovery,
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
