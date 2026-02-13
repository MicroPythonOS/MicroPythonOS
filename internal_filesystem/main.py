# This file is the only one that can't be overridden for development (without rebuilding) because it's not in lib/, so keep it minimal.

# Make sure the storage partition's lib/ is first in the path, so whatever is placed there overrides frozen libraries.
# This allows any build to be used for development as well, just by overriding the libraries in lib/
import sys
sys.path.insert(0, 'lib')

print(f"Minimal main.py importing mpos.main with sys.path: {sys.path}")
import mpos.main
