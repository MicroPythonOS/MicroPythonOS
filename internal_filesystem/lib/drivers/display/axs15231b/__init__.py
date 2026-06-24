import sys
from . import axs15231b
from . import _axs15231b_init

sys.modules["_axs15231b_init"] = _axs15231b_init

__all__ = [
    "AXS15231B",
]

AXS15231B = axs15231b.AXS15231B
