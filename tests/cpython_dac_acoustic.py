#!/usr/bin/env python3
"""CPython tests for scripts/mpos_dac_acoustic.py — no sound card or badge needed.

Renders the on-badge tone generator with CPython, checks the WAV it produces,
and (when numpy is available) feeds synthetic captures through the analyzer.
Skipped analysis tests run everywhere numpy exists.

Usage:
    python3 tests/cpython_dac_acoustic.py
"""

import os
import sys
import tempfile
import unittest
from array import array

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    import numpy as np
except ImportError:  # pragma: no cover - depends on the host
    np = None

from scripts import mpos_buzzer_acoustic as base  # noqa: E402
from scripts import mpos_dac_acoustic as dac  # noqa: E402


HAVE_NUMPY = np is not None


def render_tones(path, notes=("a4", "a5"), **kwargs):
    """Execute the generated MicroPython source with CPython and return the path."""
    sequence = dac.tone_sequence(list(notes), **{k: v for k, v in kwargs.items()
                                                 if k in ("rate", "note_seconds")})
    source = dac.build_tone_source(
        sequence, path,
        rate=kwargs.get("rate", dac.DEFAULT_TONE_RATE),
        amplitude=kwargs.get("amplitude", dac.DEFAULT_AMPLITUDE),
        pre_s=kwargs.get("pre_s", 0.4), tail_s=kwargs.get("tail_s", 0.8))
    namespace = {"__name__": "render_tones"}
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(source, "<dac-tone-source>", "exec"), namespace)
    return path


