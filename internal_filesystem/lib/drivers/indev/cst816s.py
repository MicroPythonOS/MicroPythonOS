# Copyright (c) 2024 - 2025 Kevin G. Schlosser

from micropython import const  # NOQA
import pointer_framework
import time
import machine  # NOQA


I2C_ADDR = 0x15
BITS = 8

# 0x00: No gesture
# 0x01: Swipe up
# 0x02: Swipe down
# 0x03: Swipe left
# 0x04: Swipe right
# 0x05: Single click
# 0x0B: Double click
# 0x0C: Long press
_GestureID = const(0x01)

# 0: No finger
# 1: 1 finger
_FingerNum = const(0x02)

# & 0xF << 8
_XposH = const(0x03)
_XposL = const(0x04)

#  & 0xF << 8
_YposH = const(0x05)
_YposL = const(0x06)

_RegisterVersion = const(0x15)

_BPC0H = const(0xB0)
_BPC0L = const(0xB1)

_BPC1H = const(0xB2)
_BPC1L = const(0xB3)

_ChipID = const(0xA7)
_ChipIDValue = const(0xB5)
_ChipIDValue2 = const(0xB6)

_ProjID = const(0xA8)
_FwVersion = const(0xA9)


# ===============================
_MotionMask = const(0xEC)

# Enables continuous left and right sliding
_EnConLR = const(0x04)
# Enables continuous up and down sliding
_EnConUD = const(0x02)
# Enable double-click action
_EnDClick = const(0x01)
# ===============================

# Interrupt low pulse output width.
# Unit 0.1ms, optional value: 1~200. The default value is 10.
_IrqPluseWidth = const(0xED)

# Normal fast detection cycle.
# This value affects LpAutoWakeTime and AutoSleepTime.
# Unit 10ms, optional value: 1~30. The default value is 1.
_NorScanPer = const(0xEE)

# Gesture detection sliding partition angle control. Angle=tan(c)*10
# c is the angle based on the positive direction of the x-axis.
_MotionSlAngle = const(0xEF)

_LpScanRaw1H = const(0xF0)
_LpScanRaw1L = const(0xF1)
_LpScanRaw2H = const(0xF2)
_LpScanRaw2L = const(0xF3)

# Automatic recalibration period in low power consumption.
# Unit: 1 minute, optional value: 1 to 5. The default value is 5.
_LpAutoWakeTime = const(0xF4)


# Low power scan wake-up threshold. The smaller the value,
# the more sensitive it is.
# Optional values: 1 to 255. The default value is 48.
_LpScanTH = const(0xF5)

# Low power scan range. The larger the value, the more sensitive it is,
# and the higher the power consumption is.
# Optional values: 0, 1, 2, 3. The default value is 3.
_LpScanWin = const(0xF6)

# Low power scan frequency. The smaller the value, the more sensitive it is.
# Optional values: 1 to 255. The default value is 7.
_LpScanFreq = const(0xF7)

# Low power scan current. The smaller the value, the more sensitive it is.
# Optional values: 1 to 255.
_LpScanIdac = const(0xF8)


# Automatically enters low power mode when there is no touch within x seconds.
# Unit: 1S, default value: 2S.
_AutoSleepTime = const(0xF9)

# ===============================
_IrqCtl = const(0xFA)
# Interrupt pin test, automatically sends low pulses periodically after enabling
_EnTest = const(0x80)
# Sends low pulses periodically when touch is detected.
_EnTouch = const(0x40)
# Sends low pulses when touch state changes are detected.
_EnChange = const(0x20)
# Sends low pulses when gestures are detected.
_EnMotion = const(0x10)
# Long press gesture only sends one low pulse signal.
_OnceWLP = const(0x01)
# ===============================


# Automatically reset when there is touch but no valid gesture within x seconds.
# Unit: 1S. This function is not enabled when it is 0. The default value is 5.
_AutoReset = const(0xFB)

# Automatically reset after long pressing for x seconds.
# Unit: 1S. This function is not enabled when it is 0. The default value is 10.
_LongPressTime = const(0xFC)

# ===============================
_IOCtl = const(0xFD)

# The master controller realizes the soft reset function
# of the touch screen by pulling down the IRQ pin.
#   0: Disable soft reset.
#   1: Enable soft reset.
_SOFT_RST = const(0x04)

# IIC pin drive mode, the default is resistor pull-up.
#   0: Resistor pull-up
#   1: OD
_IIC_OD = const(0x02)

# IIC and IRQ pin level selection, the default is VDD level.
#   0: VDD
#   1: 1.8V
_En1v8 = const(0x01)
# ===============================

