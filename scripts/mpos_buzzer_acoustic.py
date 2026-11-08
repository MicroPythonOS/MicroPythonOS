#!/usr/bin/env python3
"""Acoustic verification of the MicroPythonOS badge buzzer.

A host USB microphone records the badge while the device plays a known RTTTL
note sequence. The recording is segmented by loudness and, for every segment,
the strongest spectral peak is folded down to the nearest harmonic of the
expected note. That makes the check work even for a low note whose fundamental
is buried under the piezo resonance (a buzzer is a square-wave PWM output, not
a sine, and small piezo discs resonate around 3-4 kHz).

Commands:
    list       enumerate capture devices
    record     record N seconds to a WAV file
    analyze    verify a WAV file offline (no device needed)
    verify     play notes on the badge, record, analyze and gate pass/fail

Examples:
    python3 scripts/mpos_buzzer_acoustic.py list
    python3 scripts/mpos_buzzer_acoustic.py verify --port /dev/ttyACM0 \\
        --relayport /dev/ttyUSB0 --notes a4,a5,a6,a7
    python3 scripts/mpos_buzzer_acoustic.py record --seconds 5 --out tmp/buzzertests/silence.wav
    python3 scripts/mpos_buzzer_acoustic.py analyze --wav tmp/buzzertests/last.wav --notes a4,a5

Host requirements: ``arecord`` (alsa-utils) and ``numpy``. ``parecord``
(pulseaudio-utils) is used instead when ``--device`` names a PulseAudio source.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_PORT = os.environ.get("MPOS_BUZZER_PORT", "/dev/ttyACM0")
DEFAULT_RELAY = os.environ.get("MPOS_BUZZER_RELAY")
DEFAULT_DEVICE = os.environ.get("MPOS_BUZZER_DEVICE")
DEFAULT_OUT_DIR = os.environ.get("MPOS_BUZZER_OUT", "tmp/buzzertests")
DEFAULT_RATE = 44100
DEFAULT_NOTES = "a4,a5,a6,a7"
DEFAULT_VOLUME = 100

DEFAULT_THRESHOLDS = {
    "min_snr_db": 12.0,
    "max_freq_error_pct": 2.0,
    "min_duration_s": 0.3,
}

# Same equal-temperament table as mpos.audio.stream_rtttl.RTTTLStream._NOTES,
# so the expected frequency matches what the firmware actually plays.
NOTE_FREQUENCIES = {
    "a": 440.0,
    "b": 493.9,
    "c": 261.6,
    "d": 293.7,
    "e": 329.6,
    "f": 349.2,
    "g": 392.0,
    "a#": 466.2,
    "c#": 277.2,
    "d#": 311.1,
    "f#": 370.0,
    "g#": 415.3,
}

_WEBCAM_MARKERS = ("webcam", "c920", "c922", "c925", "logitech", "brio")


class BuzzerError(RuntimeError):
    """Raised when the acoustic rig or the device cannot be used."""


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise BuzzerError("numpy is required for buzzer verification: pip install numpy") from exc
    return np


def _require_tool(name, purpose):
    if shutil.which(name) is None:
        raise BuzzerError("%s is required %s (install it, e.g. apt install %s)" % (name, purpose, name))


# ── Notes and RTTTL ─────────────────────────────────────────────────


def note_frequency(note):
    """Return the firmware's frequency for a note such as ``a4`` or ``c#6``."""
    name, octave = parse_note(note)
    return NOTE_FREQUENCIES[name] * (1 << (octave - 4))


def parse_note(note):
    match = re.match(r"^\s*([a-gA-G])(#?)([4-7])\s*$", note)
    if match is None:
        raise BuzzerError("invalid note %r: use a letter a-g, optional #, octave 4-7 (e.g. a4, c#6)" % note)
    name = match.group(1).lower() + match.group(2)
    if name not in NOTE_FREQUENCIES:
        raise BuzzerError("unsupported note %r" % note)
    return name, int(match.group(3))


def parse_notes(spec):
    notes = [item.strip().lower() for item in str(spec).split(",") if item.strip()]
    if not notes:
        raise BuzzerError("no notes given")
    for note in notes:
        parse_note(note)
    return notes


def build_rtttl(notes, duration=4, bpm=60, name="BUZZER"):
    """Build an RTTTL string that plays *notes* once, in order."""
    if name.count(":") or "," in name:
        raise BuzzerError("invalid RTTTL name %r" % name)
    return "%s:d=%d,b=%d:%s" % (name, int(duration), int(bpm), ",".join(notes))


