#!/usr/bin/env python3
"""Manual acoustic test of the badge buzzer (host side, real hardware).

Play a known note sequence on the badge and confirm from a USB microphone
recording that every note is present at the right frequency. Run this on the
machine the USB sound card and the badge are attached to (zbox1), not inside
the device test suite: the recording happens on the host.

    python3 tests/manual_test_buzzer.py
    python3 tests/manual_test_buzzer.py --notes a4,a5,a6,a7 --volume 100
    python3 tests/manual_test_buzzer.py --port /dev/ttyACM0 --relayport /dev/ttyUSB0

The implementation lives in scripts/mpos_buzzer_acoustic.py; this file is the
manual entry point and prints a compact summary.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scripts import mpos_buzzer_acoustic as buzzer  # noqa: E402


def default_relay():
    configured = os.environ.get("MPOS_BUZZER_RELAY")
    if configured:
        return configured
    return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Manual acoustic test of the badge buzzer")
    parser.add_argument("--port", default=buzzer.DEFAULT_PORT,
                        help="badge serial port (default %s)" % buzzer.DEFAULT_PORT)
    parser.add_argument("--relayport", default=default_relay(),
                        help="USB relay port, power-cycles the badge first (e.g. /dev/ttyUSB0)")
    parser.add_argument("--device", default=buzzer.DEFAULT_DEVICE,
                        help="capture device: plughw:CARD,DEV, a card number or an alsa_input.* source")
    parser.add_argument("--notes", default=buzzer.DEFAULT_NOTES,
                        help="comma-separated notes (default %s)" % buzzer.DEFAULT_NOTES)
    parser.add_argument("--volume", type=int, default=buzzer.DEFAULT_VOLUME)
    parser.add_argument("--out-dir", default=buzzer.DEFAULT_OUT_DIR)
    parser.add_argument("--settle", type=float, default=1.5)
    parser.add_argument("--min-snr-db", type=float, default=buzzer.DEFAULT_THRESHOLDS["min_snr_db"])
    parser.add_argument("--max-freq-error", type=float, default=buzzer.DEFAULT_THRESHOLDS["max_freq_error_pct"])
    parser.add_argument("--min-duration", type=float, default=buzzer.DEFAULT_THRESHOLDS["min_duration_s"])
    parser.add_argument("--json", action="store_true", help="print the full metrics JSON only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    thresholds = {
        "min_snr_db": args.min_snr_db,
        "max_freq_error_pct": args.max_freq_error,
        "min_duration_s": args.min_duration,
    }
    try:
        measured = buzzer.verify(
            port=args.port,
            device=args.device,
            notes=args.notes,
            volume=args.volume,
            out_dir=args.out_dir,
            label="manual",
            thresholds=thresholds,
            relayport=args.relayport,
            settle=args.settle,
        )
    except buzzer.BuzzerError as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        import json
        print(json.dumps(measured, indent=1))
    else:
        capture = measured.get("capture_device") or {}
        print("badge: %s  mic: %s" % (args.port, capture.get("description", "?")))
        print("noise floor: %.1f dBFS  rtttl: %s" % (measured["noise_floor_dbfs"], measured["rtttl"]))
        for entry in measured["segments"]:
            print("  %-4s %5.2f-%.2fs  snr %5.1f dB  peak %7.1f Hz /%d = %7.1f Hz (want %7.1f Hz)  %s"
                  % (entry.get("note", "?"), entry["start_s"], entry["end_s"], entry["snr_db"],
                     entry["peak_hz"], entry["harmonic"], entry["f0_hz"], entry.get("expected_hz", 0.0),
                     "ok" if entry["ok"] else "FAIL"))
        print("wav: %s" % measured.get("wav"))
        if measured.get("ok"):
            print("PASS")
        else:
            print("FAIL: %s" % measured.get("failures"))
    return 0 if measured.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
