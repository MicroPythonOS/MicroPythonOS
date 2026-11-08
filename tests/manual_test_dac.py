#!/usr/bin/env python3
"""Manual acoustic test of the badge DAC output (host side, real hardware).

Plays a known tone sequence through the badge headphone/DAC jack and confirms
from a capture-device recording that every note is present at the right
frequency. The rig is manual: the badge jack must be wired into a capture input
(on zbox1, the on-board ALC892 microphone jack).

    python3 tests/manual_test_dac.py
    python3 tests/manual_test_dac.py --capture-gain 20
    python3 tests/manual_test_dac.py --notes a4,a5,a6 --relayport /dev/ttyUSB0
    python3 tests/manual_test_dac.py --file /music/test.mp3 --notes a4,a5,a6
    python3 tests/manual_test_dac.py --file /music/test.mp3 --json

The implementation lives in scripts/mpos_dac_acoustic.py; this file is the
manual entry point and prints a compact summary.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scripts import mpos_dac_acoustic as dac  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Manual acoustic test of the badge DAC output")
    parser.add_argument("--port", default=dac.DEFAULT_PORT,
                        help="badge serial port (default %s)" % dac.DEFAULT_PORT)
    parser.add_argument("--relayport", default=dac.DEFAULT_RELAY,
                        help="USB relay port, power-cycles the badge first (e.g. /dev/ttyUSB0)")
    parser.add_argument("--device", default=dac.DEFAULT_DEVICE,
                        help="capture device: plughw:CARD,DEV, a card number or an alsa_input.* source")
    parser.add_argument("--notes", default=None,
                        help="comma-separated notes to play and expect (default %s)" % dac.DEFAULT_NOTES)
    parser.add_argument("--file", default=None,
                        help="play this file on the badge instead of generating tones")
    parser.add_argument("--output", default=dac.DEFAULT_OUTPUT,
                        help="AudioManager output name (default %s)" % dac.DEFAULT_OUTPUT)
    parser.add_argument("--volume", type=int, default=dac.DEFAULT_VOLUME)
    parser.add_argument("--capture-gain", type=int, default=None,
                        help="set ALSA 'Capture' to this value for the run, then restore it")
    parser.add_argument("--out-dir", default=dac.DEFAULT_OUT_DIR)
    parser.add_argument("--settle", type=float, default=1.5)
    parser.add_argument("--min-snr-db", type=float, default=dac.DEFAULT_THRESHOLDS["min_snr_db"])
    parser.add_argument("--max-freq-error", type=float, default=dac.DEFAULT_THRESHOLDS["max_freq_error_pct"])
    parser.add_argument("--min-duration", type=float, default=dac.DEFAULT_THRESHOLDS["min_duration_s"])
    parser.add_argument("--json", action="store_true", help="print the full metrics JSON only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    thresholds = {
        "min_snr_db": args.min_snr_db,
        "max_freq_error_pct": args.max_freq_error,
        "min_duration_s": args.min_duration,
    }
    notes = args.notes
    if notes is None and args.file is None:
        notes = dac.DEFAULT_NOTES
    try:
        measured = dac.verify(
            port=args.port,
            device=args.device,
            notes=notes,
            file=args.file,
            output=args.output,
            volume=args.volume,
            out_dir=args.out_dir,
            label="manual-dac",
            thresholds=thresholds,
            relayport=args.relayport,
            capture_gain=args.capture_gain,
            settle=args.settle,
        )
    except dac.AcousticError as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(measured, indent=1))
    else:
        capture = measured.get("capture_device") or {}
        print("badge: %s  output: %s  mic: %s" % (
            args.port, measured.get("output", "?"), capture.get("description", "?")))
        print("noise floor: %.1f dBFS  mode: %s" % (
            measured["noise_floor_dbfs"], measured.get("mode", "?")))
        for entry in measured["segments"]:
            if "expected_hz" in entry:
                print("  %-4s %5.2f-%.2fs  snr %5.1f dB  peak %7.1f Hz = %7.1f Hz (want %7.1f Hz)  %s"
                      % (entry.get("note", "?"), entry["start_s"], entry["end_s"], entry["snr_db"],
                         entry["peak_hz"], entry["f0_hz"], entry["expected_hz"],
                         "ok" if entry["ok"] else "FAIL"))
            else:
                print("  seg%d %5.2f-%.2fs  snr %5.1f dB  peak %7.1f Hz  %s"
                      % (entry["index"], entry["start_s"], entry["end_s"], entry["snr_db"],
                         entry["peak_hz"], "ok" if entry["ok"] else "FAIL"))
        print("wav: %s" % measured.get("wav"))
        if measured.get("ok"):
            print("PASS")
        else:
            print("FAIL: %s" % measured.get("failures"))
    return 0 if measured.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
