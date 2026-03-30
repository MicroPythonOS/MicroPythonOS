# AXP192 Power Management IC Driver for M5Stack Core2
# I2C address: 0x34
# Datasheet reference + M5Stack Core2 specific initialization

from micropython import const

# Registers
_REG_POWER_STATUS = const(0x00)
_REG_CHARGE_STATUS = const(0x01)
_REG_POWER_OUTPUT_CTRL = const(0x12)
_REG_DCDC1_VOLTAGE = const(0x26)
_REG_DCDC3_VOLTAGE = const(0x27)
_REG_LDO23_VOLTAGE = const(0x28)
_REG_VBUS_IPSOUT = const(0x30)
_REG_POWER_OFF = const(0x32)
_REG_CHARGE_CTRL1 = const(0x33)
_REG_BACKUP_CHG = const(0x35)
_REG_PEK_PARAMS = const(0x36)
_REG_ADC_ENABLE1 = const(0x82)
_REG_GPIO0_FUNCTION = const(0x90)
_REG_GPIO0_LDO_VOLTAGE = const(0x91)
_REG_GPIO1_FUNCTION = const(0x92)
_REG_GPIO2_FUNCTION = const(0x93)
_REG_GPIO_SIGNAL = const(0x94)
_REG_GPIO4_FUNCTION = const(0x95)
_REG_GPIO34_SIGNAL = const(0x96)
_REG_COULOMB_CTRL = const(0xB8)

# ADC data registers
_REG_BAT_VOLTAGE_H = const(0x78)
_REG_BAT_CURRENT_IN_H = const(0x7A)
_REG_BAT_CURRENT_OUT_H = const(0x7C)
_REG_APS_VOLTAGE_H = const(0x7E)

# Power output control bits (register 0x12)
_BIT_EXTEN = const(6)  # EXTEN (5V boost)
_BIT_DCDC2 = const(4)
_BIT_LDO3 = const(3)
_BIT_LDO2 = const(2)
_BIT_DCDC3 = const(1)
_BIT_DCDC1 = const(0)

# Bus power mode
_MBUS_MODE_INPUT = const(0)
_MBUS_MODE_OUTPUT = const(1)

I2C_ADDR = const(0x34)


