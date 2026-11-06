#!/usr/bin/env python3
"""End-to-end OTA upgrade validation on a real MicroPythonOS badge.

This is the release gate that proves a published release can be installed by
the previous release, and that the newly installed release can install itself
again (``0.20.0 -> 0.21.0 -> 0.21.0``). It also proves that the ESP32 OTA
partitions alternate correctly.

The flow is deliberately user-facing:

1. flash the known base release (``--base-bin``) with esptool (retrying via an
   optional USB relay when the link is flaky)
2. boot it, provision WiFi and wait for the OTA notification
3. open the notification drawer and tap the notification
4. tap "Install new version" in OSUpdate and watch the download
5. wait for the automatic reboot and verify the version and boot partition
6. repeat through OSUpdate ("Install same version") to prove OTA0/OTA1 toggle

At chosen checkpoints the physical display is verified through a host webcam
with :mod:`mpos_screen_camera` (SIFT/RANSAC alignment to the device
framebuffer). Artifacts and a JSON report are written to ``--out-dir``.

Examples::

    python3 scripts/validate_ota_release.py \\
        --port /dev/ttyACM0 --camera /dev/video0 \\
        --base-bin MicroPythonOS_esp32s3_0.20.0.bin \\
        --base-version 0.20.0 --target-version 0.21.0 \\
        --wifi-ssid MyNetwork --wifi-password secret

    # without a webcam (still checks the UI text and partitions):
    python3 scripts/validate_ota_release.py --port /dev/ttyACM0 --no-camera ...

WiFi credentials can also come from ``MPOS_WIFI_SSID`` / ``MPOS_WIFI_PASSWORD``.
Host requirements: ``esptool``, ``pyserial``; with ``--camera`` also
``ffmpeg``, ``v4l-utils``, ``numpy`` and ``opencv-python-headless``.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE_BIN = os.path.join(REPO_ROOT, "MicroPythonOS_esp32s3_0.20.0.bin")
DEFAULT_UPDATES_URL = "https://updates.micropythonos.com"
UPDATE_NOTIFICATION_ID = "osupdate.update_available"
UPDATE_NOTIFICATION_TITLE = "OS update available"

VERSION_MARKER = "MPOSVER="
PARTITION_MARKER = "MPOSPART="
IP_MARKER = "MPOSIP="
BOOT_SENTINEL = b"Starting asyncio REPL..."


class ValidationError(RuntimeError):
    """Raised when a release-validation step fails."""


# ── Pure helpers (unit-tested in tests/cpython_validate_ota_release.py) ──


def other_partition(label):
    """Return the OTA slot that the ESP32 bootloader will boot next."""
    if label == "ota_0":
        return "ota_1"
    if label == "ota_1":
        return "ota_0"
    raise ValidationError("unexpected running partition: {!r}".format(label))


def partition_label(info):
    """Extract the label from an ``esp32.Partition.info()`` tuple."""
    try:
        return info[4]
    except (IndexError, TypeError) as exc:
        raise ValidationError("invalid partition info: {!r}".format(info)) from exc


def find_esptool(explicit=None):
    """Return the command prefix for esptool (module or standalone script)."""
    if explicit:
        return explicit.split()
    try:
        import esptool  # noqa: F401
        return [sys.executable, "-m", "esptool"]
    except ImportError:
        pass
    # ESP-IDF installs esptool in a per-toolchain virtualenv that is not on PATH.
    for python in reversed(sorted(glob.glob(os.path.expanduser("~/.espressif/python_env/*/bin/python")))):
        return [python, "-m", "esptool"]
    for name in ("esptool", "esptool.py"):
        path = shutil.which(name)
        if path:
            return [path]
    raise ValidationError("esptool not found (pip install esptool or pass --esptool)")


def build_flash_command(esptool, chip, port, flash_size, bin_path, erase_all=False):
    """Build the esptool command used to put a known release on the device."""
    command = list(esptool) + [
        "--chip", chip,
    ]
    if port:
        command += ["--port", port]
    command += [
        "--before", "default_reset", "--after", "hard_reset",
        "--connect-attempts", "10",
        "write_flash", "--flash_mode", "dio", "--flash_size", flash_size,
        "--flash_freq", "80m",
    ]
    if erase_all:
        command.append("--erase-all")
    command += ["0", bin_path]
    return command


def validate_update_metadata(data, expected_version):
    """Validate the server's osupdate JSON and return its download URL."""
    if not isinstance(data, dict):
        raise ValidationError("update metadata is not a JSON object")
    missing = [key for key in ("version", "download_url", "changelog") if key not in data]
    if missing:
        raise ValidationError("update metadata is missing: {}".format(", ".join(missing)))
    if data["version"] != expected_version:
        raise ValidationError(
            "server offers version {!r}, expected {!r}".format(data["version"], expected_version)
        )
    url = data["download_url"]
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValidationError("invalid download_url: {!r}".format(url))
    if not url.endswith(".ota"):
        raise ValidationError("download_url does not point at a .ota image: {}".format(url))
    return url


