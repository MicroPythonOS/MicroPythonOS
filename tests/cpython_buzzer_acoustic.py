#!/usr/bin/env python3
"""CPython tests for scripts/mpos_buzzer_acoustic.py — no microphone or device needed.

Synthesizes square-wave notes with a piezo-like resonance around 3.5 kHz plus
background noise, writes them to a temporary WAV file and checks that the
analysis segments them and recovers the played frequency. Skipped when numpy
is missing.

Usage:
    python3 tests/cpython_buzzer_acoustic.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import numpy as np
except ImportError:  # pragma: no cover - depends on the host
    np = None

from scripts import mpos_buzzer_acoustic as buzzer  # noqa: E402


HAVE_NUMPY = np is not None


def synth_note(frequency, seconds, rate=44100, resonance=3500.0, width=900.0, boost=6.0):
    """A square-wave-ish note whose harmonics are boosted near *resonance*."""
    time_axis = np.arange(int(seconds * rate)) / float(rate)
    signal = np.zeros_like(time_axis)
    for harmonic in range(1, 16):
        partial = frequency * harmonic
        if partial > rate / 2.0:
            break
        # 1/k square-wave envelope, a low-frequency rolloff like the mic, and a
        # piezo resonance peak: at 440 Hz the fundamental ends up far weaker
        # than the boosted harmonics, exactly like the real rig.
        highpass = (partial / 500.0) ** 2 / (1.0 + (partial / 500.0) ** 2)
        amplitude = (1.0 / harmonic) * highpass
        amplitude *= 1.0 + boost * np.exp(-0.5 * ((partial - resonance) / width) ** 2)
        signal += amplitude * np.sin(2.0 * np.pi * partial * time_axis + 0.3 * harmonic)
    return signal / np.abs(signal).max()


def synth_recording(frequencies, rate=44100, note_s=0.9, gap_s=0.1, pre_s=0.8,
                    post_s=0.5, level=0.3, noise_db=-45.0, seed=7):
    """Concatenate notes with silence between them, then add room noise."""
    parts = [np.zeros(int(pre_s * rate))]
    for frequency in frequencies:
        parts.append(level * synth_note(frequency, note_s, rate))
        parts.append(np.zeros(int(gap_s * rate)))
    parts.append(np.zeros(int(post_s * rate)))
    signal = np.concatenate(parts)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 10.0 ** (noise_db / 20.0), signal.size)
    return np.clip(signal + noise, -1.0, 1.0)


class TestNotes(unittest.TestCase):

    def test_note_frequencies_match_firmware_table(self):
        self.assertAlmostEqual(buzzer.note_frequency("a4"), 440.0)
        self.assertAlmostEqual(buzzer.note_frequency("a5"), 880.0)
        self.assertAlmostEqual(buzzer.note_frequency("a7"), 3520.0)
        self.assertAlmostEqual(buzzer.note_frequency("c6"), 1046.4)
        self.assertAlmostEqual(buzzer.note_frequency("c#6"), 1108.8)

    def test_parse_notes_accepts_spaces_and_case(self):
        self.assertEqual(buzzer.parse_notes(" A4, c#6 ,a7 "), ["a4", "c#6", "a7"])

    def test_invalid_note_rejected(self):
        for note in ("a3", "h4", "a", "a#9", "a4b"):
            with self.assertRaises(buzzer.BuzzerError):
                buzzer.note_frequency(note)

    def test_rtttl_string(self):
        self.assertEqual(buzzer.build_rtttl(["a4", "a5"]), "BUZZER:d=4,b=60:a4,a5")
        self.assertEqual(buzzer.build_rtttl(["a4"], duration=2, bpm=120, name="POC"), "POC:d=2,b=120:a4")

    def test_note_duration(self):
        self.assertAlmostEqual(buzzer.note_duration_s(4, 60), 1.0)
        self.assertAlmostEqual(buzzer.note_duration_s(2, 60), 2.0)


class TestDeviceParsing(unittest.TestCase):

    ARECORD = (
        "**** List of CAPTURE Hardware Devices ****\n"
        "card 0: Intel [HDA Intel], device 0: ALC892 Analog [ALC892 Analog]\n"
        "  Subdevices: 1/1\n"
        "card 2: C925e [Logitech Webcam C925e], device 0: USB Audio [USB Audio]\n"
        "card 3: Device [USB Audio Device], device 0: USB Audio [USB Audio]\n"
    )

    def test_parse_arecord_listing(self):
        devices = buzzer.parse_arecord_listing(self.ARECORD)
        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[2].card, 3)
        self.assertEqual(devices[2].device, 0)
        self.assertEqual(devices[2].card_name, "USB Audio Device")
        self.assertEqual(devices[2].alsa, "plughw:3,0")

    def test_webcam_flagged(self):
        devices = buzzer.parse_arecord_listing(self.ARECORD)
        self.assertTrue(devices[1].is_webcam)
        self.assertFalse(devices[2].is_webcam)

    def test_parse_pactl_sources(self):
        text = (
            "\tName: alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback\n"
            "\tDescription: USB Audio Device Mono\n"
            "\tProperties:\n"
            '\t\talsa.device = "0"\n'
            '\t\talsa.card = "3"\n'
            "\tName: alsa_input.usb-046d_Logitech_Webcam-02.analog-stereo\n"
            '\t\talsa.card = "2"\n'
            '\t\talsa.device = "0"\n'
        )
        mapping = buzzer.parse_pactl_sources(text)
        self.assertEqual(mapping[(3, 0)], "alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback")
        self.assertEqual(mapping[(2, 0)], "alsa_input.usb-046d_Logitech_Webcam-02.analog-stereo")

    def test_device_spec(self):
        self.assertEqual(buzzer._device_from_spec("plughw:3,0").alsa, "plughw:3,0")
        self.assertEqual(buzzer._device_from_spec("hw:2,1").alsa, "plughw:2,1")
        self.assertEqual(buzzer._device_from_spec("3").alsa, "plughw:3,0")
        pulse = buzzer._device_from_spec("alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback")
        self.assertEqual(pulse.pulse_source, "alsa_input.usb-GeneralPlus_USB_Audio_Device-00.mono-fallback")
        with self.assertRaises(buzzer.BuzzerError):
            buzzer._device_from_spec("nonsense")


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestAnalysis(unittest.TestCase):

    def test_detects_played_notes(self):
        signal = synth_recording([440.0, 880.0, 3520.0])
        measured = buzzer.analyze_waveform(signal, 44100, ["a4", "a5", "a7"])
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(len(measured["segments"]), 3)
        for entry in measured["segments"]:
            self.assertLessEqual(abs(entry["error_pct"]), 1.0, entry)
            self.assertGreater(entry["snr_db"], 12.0, entry)

    def test_low_note_folded_from_dominant_harmonic(self):
        signal = synth_recording([440.0])
        measured = buzzer.analyze_waveform(signal, 44100, ["a4"])
        self.assertTrue(measured["ok"], measured.get("failures"))
        entry = measured["segments"][0]
        self.assertNotAlmostEqual(entry["peak_hz"], 440.0, delta=40.0,
                                  msg="resonance should make a harmonic louder than the fundamental")
        self.assertEqual(entry["harmonic"], int(round(entry["peak_hz"] / 440.0)))
        self.assertLessEqual(abs(entry["error_pct"]), 1.0)

    def test_silence_reports_no_segments(self):
        signal = synth_recording([])
        measured = buzzer.analyze_waveform(signal, 44100, ["a4"])
        self.assertFalse(measured["ok"])
        self.assertEqual(measured["segments"], [])
        self.assertIn("segments", measured["failures"])

    def test_wrong_note_fails(self):
        signal = synth_recording([880.0])
        measured = buzzer.analyze_waveform(signal, 44100, ["c6"])
        self.assertFalse(measured["ok"])
        self.assertIn("c6", measured["failures"])

    def test_short_blip_is_ignored(self):
        signal = synth_recording([880.0], note_s=0.1)
        measured = buzzer.analyze_waveform(signal, 44100, ["a5"])
        self.assertEqual(measured["segments"], [])

    def test_single_long_note_still_detected(self):
        signal = synth_recording([880.0], note_s=2.5, pre_s=0.3, post_s=0.3)
        measured = buzzer.analyze_waveform(signal, 44100, ["a5"])
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(len(measured["segments"]), 1)

    def test_wav_roundtrip(self):
        signal = synth_recording([880.0])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.wav")
            buzzer.write_wav(path, signal, 44100)
            loaded, rate = buzzer.read_wav(path)
        self.assertEqual(rate, 44100)
        self.assertEqual(loaded.size, signal.size)
        self.assertLess(float(np.abs(loaded - signal).max()), 1e-3)

    def test_analyze_file(self):
        signal = synth_recording([880.0, 1760.0])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "note.wav")
            buzzer.write_wav(path, signal, 44100)
            measured = buzzer.analyze(path, "a5,a6")
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(measured["wav"], os.path.abspath(path))

    def test_check_thresholds(self):
        good = {
            "expected": [{"note": "a4", "frequency_hz": 440.0}],
            "segments": [{"note": "a4", "snr_db": 20.0, "error_pct": 0.2, "f0_hz": 441.0, "expected_hz": 440.0}],
        }
        ok, failures = buzzer.check_thresholds(good)
        self.assertTrue(ok, failures)
        bad = {
            "expected": good["expected"],
            "segments": [{"note": "a4", "snr_db": 3.0, "error_pct": 9.0, "f0_hz": 480.0, "expected_hz": 440.0}],
        }
        ok, failures = buzzer.check_thresholds(bad)
        self.assertFalse(ok)
        self.assertIn("a4", failures)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestVerifyOrchestration(unittest.TestCase):

    def test_verify_with_fake_rig(self):
        played = {}

        class Controller:
            def start(self):
                return True

            def stop(self):
                pass

            def exec(self, code, timeout=30):
                return b"BUZZER_STARTED"

        signal = synth_recording([880.0, 1760.0])
        original = (buzzer.find_capture_device, buzzer.start_recording, buzzer.stop_recording,
                    buzzer.wait_for_recording, buzzer._play_notes, buzzer.time.sleep)

        def fake_start(device, out_path, rate):
            return out_path

        def fake_stop(process, out_path=None):
            buzzer.write_wav(out_path, signal, 44100)

        def fake_play(controller, rtttl, volume):
            played["rtttl"] = rtttl
            played["volume"] = volume

        try:
            buzzer.find_capture_device = lambda spec=None: buzzer.CaptureDevice(3, 0, "USB Audio Device", "USB Audio")
            buzzer.start_recording = fake_start
            buzzer.stop_recording = fake_stop
            buzzer.wait_for_recording = lambda process, out_path, timeout=8.0: True
            buzzer._play_notes = fake_play
            buzzer.time.sleep = lambda seconds: None
            with tempfile.TemporaryDirectory() as tmp:
                measured = buzzer.verify(controller=Controller(), notes="a5,a6", out_dir=tmp,
                                         settle=0, pre_roll=0, tail=0)
                self.assertTrue(os.path.isfile(measured["artifacts"]["metrics_json"]))
        finally:
            (buzzer.find_capture_device, buzzer.start_recording, buzzer.stop_recording,
             buzzer.wait_for_recording, buzzer._play_notes, buzzer.time.sleep) = original
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(played["rtttl"], "BUZZER:d=4,b=60:a5,a6")
        self.assertEqual(played["volume"], 100)

    def test_play_notes_rejects_missing_buzzer(self):
        class Controller:
            def exec(self, code, timeout=30):
                return b"BUZZER_MISSING"

        with self.assertRaises(buzzer.BuzzerError):
            buzzer._play_notes(Controller(), "BUZZER:d=4,b=60:a4", 100)

    def test_verify_retries_controller_start(self):
        attempts = {"n": 0, "stops": 0}

        class Flaky:
            def start(self):
                attempts["n"] += 1
                if attempts["n"] < 3:
                    raise OSError(71, "Protocol error")
                return True

            def stop(self):
                attempts["stops"] += 1

        original = (buzzer._controller, buzzer.find_capture_device, buzzer.start_recording,
                    buzzer.stop_recording, buzzer.wait_for_recording, buzzer._play_notes,
                    buzzer.time.sleep)
        try:
            buzzer._controller = lambda port: Flaky()
            buzzer.find_capture_device = lambda spec=None: buzzer.CaptureDevice(3, 0, "USB Audio Device", "USB Audio")
            buzzer.start_recording = lambda device, out_path, rate: out_path
            buzzer.stop_recording = lambda process, out_path=None: buzzer.write_wav(
                out_path, synth_recording([880.0]), 44100)
            buzzer.wait_for_recording = lambda process, out_path, timeout=8.0: True
            buzzer._play_notes = lambda controller, rtttl, volume: None
            buzzer.time.sleep = lambda seconds: None
            with tempfile.TemporaryDirectory() as tmp:
                measured = buzzer.verify(port="/dev/ttyACM0", notes="a5", out_dir=tmp,
                                         settle=0, pre_roll=0, tail=0)
        finally:
            (buzzer._controller, buzzer.find_capture_device, buzzer.start_recording,
             buzzer.stop_recording, buzzer.wait_for_recording, buzzer._play_notes,
             buzzer.time.sleep) = original
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(attempts["n"], 3)

    def test_verify_gives_up_after_three_failures(self):
        class Dead:
            def start(self):
                raise OSError(71, "Protocol error")

            def stop(self):
                pass

        original = (buzzer._controller, buzzer.find_capture_device, buzzer.time.sleep)
        try:
            buzzer._controller = lambda port: Dead()
            buzzer.find_capture_device = lambda spec=None: buzzer.CaptureDevice(3, 0, "USB Audio Device", "USB Audio")
            buzzer.time.sleep = lambda seconds: None
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(buzzer.BuzzerError) as raised:
                buzzer.verify(port="/dev/ttyACM9", notes="a5", out_dir=tmp)
        finally:
            (buzzer._controller, buzzer.find_capture_device, buzzer.time.sleep) = original
        self.assertIn("/dev/ttyACM9", str(raised.exception))
        self.assertIn("Protocol error", str(raised.exception))


class TestRecordingCommand(unittest.TestCase):

    def test_alsa_command(self):
        device = buzzer.CaptureDevice(3, 0, "USB Audio Device", "USB Audio")
        command = buzzer._capture_command(device, "/tmp/x.wav", 44100)
        self.assertEqual(command[0], "arecord")
        self.assertIn("plughw:3,0", command)
        self.assertIn("/tmp/x.wav", command)

    def test_pulse_command(self):
        device = buzzer.CaptureDevice(-1, -1, "PulseAudio", "src", pulse_source="alsa_input.foo")
        original = buzzer.shutil.which
        buzzer.shutil.which = lambda name: "/usr/bin/parecord" if name in ("parecord", "pactl") else original(name)
        try:
            command = buzzer._capture_command(device, "/tmp/x.wav", 44100)
        finally:
            buzzer.shutil.which = original
        self.assertEqual(command[0], "parecord")
        self.assertIn("--device=alsa_input.foo", command)


class TestWaitForRecording(unittest.TestCase):

    class Process:
        def __init__(self, returncode=None, stderr=b""):
            self.returncode = returncode
            self._stderr = stderr

        def poll(self):
            return self.returncode

        @property
        def stderr(self):
            import io
            return io.BytesIO(self._stderr)

    def test_returns_once_file_has_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "capture.wav")
            with open(path, "wb") as handle:
                handle.write(b"\0" * 44)
            edited = []

            def fake_sleep(seconds):
                edited.append(seconds)
                with open(path, "ab") as handle:
                    handle.write(b"\0" * 8192)

            original = buzzer.time.sleep
            buzzer.time.sleep = fake_sleep
            try:
                self.assertTrue(buzzer.wait_for_recording(self.Process(), path, timeout=1.0))
            finally:
                buzzer.time.sleep = original
            self.assertTrue(edited)

    def test_empty_file_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "capture.wav")
            with open(path, "wb") as handle:
                handle.write(b"\0" * 44)
            original = buzzer.time.sleep
            buzzer.time.sleep = lambda seconds: None
            try:
                with self.assertRaises(buzzer.BuzzerError):
                    buzzer.wait_for_recording(self.Process(), path, timeout=0.1)
            finally:
                buzzer.time.sleep = original

    def test_dead_recorder_raises_with_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "capture.wav")
            process = self.Process(returncode=1, stderr=b"device busy")
            with self.assertRaises(buzzer.BuzzerError) as raised:
                buzzer.wait_for_recording(process, path, timeout=1.0)
            self.assertIn("device busy", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
