from mpos import Activity

"""
Look at https://open-meteo.com/en/docs , then design an application that would display current time and weather, and summary of forecast ("no change expected for 2 days" or maybe "rain in 5 hours"), with a way to access detailed forecast.
"""

import time
import os

try:
    import lvgl as lv
except ImportError:
    pass

from mpos import Activity, MposKeyboard, DownloadManager

import ujson
import utime
import usocket as socket
import ujson

# -----------------------------
# WEATHER DATA MODEL
# -----------------------------

class WData:
    WMO_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        56: "Freezing drizzle",
        57: "Freezing drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        66: "Freezing rain",
        67: "Freezing rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Rain showers",
        81: "Rain showers",
        82: "Heavy rain showers",
        85: "Snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm + hail",
        99: "Thunderstorm + hail",
    }

    def init(self):
        pass

    def code_to_text(self, code):
        return self.WMO_CODES.get(int(code), "Unknown")

    def get(self, v, cw, ind):
        if ind == None:
            return cw[v]
        else:
            return cw[v][ind]

    def full(self):
        return f"{self.code}\nTemp {self.temp:.1f} dew {self.dew:.1f} pres {self.pres:1f}\n" \
               f"Precip {self.precip}\nWind {self.wind} gust {self.gust}"
        
    def short(self):
        r = f"{self.code} {self.temp:.1f}°C"
        if self.dew + 3 > self.temp:
            r += f" dew {self.dew:.1f}°C"
        if self.gust > self.wind + 5:
            r += f" {self.gust:.0f} g"
        elif self.wind > 10:
            r += f" {self.wind:.0f} w"
        # FIXME: add precip
        return r

    def similar(self, prev):
        if self.code != prev.code:
            return False
        if abs(self.temp - prev.temp) > 3:
            return False
        if abs(self.wind - prev.wind) > 10:
            return False
        if abs(self.gust - prev.gust) > 10:
            return False
        return True

    def summarize(self):
        return self.ftime() + self.short()
    
class Hourly(WData):
    def init(self, cw, ind):
        super().init()
        self.time = None
        self.temp   = self.get("temperature_2m", cw, ind)
        self.dew    = self.get("dewpoint_2m", cw, ind)
        self.pres   = self.get("pressure_msl", cw, ind)
        self.precip = self.get("precipitation", cw, ind)
        self.wind   = self.get("wind_speed_10m", cw, ind)
        self.gust   = self.get("wind_gusts_10m", cw, ind)
        self.raw_code = self.get("weather_code", cw, ind)
        self.code = self.code_to_text(self.raw_code)

    def ftime(self):
        if self.time:
            return self.time[11:13] + "h "
        return ""

class Daily(WData):
    def init(self, cw, ind):
        super().init()
        self.temp       = self.get("temperature_2m_max", cw, ind)
        self.temp_min   = self.get("temperature_2m_min", cw, ind)
        self.dew        = self.get("dewpoint_2m_max", cw, ind)
        self.dew_min    = self.get("dewpoint_2m_min", cw, ind)
        self.pres       = None
        self.precip     = self.get("precipitation_sum", cw, ind)
        self.wind       = self.get("wind_speed_10m_max", cw, ind)
        self.gust       = self.get("wind_gusts_10m_max", cw, ind)
        self.raw_code   = self.get("weather_code", cw, ind)
        self.code = self.code_to_text(self.raw_code)

    def ftime(self):
        return self.time[8:10] + ". "

class Weather:
    name = "Prague"
    # LKPR airport
    lat = 50 + 6/60.
    lon = 14 + 15/60.
    
    def __init__(self):
        self.now = None
        self.hourly = []
        self.daily = []
        self.summary = "(no weather)"

    def fetch(self):
        self.summary = "...fetching..."

        # See https://open-meteo.com/en/docs?forecast_days=1&current=relative_humidity_2m
        
        host = "api.open-meteo.com"
        path = (
            "/v1/forecast?"
            "latitude={}&longitude={}"
            "&current=temperature_2m,dewpoint_2m,pressure_msl,precipitation,weather_code,wind_speed_10m,wind_gusts_10m"
            "&forecast_hours=8"
            "&hourly=temperature_2m,dewpoint_2m,pressure_msl,precipitation,weather_code,wind_speed_10m,wind_gusts_10m"
	    "&forecast_days=10"
	    "&daily=temperature_2m_max,temperature_2m_min,dewpoint_2m_min,dewpoint_2m_max,pressure_msl_min,pressure_msl_max,precipitation_sum,weather_code,wind_speed_10m_max,wind_gusts_10m_max"
            "&timezone=auto"
        ).format(self.lat, self.lon)

        print("Weather fetch: ", path)
        data = DownloadManager.download_url("https://"+host+path)
        if not data:
            self.summary = "Download error"
            return
        
        #print("Have result:", body.decode())

        # Parse JSON
        data = ujson.loads(data)

        # ---- Extract data ----
        print("\n\n")

        s = ""

        print("---- ")
        cw = data["current"]
        self.now = Hourly()
        self.now.init(cw, None)
        prev = self.now
        t = self.now.summarize()
        s += t + "\n"
        print(t)

        self.hourly = []
        d = data["hourly"]
        times = d["time"]
        #print(d)

        print("---- ")
        for i in range(len(times)):
            h = Hourly()
            h.init(d, i)
            h.time = times[i]
            self.hourly.append(h)
            if not h.similar(prev):
                t = h.summarize()
                s += t + "\n"
                print(t)
                prev = h

        self.daily = []
        d = data["daily"]
        times = d["time"]
        #print(d)

        print("---- ")
        for i in range(len(times)):
            h = Daily()
            h.init(d, i)
            h.time = times[i]
            self.daily.append(h)
            if i == 0:
                prev = h
            elif not h.similar(prev):
                t = h.summarize()
                s += t + "\n"
                print(t)
                prev = h


        self.summary = s

    def summarize_future():
        now = utime.time()

        # Rain detection in next 24h
        for h in weather.hourly[:24]:
            if h["precip"] >= 1.0:
                return "Rain soon"

        # Temperature trend
        if len(weather.hourly) > 24:
            t0 = weather.hourly[0]["temp"]
            t24 = weather.hourly[24]["temp"]
            if abs(t24 - t0) < 2:
                return "No change expected"
            if t24 > t0:
                return "Getting warmer"
            else:
                return "Getting cooler"

        return "Stable weather"
            
        