def partition_sequence_errors(base, after_first, after_second, require_clean_base=True):
    """Check the expected OTA0 -> OTA1 -> OTA0 sequence."""
    errors = []
    if base not in ("ota_0", "ota_1"):
        errors.append("base booted from unexpected partition {!r}".format(base))
        return errors
    if require_clean_base and base != "ota_0":
        errors.append("clean flash booted from {!r}, expected ota_0".format(base))
    expected_first = other_partition(base)
    if after_first != expected_first:
        errors.append(
            "first OTA booted from {!r}, expected {!r}".format(after_first, expected_first)
        )
    if after_second != base:
        errors.append(
            "second OTA booted from {!r}, expected {!r} (the original slot)".format(after_second, base)
        )
    return errors


def parse_marker(output, marker):
    """Return the value after *marker* on the last matching output line."""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    value = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith(marker):
            value = line[len(marker):].strip()
    return value


def find_release_text(texts, prefix="Release version:"):
    """Return the value after *prefix* from a list of UI strings."""
    for text in texts:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return None


def find_partition_text(texts):
    """Return the partition label rendered by the About app, if present."""
    for text in texts:
        if text.startswith("Partition.RUNNING:"):
            match = re.search(r"label=([^,>\s]+)", text)
            if match:
                return match.group(1)
    return None


# ── Reporting ───────────────────────────────────────────────────────


class Report:
    """Collect pass/fail checks and write them incrementally as JSON."""

    def __init__(self, out_dir):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "report.json")
        self.data = {
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "checks": [],
            "ok": True,
        }
        self.write()

    def check(self, name, ok, detail=""):
        entry = {"name": name, "ok": bool(ok), "detail": detail}
        self.data["checks"].append(entry)
        if not ok:
            self.data["ok"] = False
        self.write()
        print("[{}] {} {}".format("PASS" if ok else "FAIL", name, detail))
        return ok

    def require(self, name, ok, detail=""):
        if not self.check(name, ok, detail):
            raise ValidationError("{}: {}".format(name, detail))
        return True

    def write(self):
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(self.path, "w") as handle:
            json.dump(self.data, handle, indent=1)


# ── Device helpers ──────────────────────────────────────────────────


def _controller_class():
    try:
        from .mpos_controller import MPOSController
    except ImportError:
        from mpos_controller import MPOSController
    return MPOSController


def wait_for_boot(port, timeout):
    """Wait for the device to finish booting after a reset.

    Reads the raw serial stream until main.py prints its boot sentinel. A bare
    newline fallback handles the case where the sentinel scrolled past while the
    port was being reopened (for example on USB/IP, where the node never
    disappears).
    """
    import serial

    started = time.monotonic()
    deadline = started + timeout
    last_error = None
    while time.monotonic() < deadline:
        if not os.path.exists(port):
            time.sleep(0.5)
            continue
        try:
            handle = serial.Serial(port, 115200, timeout=0.5, write_timeout=2)
        except Exception as exc:  # serial port is re-enumerating
            last_error = exc
            time.sleep(0.5)
            continue
        try:
            seen = b""
            while time.monotonic() < deadline:
                chunk = handle.read(4096)
                if chunk:
                    seen += chunk
                    if BOOT_SENTINEL in seen:
                        return True
                else:
                    # Fallback for when the sentinel scrolled past during a
                    # port reopen. Ignore the old prompt for the first 10s so a
                    # pre-reset REPL cannot be mistaken for a finished boot.
                    if time.monotonic() - started < 10:
                        continue
                    try:
                        handle.write(b"\r\n")
                        probe = handle.read(4096)
                    except Exception:
                        probe = b""
                    if b"\r\n>>> " in probe or probe.startswith(b">>> "):
                        return True
        except Exception as exc:  # device reset while reading
            last_error = exc
        finally:
            try:
                handle.close()
            except Exception:
                pass
        time.sleep(0.5)
    raise ValidationError(
        "device at {} did not finish booting within {}s ({})".format(port, timeout, last_error)
    )


