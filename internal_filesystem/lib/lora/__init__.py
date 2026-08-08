# MicroPython lora module
# MIT license; Copyright (c) 2023 Angus Gratton

# ponytail: trimmed to sx126x only (no sx127x, stm32wl5)

from .modem import RxPacket  # noqa: F401

try:
    from .sx126x import *  # noqa: F401
except ImportError:
    raise ImportError(
        "Incomplete lora installation. Need lora-sx126x plus lora-sync."
    )