def note_duration_s(duration=4, bpm=60):
    """Seconds a single RTTTL note lasts (before the 10% gap)."""
    return (240000.0 / float(bpm)) / float(duration) / 1000.0


# ── Capture devices ─────────────────────────────────────────────────


@dataclass
class CaptureDevice:
    card: int
    device: int
    card_name: str
    device_name: str
    pulse_source: Optional[str] = None

    @property
    def alsa(self):
        return "plughw:%d,%d" % (self.card, self.device)

    @property
    def description(self):
        return "%s (%s)" % (self.device_name, self.card_name)

    @property
    def is_webcam(self):
        haystack = (self.card_name + " " + self.device_name).lower()
        return any(marker in haystack for marker in _WEBCAM_MARKERS)

    def to_dict(self):
        return {
            "card": self.card,
            "device": self.device,
            "alsa": self.alsa,
            "card_name": self.card_name,
            "device_name": self.device_name,
            "pulse_source": self.pulse_source,
            "description": self.description,
        }


def parse_arecord_listing(text):
    """Parse ``arecord -l`` output into :class:`CaptureDevice` entries."""
    devices = []
    pattern = re.compile(r"^card (\d+): (.+?) \[(.+?)\], device (\d+): (.+?) \[(.+?)\]")
    for line in (text or "").splitlines():
        match = pattern.match(line.strip())
        if match is None:
            continue
        devices.append(CaptureDevice(
            card=int(match.group(1)),
            device=int(match.group(4)),
            card_name=match.group(3),
            device_name=match.group(6),
        ))
    return devices


def _arecord_capture_devices():
    _require_tool("arecord", "to record the buzzer")
    try:
        listed = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BuzzerError("could not list ALSA capture devices: %s" % exc) from exc
    return parse_arecord_listing(listed.stdout)


def parse_pactl_sources(text):
    """Map ``(alsa.card, alsa.device)`` to the PulseAudio source name."""
    mapping = {}
    name = None
    card = None
    device = None

    def flush():
        if name is not None and card is not None:
            mapping[(card, device if device is not None else 0)] = name

    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("Name: "):
            flush()
            name = stripped.split("Name: ", 1)[1].strip()
            card = None
            device = None
        elif stripped.startswith("alsa.card = "):
            card = int(stripped.split("=", 1)[1].strip().strip('"'))
        elif stripped.startswith("alsa.device = "):
            device = int(stripped.split("=", 1)[1].strip().strip('"'))
    flush()
    return mapping


def _pulse_sources_by_card():
    if shutil.which("pactl") is None:
        return {}
    try:
        listed = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_pactl_sources(listed.stdout)


def list_capture_devices():
    """Return every ALSA capture device, annotated with its PulseAudio source."""
    devices = _arecord_capture_devices()
    pulse = _pulse_sources_by_card()
    for device in devices:
        device.pulse_source = pulse.get((device.card, device.device))
    return devices


def _device_from_spec(spec):
    if spec.startswith("alsa_") or spec.startswith("pulse:"):
        source = spec.split("pulse:", 1)[-1]
        return CaptureDevice(card=-1, device=-1, card_name="PulseAudio", device_name=source, pulse_source=source)
    match = re.match(r"^(?:plug)?hw:(\d+),(\d+)$", spec)
    if match is not None:
        card, device = int(match.group(1)), int(match.group(2))
        return CaptureDevice(card=card, device=device, card_name="hw", device_name=spec)
    if spec.isdigit():
        return CaptureDevice(card=int(spec), device=0, card_name="hw", device_name="plughw:%s,0" % spec)
    raise BuzzerError(
        "unrecognized --device %r: use plughw:CARD,DEV, a card number, or an alsa_input.* PulseAudio source" % spec
    )


def find_capture_device(spec=None):
    """Pick the USB sound-card microphone (or honour *spec*)."""
    if spec:
        device = _device_from_spec(spec)
        if device.card < 0:
            return device
        known = _arecord_capture_devices()
        for candidate in known:
            if candidate.card == device.card and candidate.device == device.device:
                return candidate
        return device
    devices = list_capture_devices()
    if not devices:
        raise BuzzerError("no ALSA capture devices found; connect the USB sound card or pass --device")
    usb = [device for device in devices if "usb" in (device.card_name + device.device_name).lower()]
    preferred = [device for device in usb if not device.is_webcam]
    candidates = preferred or usb or devices
    if len(candidates) > 1:
        named = [device for device in candidates if "usb audio" in (device.card_name + device.device_name).lower()]
        if named:
            candidates = named
    return candidates[0]