weather = Weather()
        
# ------------------------------------------------------------
# Main activity
# ------------------------------------------------------------

class Main(Activity):
    def __init__(self):
        self.last_hour = 0
        super().__init__()

     # --------------------

    def onCreate(self):
        self.screen = lv.obj()
        #self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        scr_main = self.screen

        # ---- MAIN SCREEN ----

        label_weather = lv.label(scr_main)
        label_weather.set_text(f"{weather.name} ({weather.lat}, {weather.lon})")
        label_weather.align(lv.ALIGN.TOP_LEFT, 10, 24)
        label_weather.set_style_text_font(lv.font_montserrat_14, 0)
        self.label_weather = label_weather

        btn_hourly = lv.button(scr_main)
        btn_hourly.align(lv.ALIGN.TOP_RIGHT, -5, 24)
        lv.label(btn_hourly).set_text("Reload")
        btn_hourly.add_event_cb(lambda x: self.do_load(), lv.EVENT.CLICKED, None)
        
        label_time = lv.label(scr_main)
        label_time.set_text("(time)")
        label_time.align_to(btn_hourly, lv.ALIGN.TOP_LEFT, -85, -10)
        label_time.set_style_text_font(lv.font_montserrat_24, 0)
        self.label_time = label_time

        label_summary = lv.label(scr_main)
        label_summary.set_text("(weather)")
        #label_summary.set_long_mode(lv.label.LONG.WRAP)
        #label_summary.set_width(300)
        label_summary.align_to(label_weather, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
        label_summary.set_style_text_font(lv.font_montserrat_24, 0)
        self.label_summary = label_summary


        if False:
            btn_daily = lv.button(scr_main)
            btn_daily.set_size(100, 40)
            btn_daily.align(lv.ALIGN.BOTTOM_RIGHT, -10, -10)
            lv.label(btn_daily).set_text("Daily")


        self.setContentView(self.screen)

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 15000, None)
        self.tick(0)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None

    # --------------------

    def tick(self, t):
        now = time.localtime()
        y, m, d = now[0], now[1], now[2]
        hh, mm, ss = now[3], now[4], now[5]

        if hh != self.last_hour:
            self.last_hour = hh
            self.do_load()

        self.label_time.set_text("%02d:%02d" % (hh, mm))
        self.label_summary.set_text(weather.summary)

    def do_load(self):
        self.label_summary.set_text("Requesting...")
        weather.fetch()
        
    # --------------------

    def code():
        # -----------------------------
        # LVGL UI
        # -----------------------------

        scr_main = lv.obj()
        scr_hourly = lv.obj()
        scr_daily = lv.obj()


        # ---- HOURLY SCREEN ----

        hourly_list = lv.list(scr_hourly)
        hourly_list.set_size(320, 200)
        hourly_list.align(lv.ALIGN.TOP_MID, 0, 10)

        btn_back1 = lv.button(scr_hourly)
        btn_back1.set_size(80, 30)
        btn_back1.align(lv.ALIGN.BOTTOM_MID, 0, -5)
        lv.label(btn_back1).set_text("Back")

        # ---- DAILY SCREEN ----

        daily_list = lv.list(scr_daily)
        daily_list.set_size(320, 200)
        daily_list.align(lv.ALIGN.TOP_MID, 0, 10)

        btn_back2 = lv.button(scr_daily)
        btn_back2.set_size(80, 30)
        btn_back2.align(lv.ALIGN.BOTTOM_MID, 0, -5)
        lv.label(btn_back2).set_text("Back")

    def foo():
        btn_hourly.add_event_cb(go_hourly, lv.EVENT.CLICKED, None)
        btn_daily.add_event_cb(go_daily, lv.EVENT.CLICKED, None)
        btn_back1.add_event_cb(go_back, lv.EVENT.CLICKED, None)
        btn_back2.add_event_cb(go_back, lv.EVENT.CLICKED, None)

        # -----------------------------
        # STARTUP
        # -----------------------------

        def go_hourly(e):
            populate_hourly()
            lv.scr_load(scr_hourly)

        def go_daily(e):
            populate_daily()
            lv.scr_load(scr_daily)

        def go_back(e):
            lv.scr_load(scr_main)
        
        def update_ui():
            if weather.current_temp is not None:
                text = "%s  %.1f C" % (
                    weather_code_to_text(weather.current_code),
                    weather.current_temp
                )
                label_weather.set_text(text)

            label_summary.set_text(weather.summary)

        def populate_hourly():
            hourly_list.clean()
            for h in weather.hourly[:24]:
                line = "%s  %.1fC  %.1fmm" % (
                    h["time"][11:16],
                    h["temp"],
                    h["precip"]
                )
                hourly_list.add_text(line)

        def populate_daily():
            daily_list.clean()
            for d in weather.daily:
                line = "%s  %.1f/%.1f" % (
                    d["date"],
                    d["high"],
                    d["low"]
                )
                daily_list.add_text(line)
