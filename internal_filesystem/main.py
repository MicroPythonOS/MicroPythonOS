# This file is the only one that can't be overridden for development (without rebuilding) because it's not in lib/, so keep it minimal.

# Make sure the storage partition's lib/ is first in the path, so whatever is placed there overrides frozen libraries.
# This allows any build to be used for development as well, just by overriding the libraries in lib/

# Copy this file to / on the device's internal storage to have it run automatically instead of relying on the frozen-in files.
import gc
import os
import sys

sys.path.insert(0, "lib")

print(f"{sys.version=}")
print(f"{sys.implementation=}")


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
import mpos.main  # noqa: F401
