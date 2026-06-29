#!/usr/bin/env python3
"""Insert a `#define <name> (1)` guard into a MicroPython mpconfigport.h.

Used by build_mpos.sh to enable build-time options (e.g. MICROPY_PY_WEBREPL,
MICROPY_PY_OS_DUPTERM) for the unix/macOS ports. The define is inserted right
after the `#include "mpconfigvariant.h"` line, and only if not already present.

Usage: ensure_mpconfig_define.py <mpconfigport.h path> <DEFINE_NAME>
"""
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
name = sys.argv[2]
text = path.read_text()
needle = '#include "mpconfigvariant.h"'
insert = f"\n\n#ifndef {name}\n#define {name} (1)\n#endif\n"
if needle in text and name not in text:
    path.write_text(text.replace(needle, needle + insert))
