// Derived from standard variant. Adds sys.settrace for Python-level coverage.
#define MICROPY_CONFIG_ROM_LEVEL (MICROPY_CONFIG_ROM_LEVEL_EXTRA_FEATURES)

#include "../mpconfigvariant_common.h"

#define MICROPY_PY_SYS_SETTRACE (1)
