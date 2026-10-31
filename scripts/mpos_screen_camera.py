#!/usr/bin/env python3
"""Camera-based verification of the physical MicroPythonOS display.

The device framebuffer (``MPOSController.screenshot()``) is the ground truth.
A host webcam pointed at the badge is aligned to that reference with SIFT +
RANSAC, which tolerates rotation, scale and perspective. Measured metrics:

* ``ncc_gray`` / ``ncc_gradient``: structural similarity of luminance and edges
* ``ncc_bgr``: per-channel similarity (colour fidelity)
* ``laplacian_var`` / ``tenengrad``: focus and edge energy
* ``cell_ncc_mean`` / ``cell_ncc_min``: per-icon-cell structural similarity
* ``inliers``: how many features locked (rig/readability score)
* ``eff_px_per_screen_px``: camera pixels per framebuffer pixel

This module is host-only and keeps numpy/opencv optional: they are imported
lazily, so ``mpos_controller`` and ``test_runner`` keep working without them.
Live capture uses ``ffmpeg``; camera controls use ``v4l2-ctl``.

Examples:
    python3 scripts/mpos_screen_camera.py list
    python3 scripts/mpos_screen_camera.py config --device /dev/video0 \\
        --no-auto-focus --focus 45 --no-auto-exposure --exposure 389 \\
        --wb 4300 --gain 49 --apply
    python3 scripts/mpos_screen_camera.py measure --port /dev/ttyACM0 \\
        --label 15cm --out-dir tmp/camtests
    python3 scripts/mpos_screen_camera.py focus-sweep --port /dev/ttyACM0 \\
        --start 30 --stop 55 --step 5 --repeats 2
    python3 scripts/mpos_screen_camera.py verify --port /dev/ttyACM0
    python3 scripts/mpos_screen_camera.py align --reference ref.png --frame shot.jpg
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List, Optional

DEFAULT_DEVICE = os.environ.get("MPOS_CAMERA_DEVICE", "/dev/video0")
DEFAULT_CAPTURE_SIZE = os.environ.get("MPOS_CAMERA_SIZE", "1920x1080")
DEFAULT_PIXEL_FORMAT = os.environ.get("MPOS_CAMERA_FORMAT", "mjpeg")
DEFAULT_OUT_DIR = os.environ.get("MPOS_CAMERA_OUT", "tmp/camtests")

DEFAULT_THRESHOLDS = {
    "min_inliers": 60,
    "min_ncc_gray": 0.85,
    "min_ncc_gradient": 0.75,
    "min_cell_ncc_min": 0.80,
    "min_eff_px_per_screen_px": 0.85,
}


class CameraError(RuntimeError):
    """Raised when the camera rig cannot be used or a frame cannot be aligned."""


def _np_cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise CameraError(
            "numpy and opencv-python-headless are required for camera verification: "
            "pip install numpy opencv-python-headless"
        ) from exc
    return np, cv2


def _require_tool(name, purpose):
    if shutil.which(name) is None:
        raise CameraError("%s is required %s (install it, e.g. apt install %s)" % (name, purpose, name))


@dataclass
class CameraConfig:
    device: str = DEFAULT_DEVICE
    capture_size: str = DEFAULT_CAPTURE_SIZE
    pixel_format: str = DEFAULT_PIXEL_FORMAT
    focus: Optional[int] = None
    auto_focus: Optional[bool] = None
    exposure: Optional[int] = None
    auto_exposure: Optional[bool] = None
    wb_temperature: Optional[int] = None
    gain: Optional[int] = None
    out_dir: str = DEFAULT_OUT_DIR
    reference_timeout: float = 300.0
    cache_dir: str = os.path.expanduser("~/.cache/mpos_screen_camera")
    use_cache: bool = True
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    homography: Optional[List[List[float]]] = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


def coerce_config(config):
    if config is None:
        return CameraConfig()
    if isinstance(config, CameraConfig):
        return config
    if isinstance(config, dict):
        return CameraConfig.from_dict(config)
    raise TypeError("config must be CameraConfig, dict or None")


def load_config(path):
    with open(path) as handle:
        return CameraConfig.from_dict(json.load(handle))


def save_config(path, config):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w") as handle:
        json.dump(coerce_config(config).to_dict(), handle, indent=1)


def list_devices():
    devices = []
    for path in sorted(glob.glob("/dev/video*")):
        name = ""
        try:
            with open("/sys/class/video4linux/%s/name" % os.path.basename(path)) as handle:
                name = handle.read().strip()
        except OSError:
            pass
        devices.append({"device": path, "name": name})
    return devices


def apply_config(config):
    """Apply focus/exposure/white-balance/gain through v4l2-ctl (no-op if all unset)."""
    cfg = coerce_config(config)
    controls = []
    if cfg.auto_exposure is not None:
        controls.append("auto_exposure=%d" % (3 if cfg.auto_exposure else 1))
    if cfg.exposure is not None and cfg.auto_exposure is False:
        controls.append("exposure_time_absolute=%d" % cfg.exposure)
    if cfg.auto_focus is not None:
        controls.append("focus_automatic_continuous=%d" % (1 if cfg.auto_focus else 0))
    if cfg.focus is not None and cfg.auto_focus is False:
        controls.append("focus_absolute=%d" % cfg.focus)
    if cfg.wb_temperature is not None:
        controls.append("white_balance_automatic=0")
        controls.append("white_balance_temperature=%d" % cfg.wb_temperature)
    if cfg.gain is not None:
        controls.append("gain=%d" % cfg.gain)
    if not controls:
        return
    _require_tool("v4l2-ctl", "to set camera controls (apt install v4l-utils)")
    # One control per call: some drivers reject a batch when a control only
    # becomes writable after an earlier one (e.g. focus after autofocus off).
    for control in controls:
        result = subprocess.run(["v4l2-ctl", "-d", cfg.device, "-c", control],
                                capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CameraError("v4l2-ctl failed setting %s: %s" % (control, detail))


def capture(device=DEFAULT_DEVICE, size=DEFAULT_CAPTURE_SIZE, pixel_format=DEFAULT_PIXEL_FORMAT, timeout=30.0):
    """Grab one frame from a V4L2 camera and return a BGR numpy array."""
    _np, cv2 = _np_cv()
    _require_tool("ffmpeg", "to capture the camera (apt install ffmpeg)")
    handle, path = tempfile.mkstemp(suffix=".jpg")
    os.close(handle)
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "v4l2",
            "-framerate", "5", "-video_size", size, "-input_format", pixel_format,
            "-i", device, "-frames:v", "1", "-q:v", "2", path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout)
        image = cv2.imread(path)
        if image is None:
            detail = result.stderr.decode("utf-8", "replace").strip()[-400:]
            raise CameraError("could not capture from %s: %s" % (device, detail or "no frame"))
        return image
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _mpremote_command():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled = os.path.join(repo, "lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py")
    if os.path.isfile(bundled):
        return [sys.executable, bundled]
    if shutil.which("mpremote"):
        return ["mpremote"]
    raise CameraError("mpremote not found (expected %s or on PATH)" % bundled)


def _copy_from_device(port, remote, local, timeout):
    command = _mpremote_command() + ["connect", port, "cp", ":" + remote, local]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CameraError(
            "timed out after %.0f s copying the framebuffer from %s; pass --reference with a saved "
            "image if the serial link is this slow" % (timeout, port)
        ) from exc
    if result.returncode != 0:
        raise CameraError("mpremote copy failed: %s" % (result.stderr.strip() or result.stdout.strip()))


def _device_sha1(controller, remote):
    output = controller.exec(
        "import hashlib, ubinascii\n"
        "f=open(%r,'rb'); d=f.read(); f.close()\n"
        "print('MPOSHASH' + ubinascii.hexlify(hashlib.sha1(d).digest()).decode())" % remote
    ).decode("utf-8", "replace")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("MPOSHASH"):
            return line[len("MPOSHASH"):].strip()
    raise CameraError("could not read the framebuffer hash")


def _restart_without_reset(controller):
    backend = getattr(controller, "_backend", None)
    previous = getattr(backend, "reset", None) if backend is not None else None
    if backend is not None and previous is not None:
        backend.reset = False
    try:
        controller.start()
    finally:
        if backend is not None and previous is not None:
            backend.reset = previous


def reference_from_controller(controller, config=None):
    """Return the current framebuffer as a BGR array.

    The frame is captured on the device, hashed, and cached locally, because a
    full RGB888 frame over USB-CDC can take a couple of minutes with mpremote.
    The serial port is released around the copy (mpremote needs it) and
    reopened without a reset afterwards.
    """
    np, cv2 = _np_cv()
    cfg = coerce_config(config)
    port = getattr(controller, "port", None)
    if not port:
        bmp = controller.screenshot()
        image = cv2.imdecode(np.frombuffer(bmp, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise CameraError("could not decode the controller screenshot")
        return image

    width, height = (int(value) for value in controller.display_size)
    needed = width * height * 3
    try:
        free = controller.check_free_space()
    except Exception:
        free = needed
    if free < needed:
        raise CameraError("device has %d bytes free; needs %d for the framebuffer reference" % (free, needed))

    remote = "/_mpos_camera_ref.raw"
    controller.exec(
        "import lvgl as lv; from mpos.ui.testing import capture_screenshot; "
        "capture_screenshot(%r, color_format=lv.COLOR_FORMAT.RGB888)" % remote
    )
    digest = _device_sha1(controller, remote)
    cache_path = os.path.join(cfg.cache_dir, digest + ".raw") if (cfg.use_cache and digest) else None

    data = None
    if cache_path and os.path.isfile(cache_path) and os.path.getsize(cache_path) == needed:
        data = np.fromfile(cache_path, dtype=np.uint8)

    if data is None:
        handle, local = tempfile.mkstemp(suffix=".raw")
        os.close(handle)
        controller.stop()
        try:
            _copy_from_device(port, remote, local, cfg.reference_timeout)
            data = np.fromfile(local, dtype=np.uint8)
            if cache_path and data.size == needed:
                try:
                    os.makedirs(cfg.cache_dir, exist_ok=True)
                    shutil.copyfile(local, cache_path)
                except OSError:
                    pass
        finally:
            try:
                os.unlink(local)
            except OSError:
                pass
            try:
                _restart_without_reset(controller)
            except Exception:
                pass

    try:
        controller.exec("import os\ntry: os.remove(%r)\nexcept OSError: pass" % remote)
    except Exception:
        pass

    if data is None or data.size != needed:
        raise CameraError("framebuffer reference is %s bytes, expected %d"
                          % ("missing" if data is None else data.size, needed))
    return data.reshape(height, width, 3)


def load_image(path):
    _np, cv2 = _np_cv()
    image = cv2.imread(path)
    if image is None:
        raise CameraError("could not read image: %s" % path)
    return image


@dataclass
class AlignResult:
    homography: Any
    inliers: int
    matches: int
    quad: Any
    aligned: Any
    scale: float
    rotation_deg: float


def align(reference_bgr, frame_bgr, nfeatures=4000, ratio=0.75, ransac_px=5.0):
    """Align a camera frame to the framebuffer. Returns AlignResult or None."""
    np, cv2 = _np_cv()
    ref_gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create(nfeatures=nfeatures)
    key1, des1 = sift.detectAndCompute(ref_gray, None)
    key2, des2 = sift.detectAndCompute(frame_gray, None)
    if des1 is None or des2 is None or len(key1) < 8 or len(key2) < 8:
        return None
    pairs = cv2.BFMatcher().knnMatch(des1, des2, k=2)
    good = [a for a, b in (p for p in pairs if len(p) == 2) if a.distance < ratio * b.distance]
    if len(good) < 8:
        return None
    src = np.float32([key1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([key2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(src, dst, cv2.RANSAC, ransac_px)
    if homography is None or mask is None:
        return None
    inliers = int(mask.sum())
    if inliers < 8:
        return None
    height, width = reference_bgr.shape[:2]
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]]).reshape(-1, 1, 2)
    quad = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
    aligned = cv2.warpPerspective(
        frame_bgr, np.linalg.inv(homography), (width, height),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )
    affine = homography[:2, :2]
    return AlignResult(
        homography=homography,
        inliers=inliers,
        matches=len(good),
        quad=quad,
        aligned=aligned,
        scale=float(np.sqrt(abs(np.linalg.det(affine)))),
        rotation_deg=float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0]))),
    )


def _norm(array):
    array = array.astype("float32")
    mean = array.mean()
    std = array.std()
    return (array - mean) / (std if std > 1e-6 else 1.0)


def _ncc(first, second):
    return float((_norm(first) * _norm(second)).mean())


def metrics(reference_bgr, aligned_bgr, quad=None, rows=None, cols=None):
    """Structural/quality metrics of an aligned camera image vs the reference."""
    np, cv2 = _np_cv()
    height, width = reference_bgr.shape[:2]
    if rows is None or cols is None:
        rows, cols = (4, 5) if width >= height else (5, 4)
    ref_gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
    aligned_gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)
    ref_grad = cv2.magnitude(
        cv2.Sobel(ref_gray, cv2.CV_64F, 1, 0, 3), cv2.Sobel(ref_gray, cv2.CV_64F, 0, 1, 3)
    ).astype("float32")
    aligned_grad = cv2.magnitude(
        cv2.Sobel(aligned_gray, cv2.CV_64F, 1, 0, 3), cv2.Sobel(aligned_gray, cv2.CV_64F, 0, 1, 3)
    ).astype("float32")
    sobel_x = cv2.Sobel(aligned_gray, cv2.CV_64F, 1, 0, 3)
    sobel_y = cv2.Sobel(aligned_gray, cv2.CV_64F, 0, 1, 3)

    cell_values = []
    for row in range(rows):
        for col in range(cols):
            y0, y1 = int(row * height / rows), int((row + 1) * height / rows)
            x0, x1 = int(col * width / cols), int((col + 1) * width / cols)
            cell_values.append(float((_norm(ref_gray[y0:y1, x0:x1]) * _norm(aligned_gray[y0:y1, x0:x1])).mean()))

    result = {
        "ncc_gray": round(_ncc(ref_gray, aligned_gray), 3),
        "ncc_gradient": round(_ncc(ref_grad, aligned_grad), 3),
        "ncc_bgr": [round(_ncc(reference_bgr[:, :, i], aligned_bgr[:, :, i]), 3) for i in range(3)],
        "laplacian_var": round(float(cv2.Laplacian(aligned_gray, cv2.CV_64F).var()), 1),
        "tenengrad": round(float(np.mean(sobel_x * sobel_x + sobel_y * sobel_y)), 1),
        "cell_ncc_mean": round(float(np.mean(cell_values)), 3),
        "cell_ncc_min": round(float(np.min(cell_values)), 3),
        "cells": [rows, cols],
    }
    if quad is not None:
        screen_w = float(np.linalg.norm(quad[1] - quad[0]))
        screen_h = float(np.linalg.norm(quad[3] - quad[0]))
        result["screen_px"] = [round(screen_w, 1), round(screen_h, 1)]
        result["eff_px_per_screen_px"] = round(screen_w / float(width), 3)
    return result


def check_thresholds(measured, thresholds=None):
    thresholds = thresholds or DEFAULT_THRESHOLDS
    pairs = {
        "inliers": "min_inliers",
        "ncc_gray": "min_ncc_gray",
        "ncc_gradient": "min_ncc_gradient",
        "cell_ncc_min": "min_cell_ncc_min",
        "eff_px_per_screen_px": "min_eff_px_per_screen_px",
    }
    failures = {}
    for key, threshold_key in pairs.items():
        limit = thresholds.get(threshold_key)
        value = measured.get(key)
        if limit is not None and value is not None and value < limit:
            failures[key] = {"value": value, "min": limit}
    return len(failures) == 0, failures


def save_artifacts(out_dir, label, reference_bgr, frame_bgr, aligned_bgr, measured):
    """Write raw/aligned/compare/edge images and append to metrics.jsonl."""
    np, cv2 = _np_cv()
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, label)
    paths = {
        "frame": base + "_frame.jpg",
        "aligned": base + "_aligned.png",
        "compare": base + "_compare.jpg",
        "edges": base + "_edges.jpg",
    }
    cv2.imwrite(paths["frame"], frame_bgr)
    cv2.imwrite(paths["aligned"], aligned_bgr)

    def _panel(image, title):
        panel = cv2.resize(image, (reference_bgr.shape[1] * 3, reference_bgr.shape[0] * 3),
                           interpolation=cv2.INTER_LANCZOS4)
        cv2.putText(panel, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return panel

    separator = np.full((reference_bgr.shape[0] * 3, 10, 3), 255, "uint8")
    compare = np.hstack([_panel(reference_bgr, "DEVICE (framebuffer)"), separator,
                         _panel(aligned_bgr, "CAMERA")])
    cv2.imwrite(paths["compare"], compare, [cv2.IMWRITE_JPEG_QUALITY, 92])

    ref_gray = cv2.cvtColor(reference_bgr, cv2.COLOR_BGR2GRAY)
    aligned_gray = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2GRAY)

    def _edges(gray):
        magnitude = cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0, 3), cv2.Sobel(gray, cv2.CV_32F, 0, 1, 3))
        scale = np.percentile(magnitude, 99) + 1e-6
        return cv2.cvtColor((np.clip(magnitude / scale, 0, 1) * 255).astype("uint8"), cv2.COLOR_GRAY2BGR)

    edge_panel = np.hstack([_panel(_edges(ref_gray), "GT edges"), separator,
                            _panel(_edges(aligned_gray), "CAMERA edges")])
    cv2.imwrite(paths["edges"], edge_panel, [cv2.IMWRITE_JPEG_QUALITY, 92])

    with open(os.path.join(out_dir, "metrics.jsonl"), "a") as handle:
        handle.write(json.dumps({"label": label, **measured}) + "\n")
    return paths


def _align_or_cached(config, reference_bgr, frame_bgr):
    np, cv2 = _np_cv()
    result = align(reference_bgr, frame_bgr)
    if result is not None:
        return result, "sift"
    if not config.homography:
        raise CameraError(
            "could not align the camera frame to the framebuffer (SIFT found too few matches); "
            "check focus/position, or pass a cached homography"
        )
    homography = np.array(config.homography, dtype="float32")
    height, width = reference_bgr.shape[:2]
    corners = np.float32([[0, 0], [width, 0], [width, height], [0, height]]).reshape(-1, 1, 2)
    quad = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
    aligned = cv2.warpPerspective(
        frame_bgr, np.linalg.inv(homography), (width, height),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )
    affine = homography[:2, :2]
    result = AlignResult(
        homography=homography, inliers=0, matches=0, quad=quad, aligned=aligned,
        scale=float(np.sqrt(abs(np.linalg.det(affine)))),
        rotation_deg=float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0]))),
    )
    return result, "cached_homography"


def measure(controller=None, config=None, reference=None, frame=None, label="screen", thresholds=None,
            out_dir=None, save_homography=None):
    """Capture/align/score one frame and write artifacts. Returns a metrics dict."""
    np, _cv2 = _np_cv()
    cfg = coerce_config(config)
    if reference is None:
        if controller is None:
            raise CameraError("need a controller for the framebuffer reference, or a reference image")
        reference = reference_from_controller(controller, cfg)
    if frame is None:
        frame = capture(cfg.device, cfg.capture_size, cfg.pixel_format)
    result, via = _align_or_cached(cfg, reference, frame)
    measured = metrics(reference, result.aligned, result.quad)
    measured.update({
        "good_matches": result.matches,
        "inliers": result.inliers,
        "inlier_ratio": round(result.inliers / max(1, result.matches), 2),
        "scale": round(result.scale, 3),
        "rotation_deg": round(result.rotation_deg, 1),
        "aligned_via": via,
    })
    measured["ok"], measured["failures"] = check_thresholds(measured, thresholds or cfg.thresholds)
    measured["artifacts"] = save_artifacts(out_dir or cfg.out_dir, label, reference, frame,
                                          result.aligned, measured)
    if save_homography:
        cfg.homography = np.asarray(result.homography).tolist()
        save_config(save_homography, cfg)
    return measured


def focus_sweep(config=None, reference_bgr=None, controller=None, values=None, repeats=2, settle=1.0,
                capture_fn=None, apply_fn=None):
    """Find the sharpest manual focus for the rig. Returns (best_focus, rows)."""
    cfg = coerce_config(config)
    if reference_bgr is None:
        if controller is None:
            raise CameraError("focus_sweep needs a reference image or a controller")
        reference_bgr = reference_from_controller(controller, cfg)
    if values is None:
        values = list(range(0, 251, 5))
    grab = capture_fn or (lambda: capture(cfg.device, cfg.capture_size, cfg.pixel_format))
    apply = apply_fn or apply_config
    rows = []
    for focus in values:
        apply(replace(cfg, auto_focus=False, focus=focus))
        time.sleep(settle)
        samples = []
        for _ in range(max(1, repeats)):
            time.sleep(0.5)
            result = align(reference_bgr, grab())
            if result is not None:
                sample = metrics(reference_bgr, result.aligned, result.quad)
                sample["inliers"] = result.inliers
                samples.append(sample)
        if not samples:
            continue
        keys = ("ncc_gray", "ncc_gradient", "cell_ncc_mean", "cell_ncc_min", "laplacian_var",
                "tenengrad", "inliers", "eff_px_per_screen_px")
        row = {"focus": focus}
        for key in keys:
            values_for_key = [s[key] for s in samples if key in s]
            if values_for_key:
                row[key] = round(float(sum(values_for_key) / len(values_for_key)), 3)
        rows.append(row)
    if not rows:
        raise CameraError("focus sweep produced no alignable frames")
    best = max(rows, key=lambda row: (row.get("ncc_gradient", 0), row.get("cell_ncc_min", 0),
                                      row.get("laplacian_var", 0)))
    apply(replace(cfg, auto_focus=False, focus=best["focus"]))
    return best["focus"], rows


def _controller(port):
    try:
        from .mpos_controller import MPOSController
    except ImportError:
        from mpos_controller import MPOSController
    return MPOSController(backend="serial", port=port)


def _add_camera_args(parser):
    parser.add_argument("--device", default=None, help="V4L2 device (default %s)" % DEFAULT_DEVICE)
    parser.add_argument("--capture-size", default=None, help="ffmpeg video_size (default %s)" % DEFAULT_CAPTURE_SIZE)
    parser.add_argument("--pixel-format", default=None, help="V4L2 pixel format (default %s)" % DEFAULT_PIXEL_FORMAT)
    parser.add_argument("--config", default=None, help="JSON config with device/controls/thresholds")
    parser.add_argument("--cache-dir", default=None, help="framebuffer cache directory (default ~/.cache/mpos_screen_camera)")
    parser.add_argument("--no-cache", action="store_true", help="always re-read the framebuffer")


def _add_control_args(parser):
    parser.add_argument("--focus", type=int, default=None, help="manual focus_absolute (0-250, step 5)")
    parser.add_argument("--auto-focus", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--exposure", type=int, default=None, help="manual exposure_time_absolute")
    parser.add_argument("--auto-exposure", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--wb", type=int, default=None, help="white balance temperature in K")
    parser.add_argument("--gain", type=int, default=None)


def _add_threshold_args(parser):
    parser.add_argument("--min-inliers", type=int, default=None)
    parser.add_argument("--min-ncc-gray", type=float, default=None)
    parser.add_argument("--min-ncc-gradient", type=float, default=None)
    parser.add_argument("--min-cell-ncc-min", type=float, default=None)
    parser.add_argument("--min-eff-px", type=float, default=None)


def _thresholds_from_args(args):
    pairs = {
        "min_inliers": args.min_inliers,
        "min_ncc_gray": args.min_ncc_gray,
        "min_ncc_gradient": args.min_ncc_gradient,
        "min_cell_ncc_min": args.min_cell_ncc_min,
        "min_eff_px_per_screen_px": args.min_eff_px,
    }
    return {key: value for key, value in pairs.items() if value is not None}


def _config_from_args(args, apply_controls=False):
    cfg = load_config(args.config) if args.config else CameraConfig()
    if args.device:
        cfg.device = args.device
    if args.capture_size:
        cfg.capture_size = args.capture_size
    if args.pixel_format:
        cfg.pixel_format = args.pixel_format
    controls = {
        "focus": getattr(args, "focus", None),
        "auto_focus": getattr(args, "auto_focus", None),
        "exposure": getattr(args, "exposure", None),
        "auto_exposure": getattr(args, "auto_exposure", None),
        "wb_temperature": getattr(args, "wb", None),
        "gain": getattr(args, "gain", None),
        "reference_timeout": getattr(args, "reference_timeout", None),
    }
    for field_name, value in controls.items():
        if value is not None:
            setattr(cfg, field_name, value)
    out_dir = getattr(args, "out_dir", None)
    if out_dir:
        cfg.out_dir = out_dir
    cache_dir = getattr(args, "cache_dir", None)
    if cache_dir:
        cfg.cache_dir = cache_dir
    if getattr(args, "no_cache", False):
        cfg.use_cache = False
    if apply_controls:
        apply_config(cfg)
    return cfg


def _reference_from_args(args, config=None):
    if getattr(args, "reference", None):
        return load_image(args.reference)
    port = getattr(args, "port", None)
    if not port:
        raise CameraError("give --reference IMAGE or --port to read the framebuffer")
    cfg = coerce_config(config)
    with _controller(port) as controller:
        return reference_from_controller(controller, cfg)


def _measure_from_args(args):
    cfg = _config_from_args(args)
    frame = load_image(args.frame) if getattr(args, "frame", None) else None
    controller = None
    if getattr(args, "port", None) and not getattr(args, "reference", None):
        controller = _controller(args.port)
        controller.start()
    try:
        reference = load_image(args.reference) if getattr(args, "reference", None) else None
        return measure(controller=controller, config=cfg, reference=reference, frame=frame,
                       label=args.label, thresholds=_thresholds_from_args(args),
                       out_dir=args.out_dir, save_homography=args.save_homography)
    finally:
        if controller is not None:
            controller.stop()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify the physical MicroPythonOS screen through a webcam")
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="list V4L2 devices")

    config_parser = commands.add_parser("config", help="show/apply camera controls")
    _add_camera_args(config_parser)
    _add_control_args(config_parser)
    config_parser.add_argument("--out-dir", default=None)
    config_parser.add_argument("--apply", action="store_true", help="send the controls to the camera")
    config_parser.add_argument("--save", default=None, help="write the config to a JSON file")

    reference_parser = commands.add_parser("capture-reference", help="save the device framebuffer as a reference image")
    _add_camera_args(reference_parser)
    reference_parser.add_argument("--port", required=True)
    reference_parser.add_argument("--out", required=True)

    capture_parser = commands.add_parser("capture", help="capture one frame to a file")
    _add_camera_args(capture_parser)
    capture_parser.add_argument("--file", required=True)
    capture_parser.add_argument("--apply", action="store_true")

    for name, help_text in (("measure", "capture, align and score the screen"),
                            ("verify", "like measure but exit non-zero below thresholds")):
        command = commands.add_parser(name, help=help_text)
        _add_camera_args(command)
        _add_threshold_args(command)
        command.add_argument("--port", default=None, help="serial port for the framebuffer reference")
        command.add_argument("--reference", default=None, help="reference image instead of --port")
        command.add_argument("--frame", default=None, help="camera image instead of live capture")
        command.add_argument("--reference-timeout", type=float, default=None)
        command.add_argument("--label", default="screen")
        command.add_argument("--out-dir", default=None)
        command.add_argument("--save-homography", default=None)

    sweep_parser = commands.add_parser("focus-sweep", help="find and lock the sharpest manual focus")
    _add_camera_args(sweep_parser)
    sweep_parser.add_argument("--port", default=None)
    sweep_parser.add_argument("--reference", default=None)
    sweep_parser.add_argument("--values", default=None, help="comma-separated focus values")
    sweep_parser.add_argument("--start", type=int, default=30)
    sweep_parser.add_argument("--stop", type=int, default=55)
    sweep_parser.add_argument("--step", type=int, default=5)
    sweep_parser.add_argument("--repeats", type=int, default=2)
    sweep_parser.add_argument("--settle", type=float, default=1.0)
    sweep_parser.add_argument("--reference-timeout", type=float, default=None)
    sweep_parser.add_argument("--out-dir", default=None)
    sweep_parser.add_argument("--save-config", default=None)

    align_parser = commands.add_parser("align", help="align two images offline (no camera/device)")
    align_parser.add_argument("--reference", required=True)
    align_parser.add_argument("--frame", required=True)
    align_parser.add_argument("--label", default="align")
    align_parser.add_argument("--out-dir", default=None)

    args = parser.parse_args(argv)

    if args.command == "list":
        print(json.dumps(list_devices(), indent=1))
        return 0

    if args.command == "config":
        cfg = _config_from_args(args, apply_controls=args.apply)
        if args.save:
            save_config(args.save, cfg)
        print(json.dumps(cfg.to_dict(), indent=1))
        return 0

    if args.command == "capture-reference":
        cfg = _config_from_args(args)
        _np, cv2 = _np_cv()
        with _controller(args.port) as controller:
            reference = reference_from_controller(controller, cfg)
        cv2.imwrite(args.out, reference)
        print(json.dumps({"reference": args.out, "shape": list(reference.shape)}))
        return 0

    if args.command == "capture":
        cfg = _config_from_args(args, apply_controls=args.apply)
        image = capture(cfg.device, cfg.capture_size, cfg.pixel_format)
        _np, cv2 = _np_cv()
        cv2.imwrite(args.file, image)
        print(args.file)
        return 0

    if args.command == "align":
        reference = load_image(args.reference)
        frame = load_image(args.frame)
        result = align(reference, frame)
        if result is None:
            print(json.dumps({"error": "could not align"}))
            return 1
        measured = metrics(reference, result.aligned, result.quad)
        measured.update({"good_matches": result.matches, "inliers": result.inliers,
                         "scale": round(result.scale, 3), "rotation_deg": round(result.rotation_deg, 1)})
        measured["artifacts"] = save_artifacts(args.out_dir or DEFAULT_OUT_DIR, args.label,
                                               reference, frame, result.aligned, measured)
        print(json.dumps(measured, indent=1))
        return 0

    if args.command == "focus-sweep":
        cfg = _config_from_args(args)
        values = [int(value) for value in args.values.split(",")] if args.values else \
            list(range(args.start, args.stop + 1, args.step))
        best, rows = focus_sweep(config=cfg, reference_bgr=_reference_from_args(args, cfg), values=values,
                                 repeats=args.repeats, settle=args.settle)
        result = {"best_focus": best, "rows": rows}
        if args.out_dir:
            os.makedirs(args.out_dir, exist_ok=True)
            with open(os.path.join(args.out_dir, "focus_sweep.json"), "w") as handle:
                json.dump(result, handle, indent=1)
        if args.save_config:
            save_config(args.save_config, replace(cfg, auto_focus=False, focus=best))
        print(json.dumps(result, indent=1))
        return 0

    # measure / verify
    measured = _measure_from_args(args)
    print(json.dumps(measured, indent=1))
    if args.command == "verify" and not measured.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
