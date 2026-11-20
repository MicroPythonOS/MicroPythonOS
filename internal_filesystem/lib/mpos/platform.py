"""The host's platform keys for native app files.

An app's ``MANIFEST.JSON`` can carry a ``"native"`` map: platform key to the
files that platform installs. There are two kinds of key because the two kinds
of engine need different things:

* ``soc()`` names the chip (``esp32s3``, ``esp32p4``, ``esp32``). A chip selects
  a flash-resident core (``<soc>.xip``), which is linked for that chip's
  instruction and data windows, so the key has to be the SoC.
* ``natmod_arch()`` names the ``.mpy`` native module architecture
  (``xtensawin``, ``x64``). A module only has to match the bytecode ABI, and the
  same ``xtensawin`` build serves classic ESP32 and the S3.

The installer and the apps both read these, so the ``sys.implementation``
probing lives here once instead of in each of them.
"""

import sys

# natmod architectures from MicroPython's py/persistentcode.h.
_NATMOD_NAMES = {
    1: "x86",
    2: "x64",
    3: "armv6",
    4: "armv6m",
    5: "armv7m",
    6: "armv7em",
    7: "armv7emsp",
    8: "armv7emdp",
    9: "xtensa",
    10: "xtensawin",
    11: "rv32imc",
    12: "rv64imc",
}

# Longest first: "esp32s3" contains "esp32".
_SOC_NAMES = (
    ("ESP32S3", "esp32s3"),
    ("ESP32-P4", "esp32p4"),
    ("ESP32P4", "esp32p4"),
    ("ESP32C6", "esp32c6"),
    ("ESP32C3", "esp32c3"),
    ("ESP32S2", "esp32s2"),
    ("ESP32", "esp32"),
)


def soc():
    """The chip's key (``esp32s3``, ...), or None off a badge.

    ``sys.platform`` is ``esp32`` for every Espressif chip, so the variant comes
    from ``sys.implementation._machine`` (MicroPython's banner string).
    """
    if sys.platform != "esp32":
        return None
    name = getattr(sys.implementation, "_machine", "").upper()
    for marker, key in _SOC_NAMES:
        if marker in name:
            return key
    return None


def natmod_arch():
    """The native-module architecture key (``x64``, ``xtensawin``), or None.

    ``sys.implementation._mpy`` is the .mpy header integer: bits 8.. hold the
    feature byte (sub-version in bits 0-1, architecture in bits 2-7).
    """
    mpy = getattr(sys.implementation, "_mpy", None)
    if mpy is None:
        return None
    return _NATMOD_NAMES.get((mpy >> 10) & 0x2F)


def native_keys():
    """The keys this host installs from a manifest's ``"native"`` map."""
    keys = []
    chip = soc()
    if chip is not None:
        keys.append(chip)
    arch = natmod_arch()
    if arch is not None and arch not in keys:
        keys.append(arch)
    return keys