# ── Recording ───────────────────────────────────────────────────────


def _capture_command(device, out_path, rate):
    if device.pulse_source:
        _require_tool("parecord", "to record a PulseAudio source")
        return [
            "parecord", "--device=" + device.pulse_source, "--format=s16le",
            "--rate=%d" % rate, "--channels=1", "--file-format=wav", out_path,
        ]
    _require_tool("arecord", "to record the buzzer")
    return [
        "arecord", "-q", "-D", device.alsa, "-f", "S16_LE", "-r", str(rate),
        "-c", "1", "-t", "wav", out_path,
    ]


def start_recording(device, out_path, rate=DEFAULT_RATE):
    """Start a background capture; pair with :func:`stop_recording`."""
    if os.path.exists(out_path):
        os.remove(out_path)
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    command = _capture_command(device, out_path, rate)
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def stop_recording(process, out_path=None):
    """Stop a capture started with :func:`start_recording`; returns stderr text."""
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    stderr = process.stderr.read().decode("utf-8", "replace").strip() if process.stderr else ""
    if out_path is not None and (not os.path.exists(out_path) or os.path.getsize(out_path) <= 44):
        raise BuzzerError("recording produced no audio: %s" % (stderr or "empty WAV"))
    return stderr


def wait_for_recording(process, out_path, timeout=8.0):
    """Block until the recorder has written audio, so no tone is missed.

    ``arecord`` can take well over a second to open the device (PulseAudio may
    still hold it), during which the WAV file contains only its header.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", "replace").strip() if process.stderr else ""
            raise BuzzerError("recorder exited before capturing audio: %s" % (stderr or "exit %s" % process.returncode))
        try:
            if os.path.getsize(out_path) > 4096:
                return True
        except OSError:
            pass
        time.sleep(0.05)
    raise BuzzerError("recorder did not start within %.0fs" % timeout)


def record(device, seconds, out_path, rate=DEFAULT_RATE):
    """Record *seconds* of audio to *out_path* and return the WAV path."""
    process = start_recording(device, out_path, rate)
    try:
        wait_for_recording(process, out_path)
        time.sleep(max(0.1, float(seconds)))
    finally:
        stop_recording(process, out_path)
    return out_path


def read_wav(path):
    """Read a PCM16 WAV file into a mono float signal in [-1, 1]."""
    np = _numpy()
    import wave

    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise BuzzerError("expected a 16-bit WAV, got %d-bit: %s" % (width * 8, path))
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if samples.size == 0:
        raise BuzzerError("empty WAV: %s" % path)
    return samples, rate


def write_wav(path, samples, rate):
    """Write a float signal in [-1, 1] as a mono PCM16 WAV (used by tests)."""
    np = _numpy()
    import wave

    clipped = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    data = (clipped * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(data.tobytes())
    return path


# ── Analysis ────────────────────────────────────────────────────────


def _segment(samples, rate, min_duration_s):
    np = _numpy()
    window = max(1, int(0.02 * rate))
    count = samples.size // window
    if count < 2:
        return [], 0.0, 0.0
    trimmed = samples[:count * window].reshape(count, window)
    rms = np.sqrt(np.mean(trimmed * trimmed, axis=1))
    noise = float(np.percentile(rms, 10))
    loudest = float(rms.max())
    threshold = max(noise * 3.0, loudest * 0.15, 1e-4)
    segments = []
    start = None
    for index, value in enumerate(rms):
        if value >= threshold and start is None:
            start = index
        elif value < threshold and start is not None:
            segments.append((start, index))
            start = None
    if start is not None:
        segments.append((start, count))
    minimum = max(1, int(round(min_duration_s * rate / window)))
    kept = [(first, last) for first, last in segments if last - first >= minimum]
    return [(first * window, last * window) for first, last in kept], noise, threshold


def analyze_waveform(samples, rate, notes, thresholds=None):
    """Segment a recording and report the detected note per segment."""
    np = _numpy()
    limits = dict(DEFAULT_THRESHOLDS)
    limits.update(thresholds or {})
    expected = [(note, note_frequency(note)) for note in notes]
    spans, noise, threshold = _segment(samples, rate, limits["min_duration_s"])
    noise = max(noise, 1e-12)
    measured = {
        "sample_rate": rate,
        "duration_s": round(samples.size / float(rate), 3),
        "noise_floor_dbfs": round(20.0 * np.log10(noise), 1),
        "threshold_rms": round(threshold, 5),
        "expected": [{"note": note, "frequency_hz": float(freq)} for note, freq in expected],
        "segments": [],
    }
    for index, (first, last) in enumerate(spans):
        span = samples[first:last]
        span = span - span.mean()
        weighted = span * np.hanning(span.size)
        spectrum = np.abs(np.fft.rfft(weighted))
        frequencies = np.fft.rfftfreq(span.size, 1.0 / rate)
        mask = frequencies >= 150.0
        if not mask.any():
            peak_hz = 0.0
        else:
            peak_hz = float(frequencies[mask][int(np.argmax(spectrum[mask]))])
        rms = float(np.sqrt(np.mean(span * span)))
        entry = {
            "index": index,
            "start_s": round(first / float(rate), 3),
            "end_s": round(last / float(rate), 3),
            "duration_s": round((last - first) / float(rate), 3),
            "rms_dbfs": round(20.0 * np.log10(max(rms, 1e-12)), 1),
            "snr_db": round(20.0 * np.log10(max(rms, 1e-12) / noise), 1),
            "peak_hz": round(peak_hz, 1),
            "ok": False,
        }
        if index < len(expected):
            note, frequency = expected[index]
            harmonic = int(round(peak_hz / frequency)) if frequency else 1
            harmonic = max(1, min(harmonic, 20))
            folded = peak_hz / harmonic
            error = 100.0 * (folded - frequency) / frequency
            entry.update({
                "note": note,
                "expected_hz": round(float(frequency), 1),
                "harmonic": harmonic,
                "f0_hz": round(folded, 1),
                "error_pct": round(error, 2),
            })
            entry["ok"] = abs(error) <= limits["max_freq_error_pct"]
        measured["segments"].append(entry)
    measured["ok"], measured["failures"] = check_thresholds(measured, limits)
    return measured


def check_thresholds(measured, thresholds=None):
    """Return ``(ok, failures)`` for a measurement dict."""
    limits = dict(DEFAULT_THRESHOLDS)
    limits.update(thresholds or {})
    failures = {}
    expected = measured.get("expected") or []
    segments = measured.get("segments") or []
    if len(segments) != len(expected):
        failures["segments"] = "expected %d tone(s), found %d" % (len(expected), len(segments))
    for index, entry in enumerate(segments):
        label = entry.get("note") or "segment_%d" % index
        if entry.get("snr_db", 0.0) < limits["min_snr_db"]:
            failures[label] = "snr %.1f dB below %.1f dB" % (entry.get("snr_db", 0.0), limits["min_snr_db"])
        if index >= len(expected):
            continue
        if "error_pct" not in entry:
            continue
        if abs(entry["error_pct"]) > limits["max_freq_error_pct"]:
            failures[label] = "detected %s Hz instead of %s Hz (%+.1f%%)" % (
                entry.get("f0_hz"), entry.get("expected_hz"), entry["error_pct"])
    return not failures, failures


def analyze(path, notes=DEFAULT_NOTES, thresholds=None):
    """Verify an existing recording offline."""
    samples, rate = read_wav(path)
    measured = analyze_waveform(samples, rate, parse_notes(notes), thresholds)
    measured["wav"] = os.path.abspath(path)
    return measured


# ── Device control ──────────────────────────────────────────────────


def _controller(port):
    try:
        from .mpos_controller import MPOSController
    except ImportError:
        from mpos_controller import MPOSController
    return MPOSController(backend="serial", port=port)


def _espressif_usb_product():
    """Return the USB product id of the attached Espressif device (e.g. 4001)."""
    try:
        listed = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (listed.stdout or "").splitlines():
        match = re.search(r"ID 303a:([0-9a-fA-F]{4})", line)
        if match is not None:
            return match.group(1).lower()
    return None


def relay_cycle(port, off_seconds=3.0, wait_seconds=60.0, settle_seconds=8.0, device_port=DEFAULT_PORT):
    """Power-cycle the badge through a USB relay (CH340) and wait for its port.

    The CDC node can appear before USB enumeration has finished; opening it that
    early wedges the session (EPROTO), so wait a settle period after the node
    shows up, exactly like ``test_runner.py --relayport`` does. ``lsusb`` is used
    to wait for the application interface (303a:4001) instead of the ROM one
    (303a:1001) when it is available.
    """
    try:
        import serial
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise BuzzerError("pyserial is required for --relayport: pip install pyserial") from exc
    with serial.Serial(port, 9600, timeout=1) as handle:
        handle.write(bytes([0xA0, 0x01, 0x00, 0xA1]))
    deadline = time.monotonic() + 8.0
    while os.path.exists(device_port) and time.monotonic() < deadline:
        time.sleep(0.2)
    time.sleep(max(0.0, off_seconds))
    with serial.Serial(port, 9600, timeout=1) as handle:
        handle.write(bytes([0xA0, 0x01, 0x01, 0xA2]))
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if os.path.exists(device_port):
            break
        time.sleep(0.5)
    else:
        raise BuzzerError("%s did not come back %.0fs after the relay cycle" % (device_port, wait_seconds))
    boot_deadline = time.monotonic() + 20.0
    while _espressif_usb_product() == "1001" and time.monotonic() < boot_deadline:
        time.sleep(0.5)
    time.sleep(max(0.0, settle_seconds))
    return True


def open_controller(port, relayport=None, attempts=3):
    """Open the serial controller, power-cycling the badge between attempts."""
    controller = _controller(port)
    last_error = None
    for attempt in range(attempts):
        try:
            if controller.start():
                return controller
            last_error = "controller.start() returned false"
        except Exception as exc:
            last_error = exc
        try:
            controller.stop()
        except Exception:
            pass
        if attempt < attempts - 1:
            if relayport:
                relay_cycle(relayport, device_port=port)
            else:
                time.sleep(3.0)
        controller = _controller(port)
    raise BuzzerError(
        "could not open %s: %s (is the badge connected? try --relayport /dev/ttyUSB0)"
        % (port, last_error)
    )


def _play_notes(controller, rtttl, volume):
    code = (
        "from mpos import AudioManager\n"
        "out = AudioManager.find_output_by_kind('buzzer')\n"
        "if out is None:\n"
        "    print('BUZZER_MISSING')\n"
        "else:\n"
        "    AudioManager.player(rtttl=%r, stream_type=1, volume=%d, output=out).start()\n"
        "    print('BUZZER_STARTED')\n"
    ) % (rtttl, int(volume))
    output = controller.exec(code, timeout=20)
    text = output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output)
    if "BUZZER_STARTED" not in text:
        raise BuzzerError("could not start buzzer playback: %s" % (text.strip() or "no output"))
    return text


# ── Artifacts and verify ────────────────────────────────────────────


def save_artifacts(out_dir, label, wav_path, measured, duration=4, bpm=60):
    """Write the measurement JSON next to the recording; returns artifact paths."""
    os.makedirs(out_dir, exist_ok=True)
    entry = dict(measured)
    entry["label"] = label
    entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    entry["note_duration_s"] = round(note_duration_s(duration, bpm), 3)
    json_path = os.path.join(out_dir, "metrics.json")
    with open(json_path, "w") as handle:
        json.dump(entry, handle, indent=1)
    jsonl_path = os.path.join(out_dir, "metrics.jsonl")
    with open(jsonl_path, "a") as handle:
        handle.write(json.dumps(entry) + "\n")
    return {"wav": wav_path, "metrics_json": json_path, "metrics_jsonl": jsonl_path}


def verify(port=DEFAULT_PORT, device=None, notes=DEFAULT_NOTES, volume=DEFAULT_VOLUME,
           out_dir=DEFAULT_OUT_DIR, label="buzzer", thresholds=None, relayport=None,
           controller=None, sample_rate=DEFAULT_RATE, pre_roll=0.8, tail=1.5, settle=1.5,
           bpm=60, duration=4, name="BUZZER"):
    """Play *notes* on the badge buzzer, record them and gate pass/fail."""
    note_list = parse_notes(notes)
    if not 0 <= int(volume) <= 100:
        raise BuzzerError("volume must be 0-100, got %s" % volume)
    capture = find_capture_device(device)
    if relayport:
        relay_cycle(relayport, device_port=port)
    owns_controller = controller is None
    rtttl = build_rtttl(note_list, duration=duration, bpm=bpm, name=name)
    os.makedirs(out_dir, exist_ok=True)
    wav_path = os.path.join(out_dir, "%s-%s.wav" % (label, time.strftime("%Y%m%d-%H%M%S")))
    if owns_controller:
        controller = open_controller(port, relayport)
    try:
        time.sleep(max(0.0, float(settle)))
        process = start_recording(capture, wav_path, sample_rate)
        try:
            wait_for_recording(process, wav_path)
            time.sleep(max(0.0, float(pre_roll)))
            _play_notes(controller, rtttl, volume)
            time.sleep(note_duration_s(duration, bpm) * len(note_list) + max(0.0, float(tail)))
        finally:
            stop_recording(process, wav_path)
    finally:
        if owns_controller:
            controller.stop()
    samples, rate = read_wav(wav_path)
    measured = analyze_waveform(samples, rate, note_list, thresholds)
    measured["rtttl"] = rtttl
    measured["volume"] = int(volume)
    measured["capture_device"] = capture.to_dict()
    measured["artifacts"] = save_artifacts(out_dir, label, wav_path, measured, duration, bpm)
    measured["wav"] = wav_path
    return measured


# ── CLI ─────────────────────────────────────────────────────────────


def _add_threshold_args(parser):
    parser.add_argument("--min-snr-db", type=float, default=DEFAULT_THRESHOLDS["min_snr_db"])
    parser.add_argument("--max-freq-error", type=float, default=DEFAULT_THRESHOLDS["max_freq_error_pct"],
                        help="allowed frequency error in percent")
    parser.add_argument("--min-duration", type=float, default=DEFAULT_THRESHOLDS["min_duration_s"],
                        help="ignore loud bursts shorter than this (seconds)")


def _thresholds_from_args(args):
    return {
        "min_snr_db": args.min_snr_db,
        "max_freq_error_pct": args.max_freq_error,
        "min_duration_s": args.min_duration,
    }


def _add_capture_args(parser):
    parser.add_argument("--device", default=DEFAULT_DEVICE,
                        help="plughw:CARD,DEV, a card number, or an alsa_input.* PulseAudio source")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)


def build_parser():
    parser = argparse.ArgumentParser(description="Acoustic verification of the MicroPythonOS buzzer")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list capture devices")

    record_parser = commands.add_parser("record", help="record a WAV file (no device control)")
    _add_capture_args(record_parser)
    record_parser.add_argument("--seconds", type=float, required=True)
    record_parser.add_argument("--out", required=True)

    analyze_parser = commands.add_parser("analyze", help="verify an existing WAV offline")
    analyze_parser.add_argument("--wav", required=True)
    analyze_parser.add_argument("--notes", default=DEFAULT_NOTES)
    _add_threshold_args(analyze_parser)
    analyze_parser.add_argument("--out-dir", default=None)
    analyze_parser.add_argument("--label", default="analyze")

    verify_parser = commands.add_parser("verify", help="play notes, record them and gate pass/fail")
    _add_capture_args(verify_parser)
    verify_parser.add_argument("--port", default=DEFAULT_PORT)
    verify_parser.add_argument("--relayport", default=DEFAULT_RELAY,
                               help="USB relay port used to power-cycle the badge first")
    verify_parser.add_argument("--notes", default=DEFAULT_NOTES)
    verify_parser.add_argument("--volume", type=int, default=DEFAULT_VOLUME)
    verify_parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    verify_parser.add_argument("--label", default="buzzer")
    verify_parser.add_argument("--settle", type=float, default=1.5)
    _add_threshold_args(verify_parser)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "list":
        print(json.dumps({"capture_devices": [device.to_dict() for device in list_capture_devices()]}, indent=1))
        return 0

    if args.command == "record":
        capture = find_capture_device(args.device)
        path = record(capture, args.seconds, args.out, args.rate)
        print(json.dumps({"wav": os.path.abspath(path), "device": capture.to_dict()}, indent=1))
        return 0

    if args.command == "analyze":
        measured = analyze(args.wav, args.notes, _thresholds_from_args(args))
        if args.out_dir:
            save_artifacts(args.out_dir, args.label, os.path.abspath(args.wav), measured)
        print(json.dumps(measured, indent=1))
        return 0 if measured.get("ok") else 1

    measured = verify(
        port=args.port, device=args.device, notes=args.notes, volume=args.volume,
        out_dir=args.out_dir, label=args.label, thresholds=_thresholds_from_args(args),
        relayport=args.relayport, sample_rate=args.rate, settle=args.settle,
    )
    print(json.dumps(measured, indent=1))
    return 0 if measured.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
