# This file is the only one that can't be overridden for development (without rebuilding) because it's not in lib/, so keep it minimal.

# Make sure the storage partition's lib/ is first in the path, so whatever is placed there overrides frozen libraries.
# This allows any build to be used for development as well, just by overriding the libraries in lib/

# Copy this file to / on the device's internal storage to have it run automatically instead of relying on the frozen-in files.
import gc
import sys

sys.path.insert(0, "lib")

# Web build: native machine.Timer is unavailable (machine_timer.c is
# removed). The native `machine` module dict is read-only, so install an
# asyncio-backed Timer by replacing sys.modules["machine"] with a thin
# wrapper that delegates every other attribute to the native module.
try:
    import machine as _native_machine
    if not hasattr(_native_machine, "Timer"):
        import sys as _sys
        import _web_machine_timer
        import _web_machine_pin
        import _web_machine_hw
        class _MachineWrapper:
            Timer = _web_machine_timer.Timer
            if not hasattr(_native_machine, "Pin"):
                Pin = _web_machine_pin.Pin
            def __getattr__(self, name):
                try:
                    return getattr(_native_machine, name)
                except AttributeError:
                    return getattr(_web_machine_hw, name)
        _sys.modules["machine"] = _MachineWrapper()
except Exception as _e:
    print("could not install web machine.Timer:", _e)

print(f"{sys.version=}")
print(f"{sys.implementation=}")

# Ensure os.path is available before starting apps.
# internal_filesystem/lib/os/__init__.py provides a pure-Python os package
# (from micropython-lib) that wraps uos and exposes os.path.
import os
sys.modules["uos"] = os

print("Free space on root filesystem:")
stat = os.statvfs("/")
total_space = stat[0] * stat[2]
free_space = stat[0] * stat[3]
used_space = total_space - free_space
print(f"{total_space=} / {used_space=} / {free_space=} bytes")


gc.collect()
print(
    f"RAM: {gc.mem_free()} free, {gc.mem_alloc()} allocated, {gc.mem_alloc() + gc.mem_free()} total"
)

print("Passing execution over to mpos.main")
try:
    import mpos.main  # noqa: F401
except Exception as e:
    print("Error importing mpos.main, sleeping 5 seconds before printing the exception...")
    import time
    time.sleep(5) # sleep so the user has time to connect to serial console
    sys.print_exception(e) # print it after the sleep so user can see it on serial console
    print("MicroPythonOS exiting.")
