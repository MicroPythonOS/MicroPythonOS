# This has only been tested with the Fri3d 2026 Badge and the Time of Flight addon

from mpos import DeviceManager
import lvgl as lv
from mpos import Activity, DisplayMetrics
import mpos.lights as LightsManager

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
        return _MockRangingData(distance, status)


class TimeOfFlight(Activity):

    def __init__(self):
        super().__init__()
        self.canvas = None
        self.canvas_layer = None
        self.canvas_buf = None
        self.canvas_width = None
        self.canvas_height = None
        self.rect_dsc = None
        self.timer = None
        self.tof = None
        self.grid = None

    def onCreate(self):
        screen = lv.obj()
        self._init_canvas(screen)
        self.timer = None

        try:
            i2c_bus = DeviceManager.getBus(type="i2c")
            if i2c_bus is None:
                raise AttributeError("I2C bus not available")
            tof = VL53L5CXMP(i2c_bus, addr=0x29)
            print("Time of Flight starting in actual hardware mode.")
        except AttributeError:
            print("Time of Flight starting in simulation mode.")
            tof = MockVL53L5CXMP()

        # don't call to.reset() because that's not needed (and errors) when there's no LPn pin

        if not tof.is_alive():
            raise ValueError("VL53L5CX not detected")

        tof.init()

        # tof.resolution = RESOLUTION_4X4
        # grid = 4

        tof.resolution = RESOLUTION_8X8
        grid = 8

        tof.ranging_freq = 2

        tof.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})

        self.tof = tof
        self.grid = grid

        self.setContentView(screen)

    def _init_canvas(self, screen):
        self.canvas_width = DisplayMetrics.width()
        self.canvas_height = DisplayMetrics.height()

        canvas = lv.canvas(screen)
        canvas.set_size(self.canvas_width, self.canvas_height)
        canvas.align(lv.ALIGN.TOP_LEFT, 0, 0)
        canvas.set_style_border_width(0, 0)
        canvas.set_style_bg_color(lv.color_black(), lv.PART.MAIN)

        self.canvas_buf = bytearray(self.canvas_width * self.canvas_height * 4)
        canvas.set_buffer(self.canvas_buf, self.canvas_width, self.canvas_height, lv.COLOR_FORMAT.NATIVE)

        self.canvas_layer = lv.layer_t()
        canvas.init_layer(self.canvas_layer)

        rect_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(rect_dsc)
        rect_dsc.bg_opa = lv.OPA.COVER
        rect_dsc.border_width = 0
        self.rect_dsc = rect_dsc

        self.canvas = canvas
        self._clear_canvas()

    def _clear_canvas(self):
        if self.canvas is None:
            return
        self.canvas.fill_bg(lv.color_black(), lv.OPA.COVER)

    def _flip_over_y(self, distance, status):
        grid = self.grid or 1
        if grid <= 1:
            return distance, status
        length = min(len(distance), len(status))
        flipped_distance = [0] * length
        flipped_status = [0] * length
        for idx in range(length):
            row = idx // grid
            col = idx % grid
            if row >= grid:
                continue
            flipped_idx = row * grid + (grid - 1 - col)
            if flipped_idx >= length:
                continue
            flipped_distance[flipped_idx] = distance[idx]
            flipped_status[flipped_idx] = status[idx]
        return flipped_distance, flipped_status

    def _flip_over_x(self, distance, status):
        grid = self.grid or 1
        if grid <= 1:
            return distance, status
        length = min(len(distance), len(status))
        flipped_distance = [0] * length
        flipped_status = [0] * length
        for idx in range(length):
            row = idx // grid
            col = idx % grid
            if row >= grid:
                continue
            flipped_idx = (grid - 1 - row) * grid + col
            if flipped_idx >= length:
                continue
            flipped_distance[flipped_idx] = distance[idx]
            flipped_status[flipped_idx] = status[idx]
        return flipped_distance, flipped_status

    def _draw_grid(self, distance, status):
        if self.canvas is None:
            return
        self._clear_canvas()

        grid = self.grid or 1
        cell_w = max(1, self.canvas_width // grid)
        cell_h = max(1, self.canvas_height // grid)

        self.canvas.init_layer(self.canvas_layer)
        for i, d in enumerate(distance):
            if status[i] != STATUS_VALID:
                continue
            row = i // grid
            col = i % grid
            if row >= grid:
                continue

            color = self._distance_color(d)
            self._fill_rect(col, row, cell_w, cell_h, grid, color)

        self.canvas.finish_layer(self.canvas_layer)

    def _fill_rect(self, col, row, cell_w, cell_h, grid, color):
        x1 = col * cell_w
        y1 = row * cell_h
        if col == grid - 1:
            x2 = self.canvas_width - 1
        else:
            x2 = (col + 1) * cell_w - 1
        if row == grid - 1:
            y2 = self.canvas_height - 1
        else:
            y2 = (row + 1) * cell_h - 1

        area = lv.area_t()
        area.x1 = x1
        area.y1 = y1
        area.x2 = x2
        area.y2 = y2

        self.rect_dsc.bg_color = color
        lv.draw_rect(self.canvas_layer, self.rect_dsc, area)

    def _distance_color(self, distance_mm):
        intensity = self._distance_intensity(distance_mm)
        return lv.color_make(0, intensity, 0)

    def _distance_intensity(self, distance_mm):
        return int(self._distance_norm(distance_mm) * 255)

    def _distance_norm(self, distance_mm):
        distance_mm = max(0, min(1000, distance_mm))
        return 1.0 - (distance_mm / 1000)

    def _clamp01(self, value):
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _rainbow_color(self, t):
        hue = t * 300.0
        h = hue / 60.0
        i = int(h)
        f = h - i

        if i == 0:
            r, g, b = 1.0, f, 0.0
        elif i == 1:
            r, g, b = 1.0 - f, 1.0, 0.0
        elif i == 2:
            r, g, b = 0.0, 1.0, f
        elif i == 3:
            r, g, b = 0.0, 1.0 - f, 1.0
        elif i == 4:
            r, g, b = f, 0.0, 1.0
        else:
            r, g, b = 1.0, 0.0, 1.0 - f

        return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5))

    def _update_leds(self, distance, status):
        if self.grid is None:
            return
        grid = self.grid or 1
        rows = min(8, len(distance) // grid)
        if rows == 0:
            return

        for row in range(rows):
            row_start = row * grid
            best_idx = None
            best_closeness = -1.0
            total_closeness = 0.0
            count = 0

            for col in range(grid):
                idx = row_start + col
                if idx >= len(distance):
                    break
                if status[idx] != STATUS_VALID:
                    continue
                closeness = self._distance_norm(distance[idx])
                total_closeness += closeness
                count += 1
                if closeness > best_closeness:
                    best_closeness = closeness
                    best_idx = col

            if count == 0:
                LightsManager.set_led(5 + row, 0, 0, 0)
                continue

            avg_closeness = total_closeness / count
            brightness = self._clamp01(max(best_closeness, avg_closeness) * 1.2)

            if grid == 1:
                pos = 0.0
            else:
                pos = best_idx / (grid - 1)

            base_r, base_g, base_b = self._rainbow_color(pos)
            red = int(base_r * brightness)
            green = int(base_g * brightness)
            blue = int(base_b * brightness)

            LightsManager.set_led(5 + row, red, green, blue)

        LightsManager.write()

    def onResume(self, screen):
        if self.tof is None:
            return
        LightsManager.set_led_num(5+8)
        for lednr in range(0,5+8):
            LightsManager.set_led(lednr, 255, 0, 0)
        LightsManager.write()
        if self.timer is None:
            self.timer = lv.timer_create(self.refresh, 1000, None)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None
        LightsManager.clear()
        LightsManager.write()
        LightsManager.set_led_num(5)

    def refresh(self, timer):
        if self.tof is None:
            return
        while not self.tof.check_data_ready():
            pass
        results = self.tof.get_ranging_data()
        distance = results.distance_mm
        status = results.target_status
        distance, status = self._flip_over_x(distance, status)

        row_cells = []

        for i, d in enumerate(distance):
            if status[i] == STATUS_VALID:
                cell = "{:4}".format(d)
                print(cell, end=" ")
            else:
                cell = "{:4}".format(d)
                print(f"{cell}?", end=" ")

            row_cells.append(cell)

            if (i + 1) % self.grid == 0:
                print("")
                row_cells = []

        print("")
        self._draw_grid(distance, status)
        self._update_leds(distance, status)
