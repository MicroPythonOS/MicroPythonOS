import os
import sys

import i2c
import lvgl as lv
from mpos import Activity

try:
    _dirname = os.path.dirname
except AttributeError:
    def _dirname(path):
        if not path:
            return ""
        slash_index = path.rfind("/")
        if slash_index == -1:
            return ""
        return path[:slash_index]

ASSETS_DIR = _dirname(__file__) if "__file__" in globals() else "."
if ASSETS_DIR not in sys.path:
    sys.path.append(ASSETS_DIR)

from vl53l5cx import DATA_DISTANCE_MM, DATA_TARGET_STATUS
from vl53l5cx import RESOLUTION_4X4, RESOLUTION_8X8, STATUS_VALID
from vl53l5cx.mp import VL53L5CXMP


class _MockRangingData:

    def __init__(self, distance_mm, target_status):
        self.distance_mm = distance_mm
        self.target_status = target_status


class MockVL53L5CXMP:

    def __init__(self, seed=1337):
        self._resolution = RESOLUTION_8X8
        self.ranging_freq = 2
        self._seed = seed & 0x7FFFFFFF

    def _randint(self, low, high):
        self._seed = (1103515245 * self._seed + 12345) & 0x7FFFFFFF
        span = high - low + 1
        return low + (self._seed % span)

    @property
    def resolution(self):
        return self._resolution

    @resolution.setter
    def resolution(self, value):
        self._resolution = value

    def is_alive(self):
        return True

    def init(self):
        return True

    def start_ranging(self, *_):
        return True

    def check_data_ready(self):
        return True

    def get_ranging_data(self):
        side = 4 if self._resolution == RESOLUTION_4X4 else 8
        distance = []
        status = []
        for index in range(side * side):
            row = index // side
            col = index % side
            base_value = (row * 650 + col * 210 + 200) % 4001
            jitter = self._randint(-45, 45)
            value = max(0, min(4000, base_value + jitter))
            distance.append(value)
            if (row + col + self._randint(0, 3)) % 6 == 0:
                status.append(0)
            else:
                status.append(STATUS_VALID)
        import time
        time.sleep(1)
        return _MockRangingData(distance, status)


class TimeOfFlight(Activity):

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_width(lv.pct(100))
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.setContentView(screen)

        try:
            i2c_bus = i2c.I2C.Bus(host=0, scl=18, sda=9, freq=400000, use_locks=False)
            # i2c_bus.scan() # address 0x29 = 41
            tof = VL53L5CXMP(i2c_bus)
        except AttributeError:
            tof = MockVL53L5CXMP()

        # don't call to.reset() because that's not needed (and errors) when there's no LPn pin

        if not tof.is_alive():
            raise ValueError("VL53L5CX not detected")

        tof.init()

        # tof.resolution = RESOLUTION_4X4
        # grid = 3

        tof.resolution = RESOLUTION_8X8
        grid = 7

        tof.ranging_freq = 2

        tof.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})

        for count in range(0, 10):
            while not tof.check_data_ready():
                pass
            results = tof.get_ranging_data()
            distance = results.distance_mm
            status = results.target_status

            rows = []
            row_cells = []
            for i, d in enumerate(distance):
                if status[i] == STATUS_VALID:
                    cell = "{:4}".format(d)
                    print(cell, end=" ")
                else:
                    cell = "xxxx"
                    print("xxxx", end=" ")

                row_cells.append(cell)

                if (i & grid) == grid:
                    print("")
                    rows.append(" ".join(row_cells))
                    row_cells = []

            print("")
            label.set_text("\n".join(rows))