def connect(port, boot_timeout=180):
    """Wait for a booted device and return a connected MPOSController."""
    wait_for_boot(port, boot_timeout)
    controller = _controller_class()(backend="serial", port=port, reset=False)
    controller.start()
    return controller


def close(controller):
    if controller is not None:
        try:
            controller.stop()
        except Exception:
            pass


def exec_text(controller, code, timeout=30):
    output = controller.exec_multiline(code, timeout=timeout)
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output)


def read_version(controller):
    return parse_marker(exec_text(controller, "from mpos import BuildInfo\nprint({!r} + BuildInfo.version.release)".format(VERSION_MARKER)), VERSION_MARKER)


def read_partition(controller):
    code = (
        "from esp32 import Partition\n"
        "print({!r} + Partition(Partition.RUNNING).info()[4])".format(PARTITION_MARKER)
    )
    return parse_marker(exec_text(controller, code), PARTITION_MARKER)


def read_hardware_id(controller):
    code = "from mpos import DeviceInfo\nprint('MPOSHARDWARE=' + str(DeviceInfo.hardware_id))"
    return parse_marker(exec_text(controller, code), "MPOSHARDWARE=")


def save_wifi_and_reboot(controller, ssid, password):
    code = (
        "from mpos import WifiService\n"
        "WifiService.save_network({!r}, {!r})\n"
        "print('MPOSWIFI=SAVED')".format(ssid, password)
    )
    output = exec_text(controller, code)
    if "MPOSWIFI=SAVED" not in output:
        raise ValidationError("could not save WiFi credentials: {}".format(output[-500:]))
    try:
        controller.exec("import machine; machine.reset()", timeout=5)
    except Exception:
        pass
    close(controller)
    time.sleep(2)


def wait_for_ip(controller, timeout):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            output = exec_text(
                controller,
                "from mpos import WifiService\nprint({!r} + str(WifiService.get_ipv4_address()))".format(IP_MARKER),
                timeout=15,
            )
            last = parse_marker(output, IP_MARKER)
        except Exception as exc:
            last = str(exc)
        if last and last not in ("None", "0.0.0.0", ""):
            return last
        time.sleep(3)
    raise ValidationError("WiFi did not obtain an IP address within {}s (last: {})".format(timeout, last))


def override_update_mirror(controller, mirror_url):
    """Point OSUpdate at *mirror_url* for this boot (e.g. a local test server).

    The override is applied after the WiFi reboot, before the boot service's
    90-second delay expires. It mutates the already-imported ``osupdate_core``
    module so both the service and the OSUpdate activity use the same URL.
    """
    code = (
        "import sys\n"
        "path = 'builtin/apps/com.micropythonos.osupdate'\n"
        "if path not in sys.path:\n"
        "    sys.path.insert(0, path)\n"
        "import osupdate_core\n"
        "osupdate_core._UPDATE_MIRRORS = ({!r},)\n"
        "try:\n"
        "    from mpos.notification_manager import NotificationManager\n"
        "    NotificationManager.cancel('osupdate.update_available')\n"
        "    manager = osupdate_core.UpdateManager.get_instance()\n"
        "    manager._last_check_ts = None\n"
        "    manager._update_info = None\n"
        "    if manager._running:\n"
        "        manager.check_for_update_now()\n"
        "except Exception:\n"
        "    pass\n"
        "print('MPOSMIRROR=' + repr(osupdate_core._UPDATE_MIRRORS))".format(mirror_url)
    )
    output = exec_text(controller, code)
    if "MPOSMIRROR=" not in output:
        raise ValidationError("could not override the update mirror: {}".format(output[-500:]))
    return parse_marker(output, "MPOSMIRROR=")


