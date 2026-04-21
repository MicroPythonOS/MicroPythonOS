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


class TimeOfFlight(Activity):

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_width(lv.pct(100))
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.setContentView(screen)

        i2c_bus = i2c.I2C.Bus(host=0, scl=18, sda=9, freq=400000, use_locks=False)
        # i2c_bus.scan() # address 0x29 = 41

        tof = VL53L5CXMP(i2c_bus)
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
