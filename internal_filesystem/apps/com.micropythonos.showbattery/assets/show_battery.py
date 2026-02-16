"""
from machine import ADC, Pin # do this inside the try because it will fail on desktop
adc = ADC(Pin(13))
# Set ADC to 11dB attenuation for 0–3.3V range (common for ESP32)
adc.atten(ADC.ATTN_11DB)
adc.read()

scale factor 0.002 is (4.15 / 4095) * 2
BUT shows 4.90 instead of 4.13
BUT shows 5.018 instead of 4.65 (raw ADC read: 2366)
SO substract 0.77
# at 2366

2506 is 4.71 (not 4.03)
scale factor 0.002 is (4.15 / 4095) * 2
BUT shows 4.90 instead of 4.13
BUT shows 5.018 instead of 4.65 (raw ADC read: 2366)
SO substract 0.77
# at 2366

USB power:
2506 is 4.71 (not 4.03)
2498
2491

battery power:
2482 is 4.180
2470 is 4.170
2457 is 4.147
2433 is 4.109
2429 is 4.102
2393 is 4.044
2369 is 4.000
2343 is 3.957
2319 is 3.916
2269 is 3.831

I want application that will show big time (hour, minutes), with smaller seconds, date, and current battery parameters on the left side, on the right side, i want big battery icon, green when over 30 percent, red otherwise, and in bottom left I want graph of history values for voltage and percentage.

"""

import lvgl as lv
import mpos.time
from mpos import Activity, BatteryManager
from mpos.battery_manager import MAX_VOLTAGE, MIN_VOLTAGE

HISTORY_LEN = 60

DARKPINK = lv.color_hex(0xEC048C)
BLACK = lv.color_hex(0x000000)

class ShowBattery(Activity):

    refresh_timer = None

    history_v = []
    history_p = []

    def onCreate(self):
        main_content = lv.obj()
        main_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        main_content.set_style_pad_all(0, 0)
        main_content.set_size(lv.pct(100), lv.pct(100))

        # --- TOP FLEX BOX: INFORMATION ---

        info_column = lv.obj(main_content)
        info_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        info_column.set_style_pad_all(1, 1)
        info_column.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.lbl_datetime = lv.label(info_column)
        self.lbl_datetime.set_style_text_font(lv.font_montserrat_16, 0)

        self.lbl_battery = lv.label(info_column)
        self.lbl_battery.set_style_text_font(lv.font_montserrat_24, 0)

        self.lbl_battery_raw = lv.label(info_column)
        self.lbl_battery_raw.set_style_text_font(lv.font_montserrat_14, 0)

        self.clear_cache_checkbox = lv.checkbox(info_column)
        self.clear_cache_checkbox.set_text("Real-time values")

        # --- BOTTOM FLEX BOX: GRAPH ---

        self.canvas_width = main_content.get_width()
        self.canvas_height = 100

        canvas_column = lv.obj(main_content)
        canvas_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        canvas_column.set_style_pad_all(0, 0)
        canvas_column.set_size(self.canvas_width, self.canvas_height)

        self.canvas = lv.canvas(canvas_column)
        self.canvas.set_size(self.canvas_width, self.canvas_height)
        buffer = bytearray(self.canvas_width * self.canvas_height * 4)
        self.canvas.set_buffer(
            buffer, self.canvas_width, self.canvas_height, lv.COLOR_FORMAT.NATIVE
        )

        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)
        self.setContentView(main_content)

    def draw_line(self, color, x1, y1, x2, y2):
        dsc = lv.draw_line_dsc_t()
        lv.draw_line_dsc_t.init(dsc)
        dsc.color = color
        dsc.width = 2
        dsc.round_end = 1
        dsc.round_start = 1
        dsc.p1 = lv.point_precise_t()
        dsc.p1.x = x1
        dsc.p1.y = y1
        dsc.p2 = lv.point_precise_t()
        dsc.p2.x = x2
        dsc.p2.y = y2
        lv.draw_line(self.layer, dsc)
        self.canvas.finish_layer(self.layer)

    def draw_graph(self):
        self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)
        self.canvas.clean()

        w = self.canvas_width
        h = self.canvas_height

        if len(self.history_v) < 2:
            return

        v_range = max(MAX_VOLTAGE - MIN_VOLTAGE, 0.01)

        for i in range(1, len(self.history_v)):
            x1 = int((i - 1) * w / HISTORY_LEN)
            x2 = int(i * w / HISTORY_LEN)

            yv1 = h - int((self.history_v[i - 1] - MIN_VOLTAGE) / v_range * h)
            yv2 = h - int((self.history_v[i] - MIN_VOLTAGE) / v_range * h)

            yp1 = h - int(self.history_p[i - 1] / 100 * h)
            yp2 = h - int(self.history_p[i] / 100 * h)

            self.draw_line(DARKPINK, x1, yv1, x2, yv2)
            self.draw_line(BLACK, x1, yp1, x2, yp2)

    def onResume(self, screen):
        super().onResume(screen)

        def update(timer):
            # --- DATE+TIME ---
            now = mpos.time.localtime()
            year, month, day = now[0], now[1], now[2]
            hour, minute, second = now[3], now[4], now[5]
            self.lbl_datetime.set_text(
                f"{year}-{month:02}-{day:02} {hour:02}:{minute:02}:{second:02}"
            )

            # --- BATTERY VALUES ---

            if self.clear_cache_checkbox.get_state() & lv.STATE.CHECKED:
                # Get "real-time" values by clearing the cache before reading
                BatteryManager.clear_cache()

            voltage = BatteryManager.read_battery_voltage()
            percent = BatteryManager.get_battery_percentage()

            if percent > 80:
                symbol = lv.SYMBOL.BATTERY_FULL
            elif percent > 60:
                symbol = lv.SYMBOL.BATTERY_3
            elif percent > 40:
                symbol = lv.SYMBOL.BATTERY_2
            elif percent > 20:
                symbol = lv.SYMBOL.BATTERY_1
            else:
                symbol = lv.SYMBOL.BATTERY_EMPTY

            self.lbl_battery.set_text(f"{symbol} {voltage:.2f}V {percent:.0f}%")
            if percent >= 30:
                bg_color = lv.PALETTE.GREEN
            else:
                bg_color = lv.PALETTE.RED
            self.lbl_battery.set_style_text_color(lv.palette_main(bg_color), 0)

            self.lbl_battery_raw.set_text(f"Raw ADC: {BatteryManager.read_raw_adc()}")

            # --- HISTORY GRAPH ---
            self.history_v.append(voltage)
            self.history_p.append(percent)

            if len(self.history_v) > HISTORY_LEN:
                self.history_v.pop(0)
                self.history_p.pop(0)

            self.draw_graph()

        self.refresh_timer = lv.timer_create(update, 1000, None)

    def onPause(self, screen):
        super().onPause(screen)
        if self.refresh_timer:
            self.refresh_timer.delete()
            self.refresh_timer = None
