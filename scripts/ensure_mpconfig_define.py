"""Insert a `#define <NAME> (1)` into a MicroPython mpconfigport.h.

Usage: ensure_mpconfig_define.py <mpconfigport.h> <DEFINE_NAME>

Adds the define right after the `#include "mpconfigvariant.h"` line, guarded
by an #ifndef so it doesn't clash with an existing definition. No-op if the
include isn't present or the name already appears in the file.
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