class TestTones(unittest.TestCase):

    def test_tone_sequence(self):
        sequence = dac.tone_sequence(["a4", "a5"], rate=22050, note_seconds=1.0)
        self.assertEqual([round(item[0]) for item in sequence], [440, 880])
        for frequency, tone, gap in sequence:
            self.assertEqual(tone + gap, 22050)
            self.assertEqual(gap, 2205)

    def test_generated_wav_is_valid(self):
        import wave
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tones.wav")
            render_tones(path)
            with wave.open(path, "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getframerate(), 22050)
                frames = handle.readframes(handle.getnframes())
        samples = array("h")
        samples.frombytes(frames)
        if sys.byteorder == "big":  # pragma: no cover - little-endian hosts only
            samples.byteswap()
        expected = int(22050 * (0.4 + 2.0 + 0.8))
        self.assertAlmostEqual(len(samples), expected, delta=22050 * 0.05)
        self.assertLessEqual(max(samples), 8000)
        self.assertGreater(max(samples), 7800)
        self.assertGreaterEqual(min(samples), -8000)
        self.assertLess(min(samples), -7800)
        self.assertTrue(all(value == 0 for value in samples[: int(22050 * 0.35)]))
        self.assertTrue(any(value != 0 for value in samples[: int(22050 * 0.6)]))

    def test_generated_tone_frequency(self):
        import wave
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tones.wav")
            render_tones(path, notes=("a4",))
            with wave.open(path, "rb") as handle:
                rate = handle.getframerate()
                frames = handle.readframes(handle.getnframes())
        samples = array("h")
        samples.frombytes(frames)
        if sys.byteorder == "big":  # pragma: no cover
            samples.byteswap()
        start = int(rate * 0.45)
        span = samples[start:start + int(rate * 0.25)]
        crossings = sum(1 for first, second in zip(span, span[1:]) if (first < 0) != (second < 0))
        measured = crossings / 2.0 / 0.25
        self.assertAlmostEqual(measured, 440.0, delta=10.0)

    def test_play_source(self):
        source = dac.play_source("/music/test.mp3", output="Headset Output", volume=73, limit_s=12)
        self.assertIn("DAC_PLAY_STARTED", source)
        self.assertIn("DAC_PLAY_DONE", source)
        self.assertIn("'/music/test.mp3'", source)
        self.assertIn("'Headset Output'", source)
        self.assertIn("volume=73", source)
        self.assertIn("12000", source)


class TestDevices(unittest.TestCase):

    def test_picks_the_microphone_over_the_line_input(self):
        # One microphone hears the buzzer and the speaker, so it is the
        # default; the line input stays available with --device.
        onboard = base.CaptureDevice(0, 0, "HDA Intel", "ALC892 Analog")
        webcam = base.CaptureDevice(2, 0, "Logitech Webcam C925e", "USB Audio")
        original = base.list_capture_devices
        base.list_capture_devices = lambda: [onboard, webcam]
        try:
            self.assertIs(dac.find_default_capture_device(), webcam)
        finally:
            base.list_capture_devices = original

    def test_falls_back_to_the_onboard_input_without_a_microphone(self):
        onboard = base.CaptureDevice(0, 0, "HDA Intel", "ALC892 Analog")
        original = base.list_capture_devices
        base.list_capture_devices = lambda: [onboard]
        try:
            self.assertIs(dac.find_default_capture_device(), onboard)
        finally:
            base.list_capture_devices = original

    def test_prefers_analog_device(self):
        digital = base.CaptureDevice(0, 1, "HDA Intel", "ALC892 Digital")
        analog = base.CaptureDevice(0, 0, "HDA Intel", "ALC892 Analog")
        original = base.list_capture_devices
        base.list_capture_devices = lambda: [digital, analog]
        try:
            self.assertIs(dac.find_default_capture_device(), analog)
        finally:
            base.list_capture_devices = original

    def test_explicit_spec_is_forwarded(self):
        expected = base.CaptureDevice(3, 0, "USB Audio Device", "USB Audio")
        original = base.find_capture_device
        seen = []

        def fake(spec=None):
            seen.append(spec)
            return expected

        base.find_capture_device = fake
        try:
            self.assertIs(dac.find_default_capture_device("3"), expected)
        finally:
            base.find_capture_device = original
        self.assertEqual(seen, ["3"])

    def test_capture_gain_is_set_and_restored(self):
        commands = []
        original_run = dac.subprocess.run
        original_value = dac._amixer_capture_value
        dac.subprocess.run = lambda command, **kwargs: commands.append(command)
        dac._amixer_capture_value = lambda card: "28,28"
        try:
            restore = dac.set_capture_gain(base.CaptureDevice(0, 0, "HDA Intel", "ALC892 Analog"), 20)
            restore()
        finally:
            dac.subprocess.run = original_run
            dac._amixer_capture_value = original_value
        self.assertIn(["amixer", "-c", "0", "sset", "Capture", "20"], commands)
        self.assertIn(["amixer", "-c", "0", "cset", "name=Capture Volume", "28,28"], commands)

    def test_capture_gain_none_is_a_noop(self):
        original_run = dac.subprocess.run
        commands = []
        dac.subprocess.run = lambda command, **kwargs: commands.append(command)
        try:
            dac.set_capture_gain(base.CaptureDevice(0, 0, "HDA Intel", "ALC892 Analog"), None)()
        finally:
            dac.subprocess.run = original_run
        self.assertEqual(commands, [])


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestMeasurement(unittest.TestCase):

    def capture(self, notes=("a4", "a5"), **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tones.wav")
            render_tones(path, notes=notes, **kwargs)
            samples, rate = base.read_wav(path)
        return samples, rate

    def test_tones_match_expected_notes(self):
        samples, rate = self.capture()
        measured = dac.analyze_recording(samples, rate, ["a4", "a5"])
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(len(measured["segments"]), 2)
        for entry in measured["segments"]:
            self.assertLessEqual(abs(entry["error_pct"]), 1.0, entry)
            self.assertGreater(entry["snr_db"], 30.0, entry)

    def test_file_mode_reports_peaks_without_notes(self):
        samples, rate = self.capture(notes=("a4",))
        measured = dac.analyze_recording(samples, rate, None)
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(len(measured["segments"]), 1)
        self.assertAlmostEqual(measured["segments"][0]["peak_hz"], 440.0, delta=10.0)

    def test_silence_fails(self):
        samples = np.zeros(44100 * 2)
        measured = dac.analyze_recording(samples, 44100, None)
        self.assertFalse(measured["ok"])
        self.assertIn("segments", measured["failures"])


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestVerifyOrchestration(unittest.TestCase):

    class Controller:
        def __init__(self):
            self.calls = []

        def exec(self, code, timeout=30):
            self.calls.append(code)
            if "DAC_WAV_OK" in code:
                return b"DAC_WAV_OK 12345"
            if "DAC_PLAY_STARTED" in code:
                return b"DAC_PLAY_STARTED Headset Output\r\nDAC_PLAY_DONE 3900"
            return b""

    def signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tones.wav")
            render_tones(path, notes=("a4", "a5"))
            return base.read_wav(path)

    def run_verify(self, **kwargs):
        controller = self.Controller()
        signal, rate = self.signal()
        original = (base.start_recording, base.stop_recording, base.wait_for_recording,
                    dac.find_default_capture_device, dac.set_capture_gain)
        try:
            base.start_recording = lambda device, path, rate, channels=None: path
            base.stop_recording = lambda process, path=None: base.write_wav(path, signal, rate)
            base.wait_for_recording = lambda process, path, timeout=8.0: True
            dac.find_default_capture_device = lambda spec=None: base.CaptureDevice(
                0, 0, "HDA Intel", "ALC892 Analog")
            dac.set_capture_gain = lambda device, value: (lambda: None)
            with tempfile.TemporaryDirectory() as tmp:
                measured = dac.verify(controller=controller, out_dir=tmp,
                                      settle=0, pre_roll=0, tail=0, **kwargs)
                measured["_out_dir"] = tmp
                self.assertTrue(os.path.isfile(measured["artifacts"]["metrics_json"]))
        finally:
            (base.start_recording, base.stop_recording, base.wait_for_recording,
             dac.find_onboard_capture_device, dac.set_capture_gain) = original
        return controller, measured

    def test_tones_mode(self):
        controller, measured = self.run_verify(notes="a4,a5")
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(measured["mode"], "tones")
        self.assertEqual(measured["output"], dac.DEFAULT_OUTPUT)
        self.assertTrue(any("DAC_WAV_OK" in call for call in controller.calls))
        play = next(index for index, call in enumerate(controller.calls) if "DAC_PLAY_STARTED" in call)
        remove = next(index for index, call in enumerate(controller.calls) if "os.remove" in call)
        self.assertGreater(remove, play)

    def test_file_mode_skips_generation(self):
        controller, measured = self.run_verify(notes=None, file="/music/test.mp3")
        self.assertTrue(measured["ok"], measured.get("failures"))
        self.assertEqual(measured["mode"], "file")
        self.assertEqual(measured["file"], "/music/test.mp3")
        self.assertFalse(any("DAC_WAV_OK" in call for call in controller.calls))
        self.assertFalse(any("os.remove" in call for call in controller.calls))

    def test_missing_output_fails(self):
        controller = self.Controller()

        def exec_missing(code, timeout=30):
            controller.calls.append(code)
            if "DAC_WAV_OK" in code:
                return b"DAC_WAV_OK 1"
            return b"DAC_OUTPUT_MISSING"

        controller.exec = exec_missing
        signal, rate = self.signal()
        original = (base.start_recording, base.stop_recording, base.wait_for_recording,
                    dac.find_default_capture_device, dac.set_capture_gain)
        try:
            base.start_recording = lambda device, path, rate, channels=None: path
            base.stop_recording = lambda process, path=None: base.write_wav(path, signal, rate)
            base.wait_for_recording = lambda process, path, timeout=8.0: True
            dac.find_default_capture_device = lambda spec=None: base.CaptureDevice(
                0, 0, "HDA Intel", "ALC892 Analog")
            dac.set_capture_gain = lambda device, value: (lambda: None)
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(dac.AcousticError):
                dac.verify(controller=controller, notes="a4", out_dir=tmp,
                           settle=0, pre_roll=0, tail=0)
        finally:
            (base.start_recording, base.stop_recording, base.wait_for_recording,
             dac.find_onboard_capture_device, dac.set_capture_gain) = original


if __name__ == "__main__":
    unittest.main()
