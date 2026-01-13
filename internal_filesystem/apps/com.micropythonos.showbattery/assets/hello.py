"""
8:44 4.15V
8:46 4.13V

import time
v = mpos.battery_voltage.read_battery_voltage()
percent = mpos.battery_voltage.get_battery_percentage()
text = f"{time.localtime()}: {v}V is {percent}%"
text

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

"""

import lvgl as lv
import time

from mpos import battery_voltage, Activity

class Hello(Activity):

    refresh_timer = None
    
    # Widgets:
    raw_label = None

    def onCreate(self):
        s = lv.obj()
        self.raw_label = lv.label(s)
        self.raw_label.set_text("starting...")
        self.raw_label.center()
        self.setContentView(s)

    def onResume(self, screen):
        super().onResume(screen)

        def update_bat(timer):
            #global l
            r = battery_voltage.read_raw_adc()
            v = battery_voltage.read_battery_voltage()
            percent = battery_voltage.get_battery_percentage()
            text = f"{time.localtime()}\n{r}\n{v}V\n{percent}%"
            #text = f"{time.localtime()}: {r}"
            print(text)
            self.update_ui_threadsafe_if_foreground(self.raw_label.set_text, text)

        self.refresh_timer = lv.timer_create(update_bat,1000,None) #.set_repeat_count(10)

    def onPause(self, screen):
        super().onPause(screen)
        if self.refresh_timer:
            self.refresh_timer.delete()