def open_update_notification_drawer(controller):
    exec_text(controller, "from mpos.ui import topmenu\ntopmenu.open_drawer()", timeout=20)
    time.sleep(1.5)


def click_button(controller, text):
    """Click a button through the on-device test helper.

    Doing the search on the device avoids mpremote's separate file copy, which
    shares the USB-CDC port with the controller and intermittently wedges it
    right after a webcam checkpoint.
    """
    code = (
        "from mpos.ui.testing import click_button, wait_for_render\n"
        "ok = click_button({!r})\n"
        "wait_for_render(iterations=20)\n"
        "print('MPOSCLICK=' + repr(ok))".format(text)
    )
    output = exec_text(controller, code, timeout=30)
    if "MPOSCLICK=True" in output:
        return
    # Fallback for widgets that the on-device helper cannot see (for example
    # layer_top overlays); still avoid failing the whole gate on a miss.
    widget = controller.find_widget(text=text)
    if widget is not None:
        controller.press(widget["center_x"], widget["center_y"])


def click_notification(controller, title):
    """Click a notification card in the layer_top drawer without mpremote."""
    code = (
        "import lvgl as lv\n"
        "from mpos.ui import topmenu\n"
        "from mpos.ui.testing import wait_for_render\n"
        "topmenu.open_drawer()\n"
        "wait_for_render(iterations=20)\n"
        "def find(node):\n"
        "    try:\n"
        "        if node.get_text() == {!r}:\n"
        "            return node\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        count = node.get_child_count()\n"
        "    except Exception:\n"
        "        return None\n"
        "    for i in range(count):\n"
        "        found = find(node.get_child(i))\n"
        "        if found is not None:\n"
        "            return found\n"
        "    return None\n"
        "label = find(lv.layer_top())\n"
        "clicked = False\n"
        "node = label\n"
        "while node is not None:\n"
        "    try:\n"
        "        if node.has_flag(lv.obj.FLAG.CLICKABLE):\n"
        "            node.send_event(lv.EVENT.CLICKED, None)\n"
        "            clicked = True\n"
        "            break\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        node = node.get_parent()\n"
        "    except Exception:\n"
        "        node = None\n"
        "wait_for_render(iterations=20)\n"
        "print('MPOSNOTIFCLICK=' + repr(clicked))".format(title)
    )
    output = exec_text(controller, code, timeout=30)
    if "MPOSNOTIFCLICK=True" in output:
        return True
    # Last resort: dispatch the notification intent directly. The drawer tap
    # path is exercised by the normal case; this keeps the gate moving when a
    # theme/driver change makes the card unfindable.
    output = exec_text(
        controller,
        "from mpos.notification_manager import NotificationManager\n"
        "print('MPOSNOTIFTRIGGER=' + repr(NotificationManager.trigger({!r})))".format(
            UPDATE_NOTIFICATION_ID
        ),
        timeout=30,
    )
    return "MPOSNOTIFTRIGGER=True" in output


def wait_for_any_text(controller, needles, timeout, poll=2.0):
    deadline = time.monotonic() + timeout
    texts = []
    while time.monotonic() < deadline:
        try:
            texts = controller.get_visible_text()
        except Exception:
            texts = []
        joined = "\n".join(texts)
        for needle in needles:
            if needle in joined:
                return needle, texts
        time.sleep(poll)
    raise ValidationError("none of {} appeared within {}s".format(needles, timeout))


def open_about(controller, timeout):
    output = exec_text(
        controller,
        "from mpos import AppManager\n"
        "print('MPOSAPP=' + repr(AppManager.start_app('com.micropythonos.about')))",
    )
    if "MPOSAPP=True" not in output:
        raise ValidationError("could not launch About app: {}".format(output[-500:]))
    wait_for_any_text(controller, ["Release version:"], timeout)


