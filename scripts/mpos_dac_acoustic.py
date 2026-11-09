#!/usr/bin/env python3
"""Acoustic verification of the badge DAC / headset output.

Plays a known tone sequence through an i2s output ("Headset Output", the
on-board DAC jack) and records it with a microphone input on the host. This is
the analogue counterpart of ``mpos_buzzer_acoustic.py``: the buzzer is a PWM
pin checked from the air, while this checks the whole digital-to-analogue path
(decoder -> i2s -> DAC -> jack -> cable -> capture device).

Commands:
    list     enumerate capture devices
    verify   play tones (or a file) on the badge, record and gate pass/fail

Examples:
    python3 scripts/mpos_dac_acoustic.py list
    python3 scripts/mpos_dac_acoustic.py verify --capture-gain 20
    python3 scripts/mpos_dac_acoustic.py verify --notes a4,a5,a6 --relayport /dev/ttyUSB0
    python3 scripts/mpos_dac_acoustic.py verify --file /music/test.mp3 --notes a4,a5,a6

The manual entry point is ``tests/manual_test_dac.py``. The rig needs the badge
headphone jack wired into a capture input; on zbox1 that is the on-board ALC892
microphone jack (``plughw:0,0``), with ``Capture`` around +4 dB (value 20/46).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

DEFAULT_PORT = os.environ.get("MPOS_DAC_PORT", "/dev/ttyACM0")
DEFAULT_RELAY = os.environ.get("MPOS_DAC_RELAY")
DEFAULT_DEVICE = os.environ.get("MPOS_DAC_DEVICE")
DEFAULT_OUT_DIR = os.environ.get("MPOS_DAC_OUT", "tmp/dactests")
DEFAULT_OUTPUT = os.environ.get("MPOS_DAC_OUTPUT", "Headset Output")
DEFAULT_NOTES = "a4,a5,a6"
DEFAULT_VOLUME = 100
DEFAULT_RATE = 44100
DEFAULT_TONE_RATE = 22050
DEFAULT_AMPLITUDE = 8000
DEFAULT_NOTE_SECONDS = 1.0
DEFAULT_TONES_PATH = "/dac_tones.wav"

DEFAULT_THRESHOLDS = dict(
    min_snr_db=12.0,
    max_freq_error_pct=2.0,
    min_duration_s=0.3,
)

try:
    from . import mpos_buzzer_acoustic as base
except ImportError:
    import mpos_buzzer_acoustic as base

AcousticError = base.BuzzerError


# ── Tones and device playback ───────────────────────────────────────


def tone_sequence(notes, rate=DEFAULT_TONE_RATE, note_seconds=DEFAULT_NOTE_SECONDS,
                  gap_ratio=0.1):
    """Return ``(frequency, tone_samples, gap_samples)`` per note."""
    sequence = []
    for note in notes:
        frequency = base.note_frequency(note)
        total = int(round(float(note_seconds) * rate))
        gap = int(round(total * float(gap_ratio)))
        sequence.append((frequency, total - gap, gap))
    return sequence


def build_tone_source(sequence, path, rate=DEFAULT_TONE_RATE, amplitude=DEFAULT_AMPLITUDE,
                      pre_s=0.4, tail_s=0.8):
    """MicroPython source that renders a mono PCM16 WAV with sine tones.

    The generated code is plain Python (math + file writes), so the host tests
    can execute it with CPython and compare the result to a reference WAV.
    """
    return """
import math

rate = %(rate)d
amplitude = %(amplitude)d
path = %(path)r
sequence = %(sequence)r
pre_samples = int(rate * %(pre_s)r)
tail_samples = int(rate * %(tail_s)r)
total_samples = pre_samples + tail_samples + sum(tone + gap for _, tone, gap in sequence)

silence = bytes(2048)


def write_silence(handle, samples):
    remaining = samples * 2
    while remaining > 0:
        count = min(len(silence), remaining)
        handle.write(silence[:count])
        remaining -= count


def write_tone(handle, frequency, samples):
    data = bytearray(samples * 2)
    phase = 0.0
    step = 2.0 * math.pi * frequency / rate
    for index in range(samples):
        value = int(amplitude * math.sin(phase)) & 0xFFFF
        data[index * 2] = value & 0xFF
        data[index * 2 + 1] = value >> 8
        phase += step
        if phase >= 2.0 * math.pi:
            phase -= 2.0 * math.pi
    handle.write(data)


