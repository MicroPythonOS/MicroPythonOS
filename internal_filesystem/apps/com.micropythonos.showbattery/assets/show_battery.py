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

HISTORY_LEN = 60

DARKPINK = lv.color_hex(0xEC048C)
BLACK = lv.color_hex(0x000000)

class ShowBattery(Activity):

    refresh_timer = None

    # Widgets
    lbl_time = None
    lbl_sec = None
    lbl_text = None

    bat_outline = None
    bat_fill = None

    clear_cache_checkbox = None  # Add reference to checkbox

    history_v = []
    history_p = []

    def onCreate(self):
        scr = lv.obj()

        # --- TIME ---
        self.lbl_time = lv.label(scr)
        self.lbl_time.set_style_text_font(lv.font_montserrat_40, 0)
        self.lbl_time.align(lv.ALIGN.TOP_LEFT, 5, 5)

        self.lbl_sec = lv.label(scr)
        self.lbl_sec.set_style_text_font(lv.font_montserrat_24, 0)
        self.lbl_sec.align_to(self.lbl_time, lv.ALIGN.OUT_RIGHT_BOTTOM, 24, -4)

        # --- CHECKBOX ---
        self.clear_cache_checkbox = lv.checkbox(scr)
        self.clear_cache_checkbox.set_text("Real-time values")
        self.clear_cache_checkbox.align(lv.ALIGN.TOP_LEFT, 5, 50)

        self.lbl_text = lv.label(scr)
        self.lbl_text.set_style_text_font(lv.font_montserrat_16, 0)
        self.lbl_text.align(lv.ALIGN.TOP_LEFT, 5, 80)

        # --- BATTERY ICON ---
        self.bat_outline = lv.obj(scr)
        self.bat_size = 225
        self.bat_outline.set_size(80, self.bat_size)
        self.bat_outline.align(lv.ALIGN.TOP_RIGHT, -10, 10)
        self.bat_outline.set_style_border_width(2, 0)
        self.bat_outline.set_style_radius(4, 0)

        self.bat_fill = lv.obj(self.bat_outline)
        self.bat_fill.align(lv.ALIGN.BOTTOM_MID, 0, -2)
        self.bat_fill.set_width(52)
        self.bat_fill.set_style_radius(2, 0)

        # --- CANVAS ---
        self.canvas = lv.canvas(scr)
        self.canvas.set_size(220, 100)
        self.canvas.align(lv.ALIGN.BOTTOM_LEFT, 5, -5)
        self.canvas.set_style_border_width(1, 0)
        self.canvas.set_style_bg_color(lv.color_white(), lv.PART.MAIN)
        buffer = bytearray(220 * 100 * 4)
        self.canvas.set_buffer(buffer, 220, 100, lv.COLOR_FORMAT.NATIVE)
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)

        self.setContentView(scr)

    def draw_line(self, color, x1, y1, x2, y2):
        dsc = lv.draw_line_dsc_t()
        lv.draw_line_dsc_t.init(dsc)
        dsc.color = color
        dsc.width = 4
        dsc.round_end = 1
        dsc.round_start = 1
        dsc.p1 = lv.point_precise_t()
        dsc.p1.x = x1
        dsc.p1.y = y1
        dsc.p2 = lv.point_precise_t()
        dsc.p2.x = x2
        dsc.p2.y = y2
        lv.draw_line(self.layer,dsc)
        self.canvas.finish_layer(self.layer)

    def onResume(self, screen):
        super().onResume(screen)

        def update(timer):
            now = mpos.time.localtime()

            hour, minute, second = now[3], now[4], now[5]
            date = f"{now[0]}-{now[1]:02}-{now[2]:02}"

            if self.clear_cache_checkbox.get_state() & lv.STATE.CHECKED:
                # Get "real-time" values by clearing the cache before reading
                BatteryManager.clear_cache()

            voltage = BatteryManager.read_battery_voltage()
            percent = BatteryManager.get_battery_percentage()

            # --- TIME ---
            self.lbl_time.set_text(f"{hour:02}:{minute:02}")
            self.lbl_sec.set_text(f":{second:02}")

            # --- BATTERY VALUES ---
            date += f"\n{voltage:.2f}V {percent:.0f}%"
            date += f"\nRaw ADC: {BatteryManager.read_raw_adc()}"
            self.lbl_text.set_text(date)

            # --- BATTERY ICON ---
            fill_h = int((percent / 100) * (self.bat_size * 0.9))
            self.bat_fill.set_height(fill_h)

            if percent >= 30:
                self.bat_fill.set_style_bg_color(lv.palette_main(lv.PALETTE.GREEN), 0)
            else:
                self.bat_fill.set_style_bg_color(lv.palette_main(lv.PALETTE.RED), 0)

            # --- HISTORY ---
            self.history_v.append(voltage)
            self.history_p.append(percent)

            if len(self.history_v) > HISTORY_LEN:
                self.history_v.pop(0)
                self.history_p.pop(0)

            self.draw_graph()

        self.refresh_timer = lv.timer_create(update, 1000, None)

    def draw_graph(self):
        self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)
        self.canvas.clean()

        w = self.canvas.get_width()
        h = self.canvas.get_height()

        if len(self.history_v) < 2:
            return

        v_min = 3.3
        v_max = 4.2
        v_range = max(v_max - v_min, 0.01)

        for i in range(1, len(self.history_v)):
            x1 = int((i - 1) * w / HISTORY_LEN)
            x2 = int(i * w / HISTORY_LEN)

            yv1 = h - int((self.history_v[i - 1] - v_min) / v_range * h)
            yv2 = h - int((self.history_v[i] - v_min) / v_range * h)

            yp1 = h - int(self.history_p[i - 1] / 100 * h)
            yp2 = h - int(self.history_p[i] / 100 * h)

            self.draw_line(DARKPINK, x1, yv1, x2, yv2)
            self.draw_line(BLACK, x1, yp1, x2, yp2)

    def onPause(self, screen):
        super().onPause(screen)
        if self.refresh_timer:
            self.refresh_timer.delete()
            self.refresh_timer = None