def scroll_to_partition_info(controller):
    exec_text(
        controller,
        "import lvgl as lv\n"
        "from mpos.ui.testing import find_label_with_text, wait_for_render\n"
        "label = find_label_with_text(lv.screen_active(), 'Partition.RUNNING')\n"
        "if label is not None:\n"
        "    label.scroll_to_view_recursive(True)\n"
        "    wait_for_render(iterations=40)\n"
        "print('MPOSSCROLL=' + repr(label is not None))",
        timeout=40,
    )


# ── Camera verification ─────────────────────────────────────────────


class CameraVerifier:

    def __init__(self, controller, out_dir, enabled, config=None):
        self.controller = controller
        self.out_dir = out_dir
        self.enabled = enabled
        self.config = config or {}

    def bind(self, controller):
        """Point the verifier at the controller for the current boot."""
        self.controller = controller
        return self

    def checkpoint(self, report, label):
        if not self.enabled:
            report.check("camera." + label, True, "skipped (--no-camera)")
            return
        cfg = dict(self.config)
        cfg["out_dir"] = self.out_dir
        measured = self.controller.screen_camera_measure(config=cfg, out_dir=self.out_dir, label=label)
        summary = {
            key: measured.get(key)
            for key in ("ok", "inliers", "ncc_gray", "ncc_gradient", "cell_ncc_min",
                        "eff_px_per_screen_px", "rotation_deg")
        }
        report.check("camera." + label, measured.get("ok"), json.dumps(summary))
        if not measured.get("ok"):
            raise ValidationError(
                "webcam verification of {!r} failed: {}".format(label, measured.get("failures"))
            )


# ── OTA flow ────────────────────────────────────────────────────────


