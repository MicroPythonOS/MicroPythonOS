# Copyright (c) 2021 Mark Grosen <mark@grosen.org>
#
# SPDX-License-Identifier: MIT

import struct
from time import sleep

from ._config_file import ConfigDataFile as ConfigData
# from ._config_bytes import ConfigDataBytes as ConfigData


NB_TARGET_PER_ZONE = 1

# set_ranging_mode
RANGING_MODE_AUTONOMOUS = 3
RANGING_MODE_CONTINUOUS = 1

# set_power
POWER_MODE_SLEEP = 0
POWER_MODE_WAKEUP = 1

# set_target_order
TARGET_ORDER_CLOSEST = 1
TARGET_ORDER_STRONGEST = 2

# set_resolution
RESOLUTION_4X4 = 16
RESOLUTION_8X8 = 64

# start_ranging
# values are used as bit offsets so don't change
DATA_AMBIENT_PER_SPAD = 0
DATA_NB_SPADS_ENABLED = 1
DATA_NB_TARGET_DETECTED = 2
DATA_SIGNAL_PER_SPAD = 3
DATA_RANGE_SIGMA_MM = 4
DATA_DISTANCE_MM = 5
DATA_REFLECTANCE = 6
DATA_TARGET_STATUS = 7
DATA_MOTION_INDICATOR = 8

# target status results
STATUS_NOT_UPDATED = 0
STATUS_RATE_TOO_LOW_SPAD = 1
STATUS_TARGET_PHASE = 2
STATUS_SIGMA_TOO_HIGH = 3
STATUS_FAILED = 4
STATUS_VALID = 5
STATUS_NO_WRAP = 6
STATUS_RATE_FAILED = 7
STATUS_RATE_TOO_LOW = 8
STATUS_VALID_LARGE_PULSE = 9
STATUS_NO_PREV_TARGET = 10
STATUS_MEASUREMENT_FAILED = 11
STATUS_BLURRED = 12
STATUS_INCONSISTENT = 13
STATUS_NO_TARGETS = 255

_OFFSET_BUFFER_SIZE = 488
_UI_CMD_STATUS = 0x2C00
_UI_CMD_START = 0x2C04
_UI_CMD_END = 0x2FFF
_DCI_PIPE_CONTROL = 0xCF78
_DCI_SINGLE_RANGE = 0xCD5C
_DCI_DSS_CONFIG = 0xAD38
_DCI_ZONE_CONFIG = 0x5450
_DCI_FREQ_HZ = 0x5458
_DCI_TARGET_ORDER = 0xAE64
_DCI_OUTPUT_LIST = 0xCD78
_DCI_OUTPUT_CONFIG = 0xCD60
_DCI_OUTPUT_ENABLES = 0xCD68
_DCI_INT_TIME = 0x545C
_DCI_RANGING_MODE = 0xAD30
_DCI_SHARPENER = 0xAED8

_START_BH = 0x0000000D
_METADATA_BH = 0x54B400C0
_COMMONDATA_BH = 0x54C00040
_AMBIENT_RATE_BH = 0x54D00104
_SPAD_COUNT_BH = 0x55D00404
_NB_TARGET_DETECTED_BH = 0xCF7C0401
_SIGNAL_RATE_BH = 0xCFBC0404
_RANGE_SIGMA_MM_BH = 0xD2BC0402
_DISTANCE_BH = 0xD33C0402
_REFLECTANCE_BH = 0xD43C0401
_TARGET_STATUS_BH = 0xD47C0401
_MOTION_DETECT_BH = 0xCC5008C0

_COMMONDATA_IDX = 0x54C0
_METADATA_IDX = 0x54B4
_AMBIENT_RATE_IDX = 0x54D0
_SPAD_COUNT_IDX = 0x55D0
_MOTION_DETECT_IDX = 0xCC50
_NB_TARGET_DETECTED_IDX = 0xCF7C
_SIGNAL_RATE_IDX = 0xCFBC
_RANGE_SIGMA_MM_IDX = 0xD2BC
_DISTANCE_IDX = 0xD33C
_REFLECTANCE_EST_PC_IDX = 0xD43C
_TARGET_STATUS_IDX = 0xD47C


