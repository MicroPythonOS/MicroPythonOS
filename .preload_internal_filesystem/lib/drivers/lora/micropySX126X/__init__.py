"""Package aliasing to satisfy micropySX126X absolute imports."""

import sys

from . import _sx126x as _sx126x_mod

sys.modules.setdefault("_sx126x", _sx126x_mod)

from . import sx126x as _sx126x_base

sys.modules.setdefault("sx126x", _sx126x_base)

