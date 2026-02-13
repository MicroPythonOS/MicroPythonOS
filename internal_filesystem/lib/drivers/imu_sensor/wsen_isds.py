"""WSEN_ISDS 6-axis IMU driver for MicroPython.

This driver is for the Würth Elektronik WSEN-ISDS IMU sensor.
Source: https://github.com/Fri3dCamp/badge_2024_micropython/pull/10

MIT License

Copyright (c) 2024 Fri3d Camp contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import time


class Wsen_Isds:
    """Driver for WSEN-ISDS 6-axis IMU (accelerometer + gyroscope)."""

    _ISDS_STATUS_REG = 0x1E  # Status data register
    _ISDS_WHO_AM_I = 0x0F    # WHO_AM_I register

    _REG_TEMP_OUT_L = 0x20

    _REG_G_X_OUT_L = 0x22
    _REG_G_Y_OUT_L = 0x24
    _REG_G_Z_OUT_L = 0x26

    _REG_A_X_OUT_L = 0x28
    _REG_A_Y_OUT_L = 0x2A
    _REG_A_Z_OUT_L = 0x2C

    _REG_A_TAP_CFG = 0x58

    _options = {
        'acc_range': {
            'reg': 0x10, 'mask': 0b11110011, 'shift_left': 2,
            'val_to_bits': {"2g": 0b00, "4g": 0b10, "8g": 0b11, "16g": 0b01}
        },
        'acc_data_rate': {
            'reg': 0x10, 'mask': 0b00001111, 'shift_left': 4,
            'val_to_bits': {
                "0": 0b0000, "1.6Hz": 0b1011, "12.5Hz": 0b0001,
                "26Hz": 0b0010, "52Hz": 0b0011, "104Hz": 0b0100,
                "208Hz": 0b0101, "416Hz": 0b0110, "833Hz": 0b0111,
                "1.66kHz": 0b1000, "3.33kHz": 0b1001, "6.66kHz": 0b1010}
        },
        'gyro_range': {
            'reg': 0x11, 'mask': 0b11110000, 'shift_left': 0,
            'val_to_bits': {
                "125dps": 0b0010, "250dps": 0b0000,
                "500dps": 0b0100, "1000dps": 0b1000, "2000dps": 0b1100}
        },
        'gyro_data_rate': {
            'reg': 0x11, 'mask': 0b00001111, 'shift_left': 4,
            'val_to_bits': {
                "0": 0b0000, "12.5Hz": 0b0001, "26Hz": 0b0010,
                "52Hz": 0b0011, "104Hz": 0b0100, "208Hz": 0b0101,
                "416Hz": 0b0110, "833Hz": 0b0111, "1.66kHz": 0b1000,
                "3.33kHz": 0b1001, "6.66kHz": 0b1010}
        },
        'tap_double_enable': {
            'reg': 0x5B, 'mask': 0b01111111, 'shift_left': 7,
            'val_to_bits': {True: 0b01, False: 0b00}
        },
        'tap_threshold': {
            'reg': 0x59, 'mask': 0b11100000, 'shift_left': 0,
            'val_to_bits': {0: 0b00, 1: 0b01, 2: 0b10, 3: 0b11, 4: 0b100, 5: 0b101,
                            6: 0b110, 7: 0b111, 8: 0b1000, 9: 0b1001}
        },
        'tap_quiet_time': {
            'reg': 0x5A, 'mask': 0b11110011, 'shift_left': 2,
            'val_to_bits': {0: 0b00, 1: 0b01, 2: 0b10, 3: 0b11}
        },
        'tap_duration_time': {
            'reg': 0x5A, 'mask': 0b00001111, 'shift_left': 2,
            'val_to_bits': {0: 0b00, 1: 0b01, 2: 0b10, 3: 0b11, 4: 0b100, 5: 0b101,
                            6: 0b110, 7: 0b111, 8: 0b1000, 9: 0b1001}
        },
        'tap_shock_time': {
            'reg': 0x5A, 'mask': 0b11111100, 'shift_left': 0,
            'val_to_bits': {0: 0b00, 1: 0b01, 2: 0b10, 3: 0b11}
        },
        'tap_single_to_int0': {
            'reg': 0x5E, 'mask': 0b10111111, 'shift_left': 6,
            'val_to_bits': {0: 0b00, 1: 0b01}
        },
        'tap_double_to_int0': {
            'reg': 0x5E, 'mask': 0b11110111, 'shift_left': 3,
            'val_to_bits': {0: 0b00, 1: 0b01}
        },
        'int1_on_int0': { # on the LSM6DSO, this is called "INT2_on_INT1"
            'reg': 0x13, 'mask': 0b11011111, 'shift_left': 5,
            'val_to_bits': {0: 0b00, 1: 0b01}
        },
        'ctrl_do_soft_reset': {
            'reg': 0x12, 'mask': 0b11111110, 'shift_left': 0,
            'val_to_bits': {True: 0b01, False: 0b00}
        },
        'ctrl_do_reboot': {
            'reg': 0x12, 'mask': 0b01111111, 'shift_left': 7,
            'val_to_bits': {True: 0b01, False: 0b00}
        },
    }

    def __init__(self, i2c, address=0x6B, acc_range="2g", acc_data_rate="1.6Hz",
                 gyro_range="125dps", gyro_data_rate="12.5Hz"):
        """Initialize WSEN-ISDS IMU.

        Args:
            i2c: I2C bus instance
            address: I2C address (default 0x6B)
            acc_range: Accelerometer range ("2g", "4g", "8g", "16g")
            acc_data_rate: Accelerometer data rate ("0", "1.6Hz", "12.5Hz", ...)
            gyro_range: Gyroscope range ("125dps", "250dps", "500dps", "1000dps", "2000dps")
            gyro_data_rate: Gyroscope data rate ("0", "12.5Hz", "26Hz", ...")
        """
        self.i2c = i2c
        self.address = address

        self.acc_range = 0
        self.acc_sensitivity = 0

        self.gyro_range = 0
        self.gyro_sensitivity = 0

        self.set_acc_range(acc_range)
        self.set_acc_data_rate(acc_data_rate)

        self.set_gyro_range(gyro_range)
        self.set_gyro_data_rate(gyro_data_rate)

        # Give sensors time to stabilize
        time.sleep_ms(100)

    def get_chip_id(self):
        """Get chip ID for detection. Returns WHO_AM_I register value."""
        try:
            return self.i2c.readfrom_mem(self.address, self._ISDS_WHO_AM_I, 1)[0]
        except:
            return 0

    def _write_option(self, option, value):
        """Write configuration option to sensor register."""
        opt = Wsen_Isds._options[option]
        try:
            bits = opt["val_to_bits"][value]
            old_value = self.i2c.readfrom_mem(self.address, opt["reg"], 1)[0]
            config_value = old_value
            config_value &= opt["mask"]
            config_value |= (bits << opt["shift_left"])
            self.i2c.writeto_mem(self.address, opt["reg"], bytes([config_value]))
        except KeyError as err:
            print(f"Invalid option: {option}, or invalid option value: {value}.", err)

    def set_acc_range(self, acc_range):
        """Set accelerometer range."""
        self._write_option('acc_range', acc_range)
        self.acc_range = acc_range
        self._acc_calc_sensitivity()

    def set_acc_data_rate(self, acc_rate):
        """Set accelerometer data rate."""
        self._write_option('acc_data_rate', acc_rate)

    def set_gyro_range(self, gyro_range):
        """Set gyroscope range."""
        self._write_option('gyro_range', gyro_range)
        self.gyro_range = gyro_range
        self._gyro_calc_sensitivity()

    def set_gyro_data_rate(self, gyro_rate):
        """Set gyroscope data rate."""
        self._write_option('gyro_data_rate', gyro_rate)

    def _gyro_calc_sensitivity(self):
        """Calculate gyroscope sensitivity based on range."""
        sensitivity_mapping = {
            "125dps": 4.375,
            "250dps": 8.75,
            "500dps": 17.5,
            "1000dps": 35,
            "2000dps": 70
        }

        if self.gyro_range in sensitivity_mapping:
            self.gyro_sensitivity = sensitivity_mapping[self.gyro_range]
        else:
            print("Invalid range value:", self.gyro_range)

    def soft_reset(self):
        """Perform soft reset of the sensor."""
        self._write_option('ctrl_do_soft_reset', True)

    def reboot(self):
        """Reboot the sensor."""
        self._write_option('ctrl_do_reboot', True)

    def set_interrupt(self, interrupts_enable=False, inact_en=False, slope_fds=False,
                      tap_x_en=True, tap_y_en=True, tap_z_en=True):
        """Configure interrupt for tap gestures on INT0 pad."""
        config_value = 0b00000000

        if interrupts_enable:
            config_value |= (1 << 7)
        if inact_en:
            inact_en = 0x01
            config_value |= (inact_en << 5)
        if slope_fds:
            config_value |= (1 << 4)
        if tap_x_en:
            config_value |= (1 << 3)
        if tap_y_en:
            config_value |= (1 << 2)
        if tap_z_en:
            config_value |= (1 << 1)

        self.i2c.writeto_mem(self.address, Wsen_Isds._REG_A_TAP_CFG,
                             bytes([config_value]))

        self._write_option('tap_double_enable', False)
        self._write_option('tap_threshold', 9)
        self._write_option('tap_quiet_time', 1)
        self._write_option('tap_duration_time', 5)
        self._write_option('tap_shock_time', 2)
        self._write_option('tap_single_to_int0', 1)
        self._write_option('tap_double_to_int0', 1)
        self._write_option('int1_on_int0', 1)

    def _acc_calc_sensitivity(self):
        """Calculate accelerometer sensitivity based on range (in mg/digit)."""
        sensitivity_mapping = {
            "2g": 0.061,
            "4g": 0.122,
            "8g": 0.244,
            "16g": 0.488
        }
        if self.acc_range in sensitivity_mapping:
            self.acc_sensitivity = sensitivity_mapping[self.acc_range]
        else:
            print("Invalid range value:", self.acc_range)

    def _read_raw_accelerations(self):
        """Read raw accelerometer data."""
        if not self._acc_data_ready():
            raise Exception("sensor data not ready")

        raw = self.i2c.readfrom_mem(self.address, Wsen_Isds._REG_A_X_OUT_L, 6)

        raw_a_x = self._convert_from_raw(raw[0], raw[1])
        raw_a_y = self._convert_from_raw(raw[2], raw[3])
        raw_a_z = self._convert_from_raw(raw[4], raw[5])

        return raw_a_x * self.acc_sensitivity, raw_a_y * self.acc_sensitivity, raw_a_z * self.acc_sensitivity


    @property
    def temperature(self) -> float:
        temp_raw = self._read_raw_temperature()
        return ((temp_raw / 256.0) + 25.0)

    def _read_raw_temperature(self):
        """Read raw temperature data."""
        if not self._temp_data_ready():
            raise Exception("temp sensor data not ready")

        raw = self.i2c.readfrom_mem(self.address, Wsen_Isds._REG_TEMP_OUT_L, 2)
        raw_temp = self._convert_from_raw(raw[0], raw[1])
        return raw_temp

    def _read_raw_angular_velocities(self):
        """Read raw gyroscope data."""
        if not self._gyro_data_ready():
            raise Exception("sensor data not ready")

        raw = self.i2c.readfrom_mem(self.address, Wsen_Isds._REG_G_X_OUT_L, 6)

        raw_g_x = self._convert_from_raw(raw[0], raw[1])
        raw_g_y = self._convert_from_raw(raw[2], raw[3])
        raw_g_z = self._convert_from_raw(raw[4], raw[5])

        return raw_g_x * self.gyro_sensitivity, raw_g_y * self.gyro_sensitivity, raw_g_z * self.gyro_sensitivity

    @staticmethod
    def _convert_from_raw(b_l, b_h):
        """Convert two bytes (little-endian) to signed 16-bit integer."""
        c = (b_h << 8) | b_l
        if c & (1 << 15):
            c -= 1 << 16
        return c

    def _acc_data_ready(self):
        """Check if accelerometer data is ready."""
        return self._get_status_reg()[0]

    def _gyro_data_ready(self):
        """Check if gyroscope data is ready."""
        return self._get_status_reg()[1]

    def _temp_data_ready(self):
        """Check if accelerometer data is ready."""
        return self._get_status_reg()[2]

    def _acc_gyro_data_ready(self):
        """Check if both accelerometer and gyroscope data are ready."""
        status_reg = self._get_status_reg()
        return status_reg[0], status_reg[1]

    def _get_status_reg(self):
        """Read status register.

        Returns:
            Tuple (acc_data_ready, gyro_data_ready, temp_data_ready)
        """
        # STATUS_REG (0x1E) is a single byte with bit flags:
        # Bit 0: XLDA (accelerometer data available)
        # Bit 1: GDA (gyroscope data available)
        # Bit 2: TDA (temperature data available)
        status = self.i2c.readfrom_mem(self.address, Wsen_Isds._ISDS_STATUS_REG, 1)[0]

        acc_data_ready = bool(status & 0x01)   # Bit 0
        gyro_data_ready = bool(status & 0x02)  # Bit 1
        temp_data_ready = bool(status & 0x04)  # Bit 2

        return acc_data_ready, gyro_data_ready, temp_data_ready