with open(path, "wb") as handle:
    handle.write(b"RIFF\\x00\\x00\\x00\\x00WAVEfmt ")
    handle.write((16).to_bytes(4, "little"))
    handle.write((1).to_bytes(2, "little"))
    handle.write((1).to_bytes(2, "little"))
    handle.write(rate.to_bytes(4, "little"))
    handle.write((rate * 2).to_bytes(4, "little"))
    handle.write((2).to_bytes(2, "little"))
    handle.write((16).to_bytes(2, "little"))
    handle.write(b"data\\x00\\x00\\x00\\x00")
    write_silence(handle, pre_samples)
    for frequency, tone_samples, gap_samples in sequence:
        write_tone(handle, frequency, tone_samples)
        write_silence(handle, gap_samples)
    write_silence(handle, tail_samples)
    data_size = total_samples * 2
    handle.seek(4)
    handle.write((data_size + 36).to_bytes(4, "little"))
    handle.seek(40)
    handle.write(data_size.to_bytes(4, "little"))

print("DAC_WAV_OK", total_samples)
""" % {
        "rate": int(rate),
        "amplitude": int(amplitude),
        "path": path,
        "sequence": list(sequence),
        "pre_s": float(pre_s),
        "tail_s": float(tail_s),
    }


def play_source(path, output=DEFAULT_OUTPUT, volume=DEFAULT_VOLUME, limit_s=600):
    """MicroPython source that plays *path* and blocks until playback ends."""
    return """
import time

from mpos import AudioManager

out = AudioManager.find_output_by_name(%(output)r)
if out is None:
    print("DAC_OUTPUT_MISSING")
else:
    player = AudioManager.player(
        file_path=%(path)r, stream_type=AudioManager.STREAM_MUSIC,
        output=out, volume=%(volume)d)
    player.start()
    print("DAC_PLAY_STARTED", out.name)
    started = time.ticks_ms()
    for _ in range(40):
        if player.is_playing():
            break
        time.sleep_ms(50)
    while player.is_playing():
        time.sleep_ms(50)
        if time.ticks_diff(time.ticks_ms(), started) > %(limit_ms)d:
            print("DAC_PLAY_TIMEOUT")
            break
    print("DAC_PLAY_DONE", time.ticks_diff(time.ticks_ms(), started))
