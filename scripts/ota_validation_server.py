#!/usr/bin/env python3
"""Serve local osupdate metadata for OTA release validation.

The live updates server only offers the newest release. To re-validate an older
upgrade path (for example 0.20.0 -> 0.21.0 after 0.21.1 is already live), point
the device at this throwaway server with
``validate_ota_release.py --mirror-url``.

Examples::

    python3 scripts/ota_validation_server.py \\
        --version 0.21.0 \\
        --ota-url https://updates.micropythonos.com/releases/esp32s3/MicroPythonOS_esp32s3_0.21.0.ota \\
        --hardware-id fri3d_2026 \\
        --port 8765

    # then, on the host running the gate:
    python3 scripts/validate_ota_release.py ... \\
        --updates-url http://<host-lan-ip>:8765 \\
        --mirror-url http://<host-lan-ip>:8765

The server only writes ``osupdate_<hardware-id>.json`` files into a temporary
directory and never proxies the OTA download itself.
"""

import argparse
import json
import os
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def build_metadata(version, ota_url, changelog):
    if not ota_url.endswith(".ota"):
        raise SystemExit("--ota-url must point at a .ota file")
    return {
        "version": version,
        "download_url": ota_url,
        "changelog": changelog,
    }


def write_metadata(directory, hardware_ids, metadata):
    paths = []
    for hardware_id in hardware_ids:
        path = os.path.join(directory, "osupdate_{}.json".format(hardware_id))
        with open(path, "w") as handle:
            json.dump(metadata, handle, indent=1)
        paths.append(path)
    return paths


def parse_hardware_ids(values):
    hardware_ids = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item and item not in hardware_ids:
                hardware_ids.append(item)
    if not hardware_ids:
        raise SystemExit("at least one --hardware-id is required")
    return hardware_ids


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve local osupdate metadata for OTA validation")
    parser.add_argument("--version", required=True, help="release version to advertise")
    parser.add_argument("--ota-url", required=True, help="download URL of the .ota image")
    parser.add_argument("--hardware-id", action="append", default=[],
                        help="hardware_id to serve (repeatable or comma-separated)")
    parser.add_argument("--changelog", default="Release validation build.",
                        help="changelog text shown by OSUpdate")
    parser.add_argument("--changelog-file", default=None,
                        help="read the changelog from a file instead of --changelog")
    parser.add_argument("--bind", default="0.0.0.0", help="interface to bind (default %(default)s)")
    parser.add_argument("--port", type=int, default=8765, help="port to bind (default %(default)s)")
    parser.add_argument("--public-url", default=None,
                        help="URL prefix printed for the device (default http://<bind>:<port>)")
    args = parser.parse_args(argv)

    hardware_ids = parse_hardware_ids(args.hardware_id)
    changelog = args.changelog
    if args.changelog_file:
        with open(args.changelog_file) as handle:
            changelog = handle.read()
    metadata = build_metadata(args.version, args.ota_url, changelog)

    directory = tempfile.mkdtemp(prefix="mpos_ota_validation_")
    write_metadata(directory, hardware_ids, metadata)

    handler = partial(SimpleHTTPRequestHandler, directory=directory)
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    prefix = args.public_url or "http://{}:{}".format(args.bind, args.port)
    print("Serving {} for {}".format(args.version, ", ".join(hardware_ids)))
    for hardware_id in hardware_ids:
        print("  {}/osupdate_{}.json".format(prefix.rstrip("/"), hardware_id))
    print("Pass --mirror-url {} to validate_ota_release.py".format(prefix))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