# The default value is 0, enabling automatic entry into low power mode.
# When the value is non-zero, automatic entry into low power mode is disabled.
#   0: enabled
#   1: disabled
_DisAutoSleep = const(0xFE)


class CST816S(pointer_framework.PointerDriver):

    def _read_reg(self, reg):
        self._tx_buf[0] = reg
        self._rx_buf[0] = 0x00

        self._device.write_readinto(self._tx_mv[:1], self._rx_mv[:1])

    def _write_reg(self, reg, value):
        self._tx_buf[0] = reg
        self._tx_buf[1] = value
        self._device.write(self._tx_mv[:2])

    def __init__(
        self,
        device,
        reset_pin=None,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,  # NOQA
        debug=False
    ):
        self._tx_buf = bytearray(2)
        self._tx_mv = memoryview(self._tx_buf)
        self._rx_buf = bytearray(1)
        self._rx_mv = memoryview(self._rx_buf)

        self._device = device

        if not isinstance(reset_pin, int):
            self._reset_pin = reset_pin
        else:
            self._reset_pin = machine.Pin(reset_pin, machine.Pin.OUT)

        if self._reset_pin:
            self._reset_pin.value(1)

        self.hw_reset()
        self.auto_sleep = False

        self._read_reg(_ChipID)
        print('Chip ID:', hex(self._rx_buf[0]))
        chip_id = self._rx_buf[0]

        self._read_reg(_RegisterVersion)
        print('Touch version:', self._rx_buf[0])

        self._read_reg(_ProjID)
        print('Proj ID:', hex(self._rx_buf[0]))

        self._read_reg(_FwVersion)
        print('FW Version:', hex(self._rx_buf[0]))

        if chip_id not in (_ChipIDValue, _ChipIDValue2):
            raise RuntimeError(f'Incorrect chip id ({hex(_ChipIDValue)})')

        self._write_reg(_IrqCtl, _EnTouch | _EnChange)

        super().__init__(
            touch_cal=touch_cal, startup_rotation=startup_rotation, debug=debug
        )

    @property
    def wake_up_threshold(self):
        self._read_reg(_LpScanTH)
        return 256 - self._rx_buf[0]

    @wake_up_threshold.setter
    def wake_up_threshold(self, value):
        if value < 1:
            value = 1
        elif value > 255:
            value = 255

        self._write_reg(_LpScanTH, 256 - value)

    @property
    def wake_up_scan_frequency(self):
        self._read_reg(_LpScanFreq)
        return 256 - self._rx_buf[0]

    @wake_up_scan_frequency.setter
    def wake_up_scan_frequency(self, value):
        if value < 1:
            value = 1
        elif value > 255:
            value = 255

        self._write_reg(_LpScanFreq, 256 - value)

    @property
    def auto_sleep_timeout(self):
        self._read_reg(_AutoSleepTime)
        return self._rx_buf[0]

    @auto_sleep_timeout.setter
    def auto_sleep_timeout(self, value):
        if value < 1:
            value = 1
        elif value > 255:
            value = 255

        self._write_reg(_AutoSleepTime, value)

    def wake_up(self):
        auto_sleep = self.auto_sleep

        self._write_reg(_DisAutoSleep, 0x00)
        time.sleep_ms(10)  # NOQA
        self._write_reg(_DisAutoSleep, 0xFE)
        time.sleep_ms(50)  # NOQA
        self._write_reg(_DisAutoSleep, 0xFE)
        time.sleep_ms(50)  # NOQA
        self._write_reg(_DisAutoSleep, int(not auto_sleep))

    @property
    def auto_sleep(self):
        self._read_reg(_DisAutoSleep)
        return self._rx_buf[0] == 0x00

    @auto_sleep.setter
    def auto_sleep(self, en):
        if en:
            self._write_reg(_DisAutoSleep, 0x00)
        else:
            self._write_reg(_DisAutoSleep, 0xFE)

    def hw_reset(self):
        if self._reset_pin is None:
            return

        self._reset_pin(0)
        time.sleep_ms(1)  # NOQA
        self._reset_pin(1)
        time.sleep_ms(50)  # NOQA

    def _get_coords(self):
        self._read_reg(_FingerNum)
        if self._rx_buf[0] == 0:
            return None

        self._read_reg(_XposH)
        x = (self._rx_buf[0] & 0x0F) << 8
        self._read_reg(_XposL)
        x |= self._rx_buf[0]

        self._read_reg(_YposH)
        y = (self._rx_buf[0] & 0x0F) << 8
        self._read_reg(_YposL)
        y |= self._rx_buf[0]

        return self.PRESSED, x, y