class Results:
    def __init__(self):
        self.ambient_per_spad = None
        self.distance_mm = None
        self.nb_spads_enabled = None
        self.nb_target_detected = None
        self.target_status = None
        self.reflectance = None
        self.motion_indicator = None
        self.range_sigma_mm = None
        self.signal_per_spad = None


class VL53L5CX:
    def __init__(self, i2c, addr=0x29, lpn=None):
        self.i2c = i2c
        self.addr = addr
        self._ntpz = NB_TARGET_PER_ZONE   # make option?
        self._lpn = lpn
        self._b1 = bytearray(1)
        self._streamcount = 255
        self._data_read_size = 0
        self.config_data = ConfigData()

    def _poll_for_answer(self, size, pos, reg16, mask, val):
        timeout = 0
        while True:
            data = self._rd_multi(reg16, size)
            if data and ((data[pos] & mask) == val):
                status = 0
                break
            if timeout >= 200:
                # print("\npoll timeout")
                status = -1 if len(data) < 3 else data[2]
                break
            elif size >= 4 and data[2] >= 0x7f:
                status = -2
                break
            else:
                timeout = timeout + 1

        sleep(0.01)
        if status:
            raise ValueError("poll_for_answer failed")
        return status

    @staticmethod
    def _swap_buffer(data):
        for i in range(0, len(data), 4):
            data[i], data[i+1], data[i+2], data[i+3] = data[i+3], data[i+2], \
                data[i+1], data[i]

    def _send_offset_data(self, offset_data, resolution):
        buf = bytearray(offset_data)
        if resolution == 16:
            buf[0x10:0x10+8] = bytes([0x0F, 0x04, 0x04, 0x00, 0x08, 0x10,
                                      0x10, 0x07])
            self._swap_buffer(buf)

            # MP does not support * unpack
            signal_grid = [0] * 64
            for i, w in enumerate(struct.unpack("64I", buf[0x3C:0x3C+256])):
                signal_grid[i] = w
            range_grid = [0] * 64
            for i, w in enumerate(struct.unpack("64h", buf[0x140:0x140+128])):
                range_grid[i] = w

            for j in range(4):
                for i in range(4):
                    signal_grid[i+(4*j)] = int((signal_grid[(2*i)+(16*j)] +
                                                signal_grid[(2*i)+(16*j)+1] +
                                                signal_grid[(2*i)+(16*j)+8] +
                                                signal_grid[(2*i)+(16*j)+9])/4)
                    range_grid[i+(4*j)] = int((range_grid[(2*i)+(16*j)] +
                                               range_grid[(2*i)+(16*j)+1] +
                                               range_grid[(2*i)+(16*j)+8] +
                                               range_grid[(2*i)+(16*j)+9])/4)

            for i in range(48):
                signal_grid[0x10 + i] = 0
                range_grid[0x10 + i] = 0

            buf[0x3C:0x3C+256] = struct.pack("64I", *signal_grid)
            buf[0x140:0x140+128] = struct.pack("64h", *range_grid)
            self._swap_buffer(buf)

        x = buf[8:-4]
        x.extend(bytes([0x00, 0x00, 0x00, 0x0F, 0x03, 0x01, 0x01, 0xE4]))

        self._wr_multi(0x2E18, x)
        return not self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0xFF, 0x03)

    def _send_xtalk_data(self, resolution):
        if resolution == RESOLUTION_4X4:
            xtalk_data = self.config_data.xtalk4x4_data
        else:
            xtalk_data = self.config_data.xtalk_data

        self._wr_multi(0x2CF8, xtalk_data)
        return not self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0xFF, 0x03)

    def _dci_read_data(self, data, index):
        data_size = len(data)
        cmd = bytearray(12)

        cmd[0] = index >> 8
        cmd[1] = index & 0xFF
        cmd[2] = (data_size & 0xFF0) >> 4
        cmd[3] = (data_size & 0xF) << 4
        cmd[7] = 0x0F
        cmd[9] = 0x02
        cmd[11] = 0x08
        self._wr_multi(_UI_CMD_END - 11, cmd)
        self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0xFF, 0x03)

        buf = self._rd_multi(_UI_CMD_START, data_size + 12)
        for i in range(0, data_size, 4):
            data[i] = buf[4 + i + 3]
            data[i + 1] = buf[4 + i + 2]
            data[i + 2] = buf[4 + i + 1]
            data[i + 3] = buf[4 + i + 0]

        # self._dump_data("read", index, data)

        return True

    def _dci_replace_data(self, data, index, new_data, pos):
        self._dci_read_data(data, index)
        for i in range(len(new_data)):
            data[pos + i] = new_data[i]
        self._dci_write_data(data, index)
        return True

    def _dci_write_data(self, data, index):
        data_size = len(data)
        buf = bytearray(data_size + 12)

        # header
        buf[0] = index >> 8
        buf[1] = index & 0xFF
        buf[2] = (data_size & 0xFF0) >> 4
        buf[3] = (data_size & 0x0F) << 4

        # data
        for i in range(0, data_size, 4):
            buf[4 + i] = data[i + 3]
            buf[4 + i + 1] = data[i + 2]
            buf[4 + i + 2] = data[i + 1]
            buf[4 + i + 3] = data[i + 0]

        for i, b in enumerate([0x00, 0x00, 0x00, 0x0f, 0x05, 0x01,
                               (data_size + 8) >> 8,
                               (data_size + 8) & 0xFF], 4 + data_size):
            buf[i] = b

        address = _UI_CMD_END - (data_size + 12) + 1

        # self._dump_data("write", index, buf)

        self._wr_multi(address, buf)
        return not self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0XFF, 0x03)

    @staticmethod
    def _header(word):
        # type - 4, size - 12, idx - 16
        return (word & 0xF), (word & 0xFFF0) >> 4, (word >> 16)

    @staticmethod
    def _ambient_per_spad(raw):
        data = []
        fmt = ">{}I".format(len(raw) // 4)
        for v in struct.unpack(fmt, raw):
            data.append(v // 2048)

        return data

    @staticmethod
    def _distance_mm(raw):
        data = []
        fmt = ">{}h".format(len(raw) // 2)
        for v in struct.unpack(fmt, raw):
            data.append(0 if v < 0 else v >> 2)

        return data

    @staticmethod
    def _nb_spads_enabled(raw):
        fmt = ">{}I".format(len(raw) // 4)
        return [v for v in struct.unpack(fmt, raw)]

    @staticmethod
    def _nb_target_detected(raw):
        return raw

    @staticmethod
    def _target_status(raw):
        return raw

    @staticmethod
    def _reflectance(raw):
        return raw

    @staticmethod
    def _motion_indicator(raw):
        return struct.unpack(">IIBBBB32I", raw)

    @staticmethod
    def _range_sigma_mm(raw):
        data = []
        fmt = ">{}H".format(len(raw) // 2)
        for r in struct.unpack(fmt, raw):
            data.append(r / 128)

        return data

    @staticmethod
    def _signal_per_spad(raw):
        data = []
        fmt = ">{}I".format(len(raw) // 4)
        for r in struct.unpack(fmt, raw):
            data.append(r / 2048)

        return data

    def is_alive(self):
        self._wr_byte(0x7FFF, 0)
        buf = self._rd_multi(0, 2)
        self._wr_byte(0x7FFF, 2)

        return (buf[0] == 0xF0) and (buf[1] == 0x02)

    def init(self):
        # SW reboot sequence
        self._wr_byte(0x7fff, 0x00)
        self._wr_byte(0x0009, 0x04)
        self._wr_byte(0x000F, 0x40)
        self._wr_byte(0x000A, 0x03)
        self._rd_byte(0x7FFF)

        self._wr_byte(0x000C, 0x01)
        self._wr_byte(0x0101, 0x00)
        self._wr_byte(0x0102, 0x00)
        self._wr_byte(0x010A, 0x01)
        self._wr_byte(0x4002, 0x01)
        self._wr_byte(0x4002, 0x00)
        self._wr_byte(0x010A, 0x03)
        self._wr_byte(0x0103, 0x01)
        self._wr_byte(0x000C, 0x00)
        self._wr_byte(0x000F, 0x43)
        sleep(0.001)

        self._wr_byte(0x000F, 0x40)
        self._wr_byte(0x000A, 0x01)
        sleep(0.1)

        # Wait for sensor booted (several ms required to get sensor ready )
        self._wr_byte(0x7fff, 0x00)
        if self._poll_for_answer(1, 0, 0x06, 0xff, 1):
            return -1

        self._wr_byte(0x000E, 0x01)
        self._wr_byte(0x7fff, 0x02)

        # Enable FW access
        self._wr_byte(0x03, 0x0D)
        self._wr_byte(0x7fff, 0x01)
        if self._poll_for_answer(1, 0, 0x21, 0x10, 0x10):
            return -2
        self._wr_byte(0x7fff, 0x00)

        # Enable host access to GO1
        self._wr_byte(0x0C, 0x01)

        # Power ON status
        self._wr_byte(0x7fff, 0x00)
        self._wr_byte(0x101, 0x00)
        self._wr_byte(0x102, 0x00)
        self._wr_byte(0x010A, 0x01)
        self._wr_byte(0x4002, 0x01)
        self._wr_byte(0x4002, 0x00)
        self._wr_byte(0x010A, 0x03)
        self._wr_byte(0x103, 0x01)
        self._wr_byte(0x400F, 0x00)
        self._wr_byte(0x21A, 0x43)
        self._wr_byte(0x21A, 0x03)
        self._wr_byte(0x21A, 0x01)
        self._wr_byte(0x21A, 0x00)
        self._wr_byte(0x219, 0x00)
        self._wr_byte(0x21B, 0x00)

        # Wake up MCU
        self._wr_byte(0x7fff, 0x00)
        self._wr_byte(0x0C, 0x00)
        self._wr_byte(0x7fff, 0x01)
        self._wr_byte(0x20, 0x07)
        self._wr_byte(0x20, 0x06)

        fw = self.config_data.fw_data(0x1000)
        for page, size in enumerate([0x8000, 0x8000, 0x5000], start=9):
            self._wr_byte(0x7fff, page)
            for sub in range(0, size, 0x1000):
                self._wr_multi(sub, next(fw))

        self._wr_byte(0x7fff, 0x01)

        # Check if FW correctly downloaded
        self._wr_byte(0x7fff, 0x02)
        self._wr_byte(0x03, 0x0D)
        self._wr_byte(0x7fff, 0x01)
        if self._poll_for_answer(1, 0, 0x21, 0x10, 0x10):
            return -3
        self._wr_byte(0x7fff, 0x00)
        self._wr_byte(0x0C, 0x01)

        # Reset MCU and wait boot
        self._wr_byte(0x7FFF, 0x00)
        self._wr_byte(0x114, 0x00)
        self._wr_byte(0x115, 0x00)
        self._wr_byte(0x116, 0x42)
        self._wr_byte(0x117, 0x00)
        self._wr_byte(0x0B, 0x00)
        self._wr_byte(0x0C, 0x00)
        self._wr_byte(0x0B, 0x01)
        if self._poll_for_answer(1, 0, 0x06, 0xff, 0x00):
            return -4

        self._wr_byte(0x7fff, 0x02)

        # Get offset NVM data and store them into the offset buffer
        nvm_cmd = bytes([
            0x54, 0x00, 0x00, 0x40,
            0x9E, 0x14, 0x00, 0xC0,
            0x9E, 0x20, 0x01, 0x40,
            0x9E, 0x34, 0x00, 0x40,
            0x9E, 0x38, 0x04, 0x04,
            0x9F, 0x38, 0x04, 0x02,
            0x9F, 0xB8, 0x01, 0x00,
            0x9F, 0xC8, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x0F,
            0x02, 0x02, 0x00, 0x24
        ])

        self._wr_multi(0x2fd8, nvm_cmd)
        if self._poll_for_answer(4, 0, 0x2C00, 0xff, 2):
            return -5

        self._offset_data = self._rd_multi(0x2C04, 492)
        if not self._send_offset_data(self._offset_data, RESOLUTION_4X4):
            return -6

        if not self._send_xtalk_data(RESOLUTION_4X4):
            return -7

        self._wr_multi(0x2C34, self.config_data.default_config_data)
        if self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0xFF, 0x03):
            return -8

        PIPE_CTRL = bytes([self._ntpz, 0x00, 0x01, 0x00])
        if not self._dci_write_data(PIPE_CTRL, _DCI_PIPE_CONTROL):
            return -9

        SINGLE_RANGE = b'\x01\x00\x00\x00'
        if not self._dci_write_data(SINGLE_RANGE, _DCI_SINGLE_RANGE):
            return -10

        return 0

    def start_ranging(self, enables):
        resolution = self.resolution
        self._data_read_size = 0
        self._streamcount = 255

        output_bh_enable = [
            0x00000007,
            0x00000000,
            0x00000000,
            0xC0000000
        ]

        output = [
            _START_BH,
            _METADATA_BH,
            _COMMONDATA_BH,
            _AMBIENT_RATE_BH,
            _SPAD_COUNT_BH,
            _NB_TARGET_DETECTED_BH,
            _SIGNAL_RATE_BH,
            _RANGE_SIGMA_MM_BH,
            _DISTANCE_BH,
            _REFLECTANCE_BH,
            _TARGET_STATUS_BH,
            _MOTION_DETECT_BH
        ]

        # always-on data contribute 3 sizes
        self._data_read_size += (0 + 4) + (4 + 0xc) + (4 + 0x4)

        for e in enables:
            btype, size, idx = self._header(output[e + 3])
            if (btype > 0) and (btype < 0xd):
                if (idx >= 0x54d0) and (idx < (0x54d0 + 960)):
                    size = resolution
                else:
                    size = resolution * self._ntpz
                self._data_read_size += (size * btype) + 4
                output[e + 3] = (idx << 16) | (size << 4) | btype
            else:
                self._data_read_size += size + 4

            output_bh_enable[0] |= 1 << (e + 3)

        # header and footer
        self._data_read_size += 20

        self._dci_write_data(struct.pack("<12I", *output), _DCI_OUTPUT_LIST)

        self._dci_write_data(struct.pack("<II", self._data_read_size,
                                         len(output) + 1),
                             _DCI_OUTPUT_CONFIG)

        self._dci_write_data(struct.pack("<IIII", *output_bh_enable),
                             _DCI_OUTPUT_ENABLES)

        # start xshut bypass (interrupt mode)
        self._wr_byte(0x7FFF, 0)
        self._wr_byte(0x09, 0x05)
        self._wr_byte(0x7FFF, 0x2)

        # start ranging session
        self._wr_multi(_UI_CMD_END - 3, b'\x00\x03\x00\x00')
        return not self._poll_for_answer(4, 1, _UI_CMD_STATUS, 0xFF, 0x03)

    def check_data_ready(self):
        status = False

        buf = self._rd_multi(0, 4)
        if ((buf[0] != self._streamcount) and (buf[0] != 255) and
                (buf[1] == 0x5) and ((buf[2] & 0x5) == 0x5) and
                ((buf[3] & 0x10) == 0x10)):

            self._streamcount = buf[0]
            status = True

        return status

    def get_ranging_data(self):
        results = Results()

        buf = self._rd_multi(0, self._data_read_size)
        self._streamcount = buf[0]

        offset = 16   # skip header
        while offset < len(buf):
            bh = struct.unpack(">I", buf[offset:offset+4])[0]
            btype, size, idx = self._header(bh)
            # print(offset, hex(btype), hex(size), hex(idx))
            # if idx not in self._results:
            #     # print("skipping {} values".format(len(buf) - offset))
            #     break

            if btype > 1 and btype < 0xD:
                msize = btype * size
            else:
                msize = size

            offset += 4
            raw = buf[offset:offset+msize]

            if idx == _AMBIENT_RATE_IDX:
                results.ambient_per_spad = self._ambient_per_spad(raw)
            elif idx == _SPAD_COUNT_IDX:
                results.nb_spads_enabled = self._nb_spads_enabled(raw)
            elif idx == _MOTION_DETECT_IDX:
                results.motion_indicator = self._motion_indicator(raw)
            elif idx == _NB_TARGET_DETECTED_IDX:
                results.nb_target_detected = self._nb_target_detected(raw)
            elif idx == _SIGNAL_RATE_IDX:
                results.signal_per_spad = self._signal_per_spad(raw)
            elif idx == _RANGE_SIGMA_MM_IDX:
                results.range_sigma_mm = self._range_sigma_mm(raw)
            elif idx == _DISTANCE_IDX:
                results.distance_mm = self._distance_mm(raw)
            elif idx == _REFLECTANCE_EST_PC_IDX:
                results.reflectance = self._reflectance(raw)
            elif idx == _TARGET_STATUS_IDX:
                results.target_status = self._target_status(raw)
            # ignore other data types from sensor

            offset += msize

        return results

    def stop_ranging(self):
        buf = self._rd_multi(0x2FFC, 4)
        auto_stop_flag = struct.unpack("<I", buf)
        if auto_stop_flag != 0x4FF:
            self._wr_byte(0x7FFF, 0x00)
            self._wr_byte(0x15, 0x16)
            self._wr_byte(0x14, 0x01)

            timeout = 1000
            while timeout:
                flag = self._rd_byte(0x6)
                if (flag & 0x80):
                    break
                sleep(0.010)
                timeout -= 10

            if timeout == 0:
                raise ValueError("failed to stop MCU")

        # undo MCU stop
        self._wr_byte(0x7FFF, 0x00)
        self._wr_byte(0x14, 0x00)
        self._wr_byte(0x15, 0x00)

        # stop xshut bypass
        self._wr_byte(0x09, 0x04)
        self._wr_byte(0x7FFF, 0x02)

    @property
    def integration_time_ms(self):
        buf = bytearray(20)
        self._dci_read_data(buf, _DCI_INT_TIME)
        return struct.unpack("<I", buf[0:4])[0] / 1000

    @integration_time_ms.setter
    def integration_time_ms(self, itime):
        if (itime < 2) or (itime > 1000):
            raise ValueError("invalid integration time (2 < it < 1000)")

        buf = bytearray(20)
        self._dci_replace_data(buf, _DCI_INT_TIME,
                               struct.pack("I", itime * 1000), 0)

    @property
    def resolution(self):
        buf = bytearray(8)
        self._dci_read_data(buf, _DCI_ZONE_CONFIG)
        return buf[0] * buf[1]

    @resolution.setter
    def resolution(self, resolution):
        if (resolution != RESOLUTION_8X8) and (resolution != RESOLUTION_4X4):
            raise ValueError("invalid resolution")

        buf = bytearray(16)
        self._dci_read_data(buf, _DCI_DSS_CONFIG)

        if resolution == RESOLUTION_8X8:
            buf[0x04] = 16
            buf[0x06] = 16
            buf[0x09] = 1
        else:
            buf[0x04] = 64
            buf[0x06] = 64
            buf[0x09] = 4

        self._dci_write_data(buf, _DCI_DSS_CONFIG)

        buf = bytearray(8)
        self._dci_read_data(buf, _DCI_ZONE_CONFIG)

        if resolution == RESOLUTION_8X8:
            buf[0x00] = 8
            buf[0x01] = 8
            buf[0x04] = 4
            buf[0x05] = 4
        else:
            buf[0x00] = 4
            buf[0x01] = 4
            buf[0x04] = 8
            buf[0x05] = 8

        self._dci_write_data(buf, _DCI_ZONE_CONFIG)

        self._send_offset_data(self._offset_data, resolution)
        self._send_xtalk_data(resolution)

    @property
    def ranging_freq(self):
        buf = bytearray(4)
        self._dci_read_data(buf, _DCI_FREQ_HZ)
        return buf[1]

    @ranging_freq.setter
    def ranging_freq(self, freq):
        buf = bytearray(4)
        self._b1[0] = freq
        return self._dci_replace_data(buf, _DCI_FREQ_HZ, self._b1, 1)

    @property
    def target_order(self):
        buf = bytearray(4)
        self._dci_read_data(buf, _DCI_TARGET_ORDER)
        return buf[0]

    @target_order.setter
    def target_order(self, order):
        buf = bytearray(4)
        self._b1[0] = order
        return self._dci_replace_data(buf, _DCI_TARGET_ORDER, self._b1, 0)

    @property
    def ranging_mode(self):
        buf = bytearray(8)
        self._dci_read_data(buf, _DCI_RANGING_MODE)
        if buf[1] == 1:
            mode = RANGING_MODE_CONTINUOUS
        else:
            mode = RANGING_MODE_AUTONOMOUS

        return mode

    @ranging_mode.setter
    def ranging_mode(self, mode):
        buf = bytearray(8)
        self._dci_read_data(buf, _DCI_RANGING_MODE)
        if mode == RANGING_MODE_CONTINUOUS:
            buf[1] = 0x1
            buf[3] = 0x3
            single_range = 0
        elif mode == RANGING_MODE_AUTONOMOUS:
            buf[1] = 0x3
            buf[3] = 0x2
            single_range = 1
        else:
            raise ValueError("invalid ranging mode")

        self._dci_write_data(buf, _DCI_RANGING_MODE)
        self._dci_write_data(struct.pack(">I", single_range),
                             _DCI_SINGLE_RANGE)

    @property
    def power_mode(self):
        self._wr_byte(0x7FFF, 0x0)
        raw = self._rd_byte(0x9)
        self._wr_byte(0x7FFF, 0x2)

        if raw == 4:
            mode = POWER_MODE_WAKEUP
        elif raw == 2:
            mode = POWER_MODE_SLEEP
        else:
            mode = -1

        return mode

    @power_mode.setter
    def power_mode(self, mode):
        if self.power_mode != mode and mode in [POWER_MODE_SLEEP, POWER_MODE_WAKEUP]:
            self._wr_byte(0x7FFF, 0)
            if mode == POWER_MODE_WAKEUP:
                self._wr_byte(0x9, 0x4)
                self._poll_for_answer(1, 0, 0x6, 0x01, 1)
            elif mode == POWER_MODE_SLEEP:
                self._wr_byte(0x09, 0x02)
                self._poll_for_answer(1, 0, 0x06, 0x01, 0)
            self._wr_byte(0x7FFF, 0x02)

    @property
    def sharpener_percent(self):
        buf = bytearray(16)
        self._dci_read_data(buf, _DCI_SHARPENER)
        return (buf[0xD] * 100) // 255

    @sharpener_percent.setter
    def sharpener_percent(self, value):
        if (value < 0) or (value > 100):
            raise ValueError("invalid sharpener percent")

        self._b1[0] = (value * 255) // 100
        self._dci_replace_data(bytearray(16), _DCI_SHARPENER, self._b1, 0xD)
