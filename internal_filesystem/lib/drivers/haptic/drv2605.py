# SPDX-FileCopyrightText: 2017 Tony DiCola for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_drv2605`
====================================================

MicroPython module for the DRV2605 haptic feedback motor driver.

This library was ported from the Adafruit CircuitPython version. Huge thanks to them for making their libs public and open.

* Original Author(s): Tony DiCola

* May 3rd, 2025 - Ported to MicroPython by Unexpected Maker for use on SQUiXL
https://quixl.io

"""

from micropython import const

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/unexpectedmaker/MicroPython_DRV2605.git"

# Internal constants:
_DRV2605_ADDR       = const(0x5A)
_DRV2605_REG_STATUS = const(0x00)
_DRV2605_REG_MODE   = const(0x01)
_DRV2605_REG_RTPIN  = const(0x02)
_DRV2605_REG_LIBRARY= const(0x03)
_DRV2605_REG_WAVESEQ1 = const(0x04)
_DRV2605_REG_WAVESEQ2 = const(0x05)
_DRV2605_REG_WAVESEQ3 = const(0x06)
_DRV2605_REG_WAVESEQ4 = const(0x07)
_DRV2605_REG_WAVESEQ5 = const(0x08)
_DRV2605_REG_WAVESEQ6 = const(0x09)
_DRV2605_REG_WAVESEQ7 = const(0x0A)
_DRV2605_REG_WAVESEQ8 = const(0x0B)
_DRV2605_REG_GO     = const(0x0C)
_DRV2605_REG_OVERDRIVE = const(0x0D)
_DRV2605_REG_SUSTAINPOS = const(0x0E)
_DRV2605_REG_SUSTAINNEG = const(0x0F)
_DRV2605_REG_BREAK  = const(0x10)
_DRV2605_REG_AUDIOCTRL = const(0x11)
_DRV2605_REG_AUDIOLVL  = const(0x12)
_DRV2605_REG_AUDIOMAX  = const(0x13)
_DRV2605_REG_RATEDV   = const(0x16)
_DRV2605_REG_CLAMPV   = const(0x17)
_DRV2605_REG_AUTOCALCOMP = const(0x18)
_DRV2605_REG_AUTOCALEMP  = const(0x19)
_DRV2605_REG_FEEDBACK = const(0x1A)
_DRV2605_REG_CONTROL1 = const(0x1B)
_DRV2605_REG_CONTROL2 = const(0x1C)
_DRV2605_REG_CONTROL3 = const(0x1D)
_DRV2605_REG_CONTROL4 = const(0x1E)
_DRV2605_REG_VBAT     = const(0x21)
_DRV2605_REG_LRARESON = const(0x22)

# User-facing mode constants:
MODE_INTTRIG     = const(0x00)
MODE_EXTTRIGEDGE = const(0x01)
MODE_EXTTRIGLVL  = const(0x02)
MODE_PWMANALOG   = const(0x03)
MODE_AUDIOVIBE   = const(0x04)
MODE_REALTIME    = const(0x05)
MODE_DIAGNOS     = const(0x06)
MODE_AUTOCAL     = const(0x07)

LIBRARY_EMPTY    = const(0x00)
LIBRARY_TS2200A  = const(0x01)
LIBRARY_TS2200B  = const(0x02)
LIBRARY_TS2200C  = const(0x03)
LIBRARY_TS2200D  = const(0x04)
LIBRARY_TS2200E  = const(0x05)
LIBRARY_LRA      = const(0x06)


class DRV2605:
    """TI DRV2605 haptic feedback motor driver."""

    def __init__(self, i2c, address = _DRV2605_ADDR):
        self._i2c = i2c
        self._addr = address
        # Verify device ID
        status = self._read_u8(_DRV2605_REG_STATUS)
        device_id = (status >> 5) & 0x07
        if device_id not in (3, 7):
            raise RuntimeError("Failed to find DRV2605, check wiring!")
        # Initialize registers
        self._write_u8(_DRV2605_REG_MODE, 0x00)
        self._write_u8(_DRV2605_REG_RTPIN, 0x00)
        self._write_u8(_DRV2605_REG_WAVESEQ1, 1)
        self._write_u8(_DRV2605_REG_WAVESEQ2, 0)
        self._write_u8(_DRV2605_REG_OVERDRIVE, 0)
        self._write_u8(_DRV2605_REG_SUSTAINPOS, 0)
        self._write_u8(_DRV2605_REG_SUSTAINNEG, 0)
        self._write_u8(_DRV2605_REG_BREAK, 0)
        self._write_u8(_DRV2605_REG_AUDIOMAX, 0x64)
        # ERM open-loop
        self.use_ERM()
        control3 = self._read_u8(_DRV2605_REG_CONTROL3)
        self._write_u8(_DRV2605_REG_CONTROL3, control3 | 0x20)
        # Default settings
        self.mode = MODE_INTTRIG
        self.library = LIBRARY_TS2200A
        self._sequence = _DRV2605_Sequence(self)

    def _read_u8(self, register: int) -> int:
        """Read a single byte from a register."""
        return self._i2c.readfrom_mem(self._addr, register, 1)[0]

    def _write_u8(self, register: int, value: int) -> None:
        """Write a single byte to a register."""
        self._i2c.writeto_mem(self._addr, register, bytes((value & 0xFF,)))

    def play(self) -> None:
        """Play the currently configured waveform sequence."""
        self._write_u8(_DRV2605_REG_GO, 1)

    def stop(self) -> None:
        """Stop any playback."""
        self._write_u8(_DRV2605_REG_GO, 0)

    @property
    def mode(self) -> int:
        """Get or set the trigger mode (0-7)."""
        return self._read_u8(_DRV2605_REG_MODE)

    @mode.setter
    def mode(self, val: int) -> None:
        if not 0 <= val <= 7:
            raise ValueError("Mode must be 0-7!")
        self._write_u8(_DRV2605_REG_MODE, val)

    @property
    def library(self) -> int:
        """Get or set the waveform library (0-6)."""
        return self._read_u8(_DRV2605_REG_LIBRARY) & 0x07

    @library.setter
    def library(self, val: int) -> None:
        if not 0 <= val <= 6:
            raise ValueError("Library must be 0-6!")
        self._write_u8(_DRV2605_REG_LIBRARY, val)

    @property
    def sequence(self) -> "_DRV2605_Sequence":
        """Get the waveform sequence helper (slots 0-7)."""
        return self._sequence

    @property
    def realtime_value(self) -> int:
        """Get or set the real-time playback value (-127-255)."""
        return self._read_u8(_DRV2605_REG_RTPIN)

    @realtime_value.setter
    def realtime_value(self, val: int) -> None:
        if not -127 <= val <= 255:
            raise ValueError("Real-time value must be between -127 and 255!")
        self._write_u8(_DRV2605_REG_RTPIN, val)

    def set_waveform(self, effect_id: int, slot: int = 0) -> None:
        """Set a single effect ID into sequence slot 0-7."""
        if not 0 <= effect_id <= 123:
            raise ValueError("Effect ID must be 0-123!")
        if not 0 <= slot <= 7:
            raise ValueError("Slot must be 0-7!")
        self._write_u8(_DRV2605_REG_WAVESEQ1 + slot, effect_id)

    def use_ERM(self) -> None:
        """Configure for an eccentric rotating mass motor."""
        fb = self._read_u8(_DRV2605_REG_FEEDBACK)
        self._write_u8(_DRV2605_REG_FEEDBACK, fb & 0x7F)

    def use_LRM(self) -> None:
        """Configure for a linear resonance actuator."""
        fb = self._read_u8(_DRV2605_REG_FEEDBACK)
        self._write_u8(_DRV2605_REG_FEEDBACK, fb | 0x80)


class Effect:
    """DRV2605 waveform effect (0-123)."""

    def __init__(self, effect_id: int) -> None:
        self.id = effect_id  # setter will validate

    @property
    def raw_value(self) -> int:
        return self._effect_id

    @property
    def id(self) -> int:
        return self._effect_id

    @id.setter
    def id(self, effect_id: int) -> None:
        if not 0 <= effect_id <= 123:
            raise ValueError("Effect ID must be 0-123!")
        self._effect_id = effect_id

    def __repr__(self) -> str:
        return "{}({})".format(type(self).__qualname__, self.id)


class Pause:
    """DRV2605 sequence pause (0.00-1.27 s)."""

    def __init__(self, duration: float) -> None:
        self.duration = duration  # setter will validate

    @property
    def raw_value(self) -> int:
        return self._duration

    @property
    def duration(self) -> float:
        return (self._duration & 0x7F) / 100.0

    @duration.setter
    def duration(self, duration: float) -> None:
        if not 0.0 <= duration <= 1.27:
            raise ValueError("Pause duration must be 0.0-1.27 s!")
        self._duration = 0x80 | round(duration * 100.0)

    def __repr__(self) -> str:
        return "{}({:.2f})".format(type(self).__qualname__, self.duration)


class _DRV2605_Sequence:
    """Helper to index the 8 waveform slots."""

    def __init__(self, drv: DRV2605) -> None:
        self._drv = drv

    def __setitem__(self, slot: int, effect) -> None:
        if not 0 <= slot <= 7:
            raise IndexError("Slot must be 0-7!")
        if not isinstance(effect, (Effect, Pause)):
            raise TypeError("Must be Effect or Pause!")
        self._drv._write_u8(_DRV2605_REG_WAVESEQ1 + slot, effect.raw_value)

    def __getitem__(self, slot: int):
        if not 0 <= slot <= 7:
            raise IndexError("Slot must be 0-7!")
        val = self._drv._read_u8(_DRV2605_REG_WAVESEQ1 + slot)
        if val & 0x80:
            # pause
            return Pause((val & 0x7F) / 100.0)
        else:
            return Effect(val)

    def __iter__(self):
        for i in range(8):
            yield self[i]

    def __repr__(self):
        return repr(list(self))