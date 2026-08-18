# This file is the only one that can't be overridden for development (without rebuilding) because it's not in lib/, so keep it minimal.

# Make sure the storage partition's lib/ is first in the path, so whatever is placed there overrides frozen libraries.
# This allows any build to be used for development as well, just by overriding the libraries in lib/

# Copy this file to / on the device's internal storage to have it run automatically instead of relying on the frozen-in files.
import sys


def _lib_override_is_safe():
    """Refuse a lib/ override whose mpos is from a different release.

    The web-installer image ships a full lib/ on the data partition, and OTA
    updates only replace the firmware partition — so after the first update
    that changes a framework API, the stale lib/mpos shadows the new frozen
    modules and the OS crashes at boot (e.g. the 0.16.1+ launcher reading
    app.categories against a 0.16.0 App class: 'App' object has no attribute
    'categories'). Compare release strings and skip lib/ on mismatch so the
    device boots the self-consistent frozen tree instead.

    The frozen release is obtained by importing mpos.build_info BEFORE lib/
    is on sys.path; the import is then purged from sys.modules so a valid
    lib/ override can still shadow mpos normally afterwards. The lib/ side
    is read as plain text (no import) to keep stale code off the path.
    """
    try:
        with open("lib/mpos/build_info.py") as f:
            lib_src = f.read()
    except OSError:
        return True  # no lib/mpos on flash -> nothing can skew
    try:
        from mpos.build_info import BuildInfo
        frozen_release = BuildInfo.version.release
        for name in list(sys.modules):
            if name == "mpos" or name.startswith("mpos."):
                del sys.modules[name]
    except Exception:
        return True  # no frozen mpos (bare interpreter): lib/ is all we have
    if ('release = "%s"' % frozen_release) in lib_src:
        return True
    print("WARNING: lib/ on the data partition is from a different release "
          "than this firmware (frozen release: %s). Skipping the lib/ "
          "override so the OS can boot; delete or update /lib to silence "
          "this warning." % frozen_release)
    return False


if _lib_override_is_safe():
    sys.path.insert(0, "lib")

print(f"{sys.version=}")
print(f"{sys.implementation=}")

# Ensure os.path is available before starting apps.
# internal_filesystem/lib/os/__init__.py provides a pure-Python os package
# (from micropython-lib) that wraps uos and exposes os.path.
import os
sys.modules["uos"] = os

# These info prints don't seem to slow down the boot measurably so let's leave them in, for now:
print("Free space on internal filesystem:")
stat = os.statvfs("/")
total_space = stat[0] * stat[2]
free_space = stat[0] * stat[3]
used_space = total_space - free_space
print(f"{total_space=} / {used_space=} / {free_space=} bytes")

import gc
gc.collect()
print(f"RAM: {gc.mem_free()} free, {gc.mem_alloc()} allocated, {gc.mem_alloc() + gc.mem_free()} total")

print("Passing execution over to mpos.main")
try:
    import mpos.main  # noqa: F401
except Exception as e:
    print("Error importing mpos.main, sleeping 5 seconds before printing the exception...")
    import time
    time.sleep(5) # sleep so the user has time to connect to serial console
    sys.print_exception(e) # print it after the sleep so user can see it on serial console
    print("MicroPythonOS exiting.")
