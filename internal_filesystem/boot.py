# This file is the only one that can't be overridden (without rebuilding) for development, so keep it minimal.

# Make sure the storage partition's /lib is first in the path, so whatever is placed there overrides frozen libraries
# This allows a "prod[uction]" build to be used for development as well, just by overriding the libraries in /lib
import sys
sys.path.insert(0, '/lib')

print("Passing execution over to MicroPythonOS's main.py")
import mpos.main