""" % {"output": output, "path": path, "volume": int(volume),
       "limit_ms": int(float(limit_s) * 1000)}


def _exec_text(controller, code, timeout=30):
    output = controller.exec(code, timeout=timeout)
    if isinstance(output, bytes):
        return output.decode("utf-8", "replace")
    return str(output)


def prepare_tones(controller, notes, path=DEFAULT_TONES_PATH, rate=DEFAULT_TONE_RATE,
                  amplitude=DEFAULT_AMPLITUDE, note_seconds=DEFAULT_NOTE_SECONDS,
                  pre_s=0.4, tail_s=0.8):
    """Render the tone WAV on the badge; returns the playback duration in seconds."""
    sequence = tone_sequence(notes, rate=rate, note_seconds=note_seconds)
    text = _exec_text(controller, build_tone_source(
        sequence, path, rate=rate, amplitude=amplitude, pre_s=pre_s, tail_s=tail_s))
    if "DAC_WAV_OK" not in text:
        raise AcousticError("could not generate the tone WAV on the badge: %s" % text.strip())
    return float(pre_s) + sum(tone + gap for _, tone, gap in sequence) / float(rate) + float(tail_s)


# ── Capture devices and mixer ───────────────────────────────────────


def find_onboard_capture_device(spec=None):
    """Pick the on-board (non-USB) capture device, or honour *spec*."""
    if spec:
        return base.find_capture_device(spec)
    devices = base.list_capture_devices()
    if not devices:
        raise AcousticError("no ALSA capture devices found; connect the cable or pass --device")
    onboard = [device for device in devices
               if "usb" not in (device.card_name + " " + device.device_name).lower()
               and "hdmi" not in (device.card_name + " " + device.device_name).lower()]
    if not onboard:
        return base.find_capture_device()
    preferred = [device for device in onboard
                 if "analog" in (device.card_name + " " + device.device_name).lower()]
    return (preferred or onboard)[0]


def _amixer_capture_value(card):
    """Return the current ``Capture`` value string (e.g. ``28,28``) or None."""
    try:
        listed = subprocess.run(
            ["amixer", "-c", str(card), "cget", "name=Capture Volume"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r":\s*values=(\S+)", listed.stdout or "")
    return match.group(1) if match else None


def set_capture_gain(device, value):
    """Set the ALSA capture volume; returns a callable that restores it."""
    if value is None or device.card < 0:
        return lambda: None
    original = _amixer_capture_value(device.card)
    try:
        subprocess.run(
            ["amixer", "-c", str(device.card), "sset", "Capture", str(int(value))],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return lambda: None

    def restore():
        if original is None:
            return
        try:
            subprocess.run(
                ["amixer", "-c", str(device.card), "cset", "name=Capture Volume", original],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass

    return restore


# ── Measurement ─────────────────────────────────────────────────────


def measure_waveform(samples, rate, thresholds=None):
    """Report loud segments without expecting specific notes (file mode)."""
    np = base._numpy()
    limits = dict(DEFAULT_THRESHOLDS)
    limits.update(thresholds or {})
    spans, noise, threshold = base._segment(samples, rate, limits["min_duration_s"])
    noise = max(noise, 1e-12)
    measured = {
        "sample_rate": rate,
        "duration_s": round(samples.size / float(rate), 3),
        "noise_floor_dbfs": round(20.0 * np.log10(noise), 1),
        "threshold_rms": round(threshold, 5),
        "segments": [],
    }
    for index, (first, last) in enumerate(spans):
        span = samples[first:last]
        span = span - span.mean()
        spectrum = np.abs(np.fft.rfft(span * np.hanning(span.size)))
        frequencies = np.fft.rfftfreq(span.size, 1.0 / rate)
        mask = frequencies >= 150.0
        peak_hz = float(frequencies[mask][int(np.argmax(spectrum[mask]))]) if mask.any() else 0.0
        rms = float(np.sqrt(np.mean(span * span)))
        snr = float(20.0 * np.log10(max(rms, 1e-12) / noise))
        measured["segments"].append({
            "index": index,
            "start_s": round(first / float(rate), 3),
            "end_s": round(last / float(rate), 3),
            "duration_s": round((last - first) / float(rate), 3),
            "rms_dbfs": round(20.0 * np.log10(max(rms, 1e-12)), 1),
            "snr_db": round(snr, 1),
            "peak_hz": round(peak_hz, 1),
            "ok": bool(snr >= limits["min_snr_db"]),
        })
    failures = {}
    if not measured["segments"]:
        failures["segments"] = "no audio detected"
    for entry in measured["segments"]:
        if not entry["ok"]:
            failures["segment_%d" % entry["index"]] = "snr %.1f dB below %.1f dB" % (
                entry["snr_db"], limits["min_snr_db"])
    measured["ok"] = not failures
    measured["failures"] = failures
    return measured


def analyze_recording(samples, rate, notes=None, thresholds=None):
    """Analyze the capture, matching notes when given."""
    if notes:
        return base.analyze_waveform(samples, rate, notes, thresholds)
    return measure_waveform(samples, rate, thresholds)


# ── Verify ──────────────────────────────────────────────────────────


def verify(port=DEFAULT_PORT, device=None, notes=DEFAULT_NOTES, file=None,
           output=DEFAULT_OUTPUT, volume=DEFAULT_VOLUME, out_dir=DEFAULT_OUT_DIR,
           label="dac", thresholds=None, relayport=None, controller=None,
           sample_rate=DEFAULT_RATE, capture_gain=None, tone_rate=DEFAULT_TONE_RATE,
           amplitude=DEFAULT_AMPLITUDE, note_seconds=DEFAULT_NOTE_SECONDS,
           pre_roll=0.5, tail=1.5, settle=1.5, play_timeout=None):
    """Play tones (or *file*) on the badge DAC, record and gate pass/fail."""
    note_list = base.parse_notes(notes) if notes else []
    if not 0 <= int(volume) <= 100:
        raise AcousticError("volume must be 0-100, got %s" % volume)
    capture = find_onboard_capture_device(device)
    if relayport:
        base.relay_cycle(relayport, device_port=port)
    owns_controller = controller is None
    if owns_controller:
        controller = base.open_controller(port, relayport)
    tones_path = None
    duration = None
    restore_gain = lambda: None
    try:
        time.sleep(max(0.0, float(settle)))
        if file is None:
            tones_path = DEFAULT_TONES_PATH
            duration = prepare_tones(
                controller, note_list, path=tones_path, rate=tone_rate,
                amplitude=amplitude, note_seconds=note_seconds)
        restore_gain = set_capture_gain(capture, capture_gain)
        os.makedirs(out_dir, exist_ok=True)
        wav_path = os.path.join(out_dir, "%s-%s.wav" % (label, time.strftime("%Y%m%d-%H%M%S")))
        process = base.start_recording(capture, wav_path, sample_rate)
        try:
            base.wait_for_recording(process, wav_path)
            time.sleep(max(0.0, float(pre_roll)))
            timeout = play_timeout or (300 if duration is None else int(duration) + 60)
            text = _exec_text(controller, play_source(
                tones_path or file, output=output, volume=volume, limit_s=timeout),
                timeout=timeout)
            if "DAC_PLAY_STARTED" not in text:
                raise AcousticError("could not start playback: %s" % (text.strip() or "no output"))
            time.sleep(max(0.0, float(tail)))
        finally:
            base.stop_recording(process, wav_path)
    finally:
        restore_gain()
        if tones_path is not None:
            try:
                _exec_text(controller, "import os\nos.remove(%r)\n" % tones_path, timeout=15)
            except Exception:
                pass
        if owns_controller:
            controller.stop()
    samples, rate = base.read_wav(wav_path)
    measured = analyze_recording(samples, rate, note_list, thresholds)
    measured["mode"] = "file" if file else "tones"
    measured["output"] = output
    measured["volume"] = int(volume)
    if file:
        measured["file"] = file
    measured["capture_device"] = capture.to_dict()
    measured["artifacts"] = base.save_artifacts(out_dir, label, wav_path, measured)
    measured["wav"] = wav_path
    return measured


# ── CLI ─────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(description="Acoustic verification of the badge DAC output")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list capture devices")

    verify_parser = commands.add_parser("verify", help="play audio on the badge and analyze the capture")
    verify_parser.add_argument("--port", default=DEFAULT_PORT)
    verify_parser.add_argument("--relayport", default=DEFAULT_RELAY,
                               help="USB relay port used to power-cycle the badge first")
    verify_parser.add_argument("--device", default=DEFAULT_DEVICE,
                               help="capture device: plughw:CARD,DEV, a card number or an alsa_input.* source")
    verify_parser.add_argument("--notes", default=None,
                               help="comma-separated notes to play and expect (default %s)" % DEFAULT_NOTES)
    verify_parser.add_argument("--file", default=None,
                               help="play an existing file on the badge instead of generating tones")
    verify_parser.add_argument("--output", default=DEFAULT_OUTPUT,
                               help="AudioManager output name (default %s)" % DEFAULT_OUTPUT)
    verify_parser.add_argument("--volume", type=int, default=DEFAULT_VOLUME)
    verify_parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    verify_parser.add_argument("--label", default="dac")
    verify_parser.add_argument("--capture-gain", type=int, default=None,
                               help="set ALSA 'Capture' to this value for the run, then restore it")
    verify_parser.add_argument("--settle", type=float, default=1.5)
    verify_parser.add_argument("--min-snr-db", type=float, default=DEFAULT_THRESHOLDS["min_snr_db"])
    verify_parser.add_argument("--max-freq-error", type=float, default=DEFAULT_THRESHOLDS["max_freq_error_pct"],
                               help="allowed frequency error in percent")
    verify_parser.add_argument("--min-duration", type=float, default=DEFAULT_THRESHOLDS["min_duration_s"])
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "list":
        print(json.dumps({"capture_devices": [
            device.to_dict() for device in base.list_capture_devices()]}, indent=1))
        return 0

    thresholds = {
        "min_snr_db": args.min_snr_db,
        "max_freq_error_pct": args.max_freq_error,
        "min_duration_s": args.min_duration,
    }
    notes = args.notes
    if notes is None and args.file is None:
        notes = DEFAULT_NOTES
    measured = verify(
        port=args.port, device=args.device, notes=notes, file=args.file,
        output=args.output, volume=args.volume, out_dir=args.out_dir,
        label=args.label, thresholds=thresholds, relayport=args.relayport,
        capture_gain=args.capture_gain,
    )
    print(json.dumps(measured, indent=1))
    return 0 if measured.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