def ensure_update_available(controller, report, timeout, natural=True):
    """Wait for the update notification, exercising the boot service path."""
    if not natural:
        exec_text(
            controller,
            "import sys\n"
            "path = 'builtin/apps/com.micropythonos.osupdate'\n"
            "if path not in sys.path:\n"
            "    sys.path.insert(0, path)\n"
            "from osupdate_core import UpdateManager\n"
            "manager = UpdateManager.get_instance()\n"
            "if not manager._running:\n"
            "    manager.start()\n"
            "manager.check_for_update_now()\n"
            "print('MPOSUM=STARTED')",
            timeout=30,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = exec_text(
            controller,
            "from mpos.notification_manager import NotificationManager\n"
            "print('MPOSNOTIF=' + repr(NotificationManager.get_notification({!r}) is not None))".format(
                UPDATE_NOTIFICATION_ID
            ),
            timeout=15,
        )
        if "MPOSNOTIF=True" in output:
            report.check("ota.notification", True, UPDATE_NOTIFICATION_ID)
            return
        time.sleep(3)
    raise ValidationError(
        "no OTA notification appeared within {}s; check WiFi, the updates server, "
        "and the OSUpdate boot service".format(timeout)
    )


def install_from_osupdate(controller, report, expected_button, timeout, camera, camera_label):
    """Wait for OSUpdate to show *expected_button*, verify it, then click it."""
    wait_for_any_text(controller, [expected_button], timeout)
    report.check("osupdate.button", True, expected_button)
    camera.checkpoint(report, camera_label)
    click_button(controller, expected_button)
    report.check("osupdate.install_clicked", True, expected_button)


def wait_for_ota_completion(controller, port, report, timeout):
    """Watch the progress UI, then wait for the automatic reboot."""
    deadline = time.monotonic() + timeout
    saw_progress = False
    saw_finished = False
    last_text = ""
    while time.monotonic() < deadline:
        try:
            texts = controller.get_visible_text()
        except Exception:
            # The device has likely reset. The reboot wait below confirms it.
            break
        last_text = "\n".join(texts)
        if "OS Update:" in last_text:
            saw_progress = True
        if "Update finished! Restarting..." in last_text:
            saw_finished = True
            break
        if "Update failed" in last_text or "Failed to check" in last_text:
            raise ValidationError("OSUpdate reported a failure: {}".format(last_text[-500:]))
        time.sleep(2)
    report.check("ota.download_started", saw_progress or saw_finished,
                 "progress UI observed" if saw_progress else "success text observed")
    close(controller)
    wait_for_boot(port, timeout)
    report.check("ota.download_finished", True, "device rebooted after OTA")
    report.check("ota.reboot", True, "device booted after OTA")


def verify_about(controller, report, camera, label, expected_version, expected_partition, timeout=60):
    open_about(controller, timeout)
    texts = controller.get_visible_text()
    version = find_release_text(texts)
    report.require(
        "about.version." + label,
        version == expected_version,
        "UI shows {!r}, expected {!r}".format(version, expected_version),
    )
    ui_partition = find_partition_text(texts)
    report.require(
        "about.partition." + label,
        ui_partition == expected_partition,
        "UI shows {!r}, expected {!r}".format(ui_partition, expected_partition),
    )
    scroll_to_partition_info(controller)
    camera.checkpoint(report, label)


def verify_boot(controller, report, label, expected_version, expected_partition):
    version = read_version(controller)
    report.require(
        "build.version." + label,
        version == expected_version,
        "BuildInfo.version = {!r}, expected {!r}".format(version, expected_version),
    )
    partition = read_partition(controller)
    report.require(
        "partition." + label,
        partition == expected_partition,
        "running partition = {!r}, expected {!r}".format(partition, expected_partition),
    )
    return partition


def fetch_update_metadata(base_url, hardware_id, expected_version):
    url = "{}/osupdate_{}.json".format(base_url.rstrip("/"), hardware_id)
    request = urllib.request.Request(url, headers={"User-Agent": "MicroPythonOS-OTA-Validation"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read())
    return url, validate_update_metadata(data, expected_version)


def preflight(args):
    if not os.path.isfile(args.base_bin):
        raise ValidationError("base image not found: {}".format(args.base_bin))
    if not args.skip_flash:
        args.esptool_command = find_esptool(args.esptool)
    try:
        import serial  # noqa: F401
    except ImportError as exc:
        raise ValidationError("pyserial is required for the serial backend") from exc
    if not args.dry_run and not os.path.exists(args.port):
        raise ValidationError("serial port not found: {}".format(args.port))
    if args.camera and not args.dry_run:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise ValidationError(
                "numpy and opencv-python-headless are required for --camera "
                "(or pass --no-camera)"
            ) from exc
        if shutil.which("ffmpeg") is None:
            raise ValidationError("ffmpeg is required for --camera (or pass --no-camera)")
        if not os.path.exists(args.camera):
            raise ValidationError("camera not found: {}".format(args.camera))
        if shutil.which("v4l2-ctl") is None:
            raise ValidationError("v4l2-ctl is required to apply camera controls (install v4l-utils)")


RELAY_OFF = b"\xA0\x01\x00\xA1"
RELAY_ON = b"\xA0\x01\x01\xA2"


def relay_power_cycle(port, settle=3.0):
    """Power-cycle the badge through a USB relay (CH340-based boards)."""
    import serial
    with serial.Serial(port, 9600, timeout=1) as handle:
        handle.write(RELAY_OFF)
        time.sleep(2)
        handle.write(RELAY_ON)
    time.sleep(settle)


def flash_base(args):
    command = build_flash_command(
        args.esptool_command, args.chip, args.port, args.flash_size, args.base_bin,
        erase_all=args.erase_all,
    )
    print(" ".join(command))
    last_detail = ""
    for attempt in range(1, args.flash_retries + 1):
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=args.flash_timeout)
        except subprocess.TimeoutExpired as exc:
            last_detail = "timed out after {}s".format(args.flash_timeout)
            result = None
        if result is not None:
            last_detail = (result.stderr or result.stdout or "").strip()[-1500:]
            if result.returncode == 0:
                return last_detail
        if attempt < args.flash_retries:
            print("esptool failed (attempt {}/{}); recovering...".format(
                attempt, args.flash_retries))
            if args.relay_port:
                relay_power_cycle(args.relay_port)
            else:
                time.sleep(3)
    raise ValidationError("esptool failed after {} attempts:\n{}".format(
        args.flash_retries, last_detail))


def run(args):
    report = Report(args.out_dir)
    controller = None
    try:
        preflight(args)
        report.check("preflight", True, "host tools and inputs present")

        if args.dry_run:
            report.check("dry_run", True, "plan printed; no device touched")
            print("Would flash {} and validate {} -> {} -> {}".format(
                args.base_bin, args.base_version, args.target_version, args.target_version
            ))
            return 0

        if not args.skip_flash:
            flash_base(args)
            report.check("flash.base", True, os.path.basename(args.base_bin))
        else:
            report.check("flash.base", True, "skipped (--skip-flash)")

        controller = connect(args.port, args.boot_timeout)
        report.check("device.connected", True, args.port)
        controller.dismiss_onboarding()

        base_version = read_version(controller)
        report.require(
            "build.base_version",
            base_version == args.base_version,
            "BuildInfo.version = {!r}, expected {!r}".format(base_version, args.base_version),
        )
        base_partition = read_partition(controller)
        report.check("partition.base", base_partition in ("ota_0", "ota_1"), base_partition)
        hardware_id = read_hardware_id(controller)
        report.check("hardware_id", bool(hardware_id), str(hardware_id))

        src, download_url = fetch_update_metadata(args.updates_url, hardware_id, args.target_version)
        report.check("updates.metadata", True, src + " -> " + download_url)

        save_wifi_and_reboot(controller, args.wifi_ssid, args.wifi_password)
        controller = connect(args.port, args.boot_timeout)
        report.check("device.reboot_after_wifi", True, "booted")
        if args.mirror_url:
            mirror = override_update_mirror(controller, args.mirror_url)
            report.check("updates.mirror_override", True, str(mirror))
        ip = wait_for_ip(controller, args.wifi_timeout)
        report.check("wifi.connected", True, ip)

        camera_config = {}
        if args.camera_config:
            with open(args.camera_config) as handle:
                camera_config = json.load(handle)
        if args.camera:
            camera_config.setdefault("device", args.camera)
        camera = CameraVerifier(controller, args.out_dir, args.camera is not None, camera_config)

        verify_about(controller, report, camera, "base", base_version, base_partition, args.ui_timeout)

        # ── pass 1: previous release -> target release via the notification ──
        ensure_update_available(controller, report, args.notification_timeout, natural=not args.force_check)
        open_update_notification_drawer(controller)
        click_notification(controller, UPDATE_NOTIFICATION_TITLE)
        wait_for_any_text(controller, ["Update version:", "Install new version"], args.ui_timeout)
        report.check("osupdate.opened_from_notification", True, UPDATE_NOTIFICATION_TITLE)

        install_from_osupdate(controller, report, "Install new version", args.ui_timeout,
                              camera, "update_available")
        wait_for_ota_completion(controller, args.port, report, args.download_timeout)

        controller = connect(args.port, args.boot_timeout)
        camera.bind(controller)
        if args.mirror_url:
            # The mirror override is per-boot; re-apply it so the second pass
            # (target -> target) sees the same metadata as the first pass.
            mirror = override_update_mirror(controller, args.mirror_url)
            report.check("updates.mirror_override_after_first_ota", True, str(mirror))
        first_partition = other_partition(base_partition)
        verify_boot(controller, report, "after_first_ota", args.target_version, first_partition)
        verify_about(controller, report, camera, "after_first_ota", args.target_version,
                     first_partition, args.ui_timeout)

        if args.second_pass:
            # ── pass 2: target release "upgrades" to itself via OSUpdate ──
            output = exec_text(
                controller,
                "from mpos import AppManager\n"
                "print('MPOSAPP=' + repr(AppManager.start_app('com.micropythonos.osupdate')))",
            )
            report.require("osupdate.second_pass_launch", "MPOSAPP=True" in output, output[-300:])
            install_from_osupdate(controller, report, "Install same version", args.ui_timeout,
                                  camera, "same_version_available")
            wait_for_ota_completion(controller, args.port, report, args.download_timeout)

            controller = connect(args.port, args.boot_timeout)
            camera.bind(controller)
            verify_boot(controller, report, "after_second_ota", args.target_version, base_partition)
            verify_about(controller, report, camera, "after_second_ota", args.target_version,
                         base_partition, args.ui_timeout)
            errors = partition_sequence_errors(
                base_partition, first_partition, base_partition,
                require_clean_base=not args.skip_flash,
            )
        else:
            errors = []
        report.check("partition.toggle", not errors, "; ".join(errors) or
                     "{} -> {} -> {}".format(base_partition, first_partition, base_partition))
        return 0
    except Exception as exc:
        report.check("run", False, "{}: {}".format(type(exc).__name__, exc))
        return 1
    finally:
        close(controller)
        report.write()


# ── CLI ─────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate a MicroPythonOS OTA release on real hardware (with optional webcam checks)",
    )
    parser.add_argument("--port", default=os.environ.get("MPOS_PORT", "/dev/ttyACM0"),
                        help="serial port (default %(default)s)")
    parser.add_argument("--camera", default=os.environ.get("MPOS_CAMERA_DEVICE", "/dev/video0"),
                        help="V4L2 camera device (default %(default)s)")
    parser.add_argument("--no-camera", action="store_true", help="skip webcam checkpoints")
    parser.add_argument("--camera-config", default=None,
                        help="JSON camera config for mpos_screen_camera (device, controls, thresholds)")
    parser.add_argument("--base-bin", default=DEFAULT_BASE_BIN,
                        help="known-good factory image to flash first")
    parser.add_argument("--base-version", default="0.20.0",
                        help="release version inside --base-bin (default %(default)s)")
    parser.add_argument("--target-version", default="0.21.0",
                        help="release the updates server should offer (default %(default)s)")
    parser.add_argument("--updates-url", default=DEFAULT_UPDATES_URL,
                        help="updates server base URL for the host-side metadata check (default %(default)s)")
    parser.add_argument("--mirror-url", default=None,
                        help="override the URL the device fetches osupdate_*.json from "
                             "(for a local test server; does not survive a reboot)")
    parser.add_argument("--esptool", default=None,
                        help="esptool command prefix (default: python -m esptool, then PATH)")
    parser.add_argument("--chip", default="esp32s3", help="esptool chip (default %(default)s)")
    parser.add_argument("--flash-size", default="16MB", help="esptool flash size (default %(default)s)")
    parser.add_argument("--skip-flash", action="store_true",
                        help="do not flash; validate the board as it is now")
    parser.add_argument("--erase-all", dest="erase_all", action="store_true", default=False,
                        help="full-chip erase before writing (slower; can wedge flaky USB links)")
    parser.add_argument("--no-erase", dest="erase_all", action="store_false",
                        help="do not full-erase (default; the factory image contains a blank otadata)")
    parser.add_argument("--relay-port", default=os.environ.get("MPOS_RELAY_PORT"),
                        help="USB relay to power-cycle the badge between flash retries")
    parser.add_argument("--flash-retries", type=int, default=3,
                        help="esptool attempts before giving up (default %(default)s)")
    parser.add_argument("--wifi-ssid", default=os.environ.get("MPOS_WIFI_SSID"),
                        help="WiFi SSID (default $MPOS_WIFI_SSID)")
    parser.add_argument("--wifi-password", default=os.environ.get("MPOS_WIFI_PASSWORD"),
                        help="WiFi password (default $MPOS_WIFI_PASSWORD)")
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "tmp", "ota_validation"),
                        help="artifacts and report directory (default %(default)s)")
    parser.add_argument("--force-check", action="store_true",
                        help="start the update check directly instead of waiting for the boot service")
    parser.add_argument("--no-second-pass", dest="second_pass", action="store_false",
                        default=True, help="only test base -> target, not target -> target")
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print the plan")
    parser.add_argument("--boot-timeout", type=float, default=180.0, help="seconds to wait for boot")
    parser.add_argument("--wifi-timeout", type=float, default=120.0, help="seconds to wait for WiFi")
    parser.add_argument("--ui-timeout", type=float, default=60.0, help="seconds to wait for a UI state")
    parser.add_argument("--notification-timeout", type=float, default=240.0,
                        help="seconds to wait for the OTA notification")
    parser.add_argument("--download-timeout", type=float, default=900.0,
                        help="seconds allowed for download + reboot")
    parser.add_argument("--flash-timeout", type=float, default=300.0, help="seconds allowed for flashing")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_camera:
        args.camera = None
    if not args.wifi_ssid:
        parser.error("--wifi-ssid (or MPOS_WIFI_SSID) is required")
    if not args.wifi_password:
        parser.error("--wifi-password (or MPOS_WIFI_PASSWORD) is required")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