class AXP192:
    """AXP192 power management driver for M5Stack Core2."""

    def __init__(self, i2c, addr=I2C_ADDR):
        self._i2c = i2c
        self._addr = addr
        self._buf1 = bytearray(1)
        self._buf2 = bytearray(2)

    def _read_reg(self, reg):
        self._buf1[0] = reg
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf1)
        return self._buf1[0]

    def _write_reg(self, reg, val):
        self._buf1[0] = val
        self._i2c.writeto_mem(self._addr, reg, self._buf1)

    def _read_12bit(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf2)
        return (self._buf2[0] << 4) | self._buf2[1]

    def _read_13bit(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf2)
        return (self._buf2[0] << 5) | self._buf2[1]

    def init_core2(self):
        """Initialize AXP192 for M5Stack Core2 hardware."""
        # VBUS-IPSOUT path: set N_VBUSEN pin control, auto VBUS current limit
        self._write_reg(_REG_VBUS_IPSOUT, (self._read_reg(_REG_VBUS_IPSOUT) & 0x04) | 0x02)

        # GPIO1: Open-drain output (Touch RST control)
        self._write_reg(_REG_GPIO1_FUNCTION, self._read_reg(_REG_GPIO1_FUNCTION) & 0xF8)

        # GPIO2: Open-drain output (Speaker enable control)
        self._write_reg(_REG_GPIO2_FUNCTION, self._read_reg(_REG_GPIO2_FUNCTION) & 0xF8)

        # RTC battery charge: 3.0V, 200uA
        self._write_reg(_REG_BACKUP_CHG, (self._read_reg(_REG_BACKUP_CHG) & 0x1C) | 0xA2)

        # Set ESP32 core voltage (DCDC1) to 3350mV
        self.set_dcdc1_voltage(3350)

        # Set LCD backlight voltage (DCDC3) to 2800mV
        self.set_dcdc3_voltage(2800)

        # Set LDO2 (LCD logic + SD card) to 3300mV
        self.set_ldo2_voltage(3300)

        # Set LDO3 (vibration motor) to 2000mV (low to keep motor off initially)
        self.set_ldo3_voltage(2000)

        # Enable LDO2 (LCD logic power)
        self.set_ldo2_enable(True)

        # Enable DCDC3 (LCD backlight)
        self.set_dcdc3_enable(True)

        # Disable LDO3 at startup (vibration motor off)
        self.set_ldo3_enable(False)

        # Set charging current to 100mA
        self.set_charge_current(0)  # 0 = 100mA

        # GPIO4: NMOS open-drain output (LCD RST)
        self._write_reg(_REG_GPIO4_FUNCTION, (self._read_reg(_REG_GPIO4_FUNCTION) & 0x72) | 0x84)

        # PEK parameters: power key settings
        self._write_reg(_REG_PEK_PARAMS, 0x4C)

        # Enable all ADCs
        self._write_reg(_REG_ADC_ENABLE1, 0xFF)

        # Check power input and configure bus power mode
        if self._read_reg(_REG_POWER_STATUS) & 0x08:
            self._write_reg(_REG_VBUS_IPSOUT, self._read_reg(_REG_VBUS_IPSOUT) | 0x80)
            self._set_bus_power_mode(_MBUS_MODE_INPUT)
        else:
            self._set_bus_power_mode(_MBUS_MODE_OUTPUT)

        # Perform LCD + Touch reset sequence (both share AXP192 GPIO4)
        self.set_lcd_reset(False)
        import time
        time.sleep_ms(100)
        self.set_lcd_reset(True)
        time.sleep_ms(300)  # FT6336U needs ~300ms after reset to be ready

        # Enable speaker amp after init
        self.set_speaker_enable(True)

    # -- Voltage setters --

    def set_dcdc1_voltage(self, mv):
        """Set DCDC1 voltage (ESP32 core). Range: 700-3500mV, step 25mV."""
        val = max(0, min(127, (mv - 700) // 25))
        self._write_reg(_REG_DCDC1_VOLTAGE, (self._read_reg(_REG_DCDC1_VOLTAGE) & 0x80) | val)

    def set_dcdc3_voltage(self, mv):
        """Set DCDC3 voltage (LCD backlight). Range: 700-3500mV, step 25mV."""
        val = max(0, min(127, (mv - 700) // 25))
        self._write_reg(_REG_DCDC3_VOLTAGE, (self._read_reg(_REG_DCDC3_VOLTAGE) & 0x80) | val)

    def set_ldo2_voltage(self, mv):
        """Set LDO2 voltage. Range: 1800-3300mV, step 100mV."""
        val = max(0, min(15, (mv - 1800) // 100))
        self._write_reg(_REG_LDO23_VOLTAGE, (self._read_reg(_REG_LDO23_VOLTAGE) & 0x0F) | (val << 4))

    def set_ldo3_voltage(self, mv):
        """Set LDO3 voltage. Range: 1800-3300mV, step 100mV."""
        val = max(0, min(15, (mv - 1800) // 100))
        self._write_reg(_REG_LDO23_VOLTAGE, (self._read_reg(_REG_LDO23_VOLTAGE) & 0xF0) | val)

    # -- Power output enable/disable --

    def _set_power_output(self, bit, enable):
        reg = self._read_reg(_REG_POWER_OUTPUT_CTRL)
        if enable:
            reg |= (1 << bit)
        else:
            reg &= ~(1 << bit)
        self._write_reg(_REG_POWER_OUTPUT_CTRL, reg)

    def set_dcdc1_enable(self, enable):
        self._set_power_output(_BIT_DCDC1, enable)

    def set_dcdc3_enable(self, enable):
        self._set_power_output(_BIT_DCDC3, enable)

    def set_ldo2_enable(self, enable):
        self._set_power_output(_BIT_LDO2, enable)

    def set_ldo3_enable(self, enable):
        self._set_power_output(_BIT_LDO3, enable)

    # -- GPIO control (used for peripherals) --

    def set_lcd_reset(self, state):
        """Control LCD reset via AXP192 GPIO4."""
        data = self._read_reg(_REG_GPIO34_SIGNAL)
        if state:
            data |= 0x02
        else:
            data &= ~0x02
        self._write_reg(_REG_GPIO34_SIGNAL, data)

    def set_touch_reset(self, state):
        """Control touch controller reset via AXP192 GPIO4 (shared with LCD)."""
        self.set_lcd_reset(state)

    def set_speaker_enable(self, state):
        """Control speaker amplifier enable via AXP192 GPIO2."""
        data = self._read_reg(_REG_GPIO_SIGNAL)
        if state:
            data |= 0x04
        else:
            data &= ~0x04
        self._write_reg(_REG_GPIO_SIGNAL, data)

    def _set_bus_power_mode(self, mode):
        if mode == _MBUS_MODE_INPUT:
            # GPIO0 LDO output, pull up N_VBUSEN to disable 5V from BUS
            data = self._read_reg(0x91)
            self._write_reg(0x91, (data & 0x0F) | 0xF0)
            data = self._read_reg(0x90)
            self._write_reg(0x90, (data & 0xF8) | 0x02)
            # Enable EXTEN for 5V boost
            data = self._read_reg(_REG_POWER_OUTPUT_CTRL)
            self._write_reg(_REG_POWER_OUTPUT_CTRL, data | 0x40)
        else:
            # Disable 5V boost
            data = self._read_reg(_REG_POWER_OUTPUT_CTRL)
            self._write_reg(_REG_POWER_OUTPUT_CTRL, data & 0xBF)
            # GPIO0 floating, external pulldown enables BUS_5V supply
            data = self._read_reg(0x90)
            self._write_reg(0x90, (data & 0xF8) | 0x01)

    # -- Charging --

    def set_charge_current(self, level):
        """Set charge current. 0=100mA, 1=190mA, ..., 8=780mA, etc."""
        data = self._read_reg(_REG_CHARGE_CTRL1)
        data = (data & 0xF0) | (level & 0x0F)
        self._write_reg(_REG_CHARGE_CTRL1, data)

    # -- Battery / power readings --

    def get_battery_voltage(self):
        """Get battery voltage in volts."""
        return self._read_12bit(_REG_BAT_VOLTAGE_H) * 1.1 / 1000.0

    def get_battery_current(self):
        """Get net battery current in mA (positive=charging, negative=discharging)."""
        current_in = self._read_13bit(_REG_BAT_CURRENT_IN_H) * 0.5
        current_out = self._read_13bit(_REG_BAT_CURRENT_OUT_H) * 0.5
        return current_in - current_out

    def is_charging(self):
        return bool(self._read_reg(_REG_POWER_STATUS) & 0x04)

    def is_vbus_present(self):
        return bool(self._read_reg(_REG_POWER_STATUS) & 0x20)

    def get_battery_level(self):
        """Estimate battery percentage (simple linear approximation)."""
        v = self.get_battery_voltage()
        if v < 3.2:
            return 0
        pct = (v - 3.12) * 100.0
        return min(100, max(0, int(pct)))

    # -- Screen brightness via DCDC3 --

    def set_screen_brightness(self, percent):
        """Set screen brightness 0-100% by adjusting DCDC3 voltage (2500-3300mV)."""
        percent = max(0, min(100, percent))
        mv = 2500 + int(percent * 8)  # 2500mV-3300mV
        self.set_dcdc3_voltage(mv)

    # -- Power control --

    def power_off(self):
        """Cut all power except RTC (LDO1)."""
        self._write_reg(_REG_POWER_OFF, self._read_reg(_REG_POWER_OFF) | 0x80)

    def set_vibration(self, enable):
        """Enable/disable vibration motor via LDO3."""
        self.set_ldo3_enable(enable)
