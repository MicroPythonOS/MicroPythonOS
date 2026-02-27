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

from mpos import Activity, MposKeyboard

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

    def code_to_text(self, code):
        return self.WMO_CODES.get(int(code), "Unknown")

class Hourly(WData):
    def __init__(self, cw):
        self.temp = cw["temperature_2m"]
        self.wind = cw["windspeed"]
        self.code = self.code_to_text(cw["weather_code"])

    def summarize(self):
        return f"{self.code}\nTemp {self.temp}\nWind {self.wind}"

class Weather:
    name = "Prague"
    lat = 50.08
    lon = 14.44
    
    def __init__(self):
        self.now = None
        self.hourly = []
        self.daily = []
        self.summary = "(no weather)"

    def fetch(self):
        self.summary = "...fetching..."

        # See https://open-meteo.com/en/docs?forecast_days=1&current=relative_humidity_2m
        
        host = "api.open-meteo.com"
        port = 80  # HTTP only
        path = (
            "/v1/forecast?"
            "latitude={}&longitude={}"
            "&current=temperature_2m,dewpoint_2m,pressure_msl,precipitation,weather_code,windspeed"
            "&timezone=auto"
        ).format(self.lat, self.lon)

        print("Weather fetch: ", path)

        # Resolve DNS
        addr = socket.getaddrinfo(host, port, socket.AF_INET)[0][-1]
        print("DNS", addr)

        s = socket.socket()
        s.connect(addr)

        # Send HTTP request
        request = (
            "GET {} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Connection: close\r\n\r\n"
        ).format(path, host)

        s.send(request.encode())

        # ---- Read response ----
        # Skip HTTP headers
        buffer = b""
        while True:
            chunk = s.recv(256)
            if not chunk:
                raise Exception("No response")
            buffer += chunk
            header_end = buffer.find(b"\r\n\r\n")
            if header_end != -1:
                body = buffer[header_end + 4:]
                break


        # Read remaining body
        while True:
            chunk = s.recv(512)
            if not chunk:
                break
            body += chunk

        s.close()

        # Strip non-json parts
        body = body[5:]
        body = body[:-7]

        print("Have result:", body.decode())

        # Parse JSON
        data = ujson.loads(body)

        # ---- Extract data ----
        cw = data["current"]
        self.now = Hourly(cw)
        self.summary = self.now.summarize()
        
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

        label_time = lv.label(scr_main)
        label_time.set_text("(time)")
        label_time.align(lv.ALIGN.TOP_LEFT, 10, 40)
        label_time.set_style_text_font(lv.font_montserrat_24, 0)
        self.label_time = label_time

        label_weather = lv.label(scr_main)
        label_weather.set_text(f"Weather for {weather.name} ({weather.lat}, {weather.lon})")
        label_weather.align_to(label_time, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 10)
        label_weather.set_style_text_font(lv.font_montserrat_14, 0)
        self.label_weather = label_weather

        label_summary = lv.label(scr_main)
        label_summary.set_text("(weather)")
        #label_summary.set_long_mode(lv.label.LONG.WRAP)
        label_summary.set_width(300)
        label_summary.align_to(label_weather, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
        label_summary.set_style_text_font(lv.font_montserrat_24, 0)
        self.label_summary = label_summary

        btn_hourly = lv.button(scr_main)
        btn_hourly.set_size(100, 40)
        btn_hourly.align(lv.ALIGN.BOTTOM_LEFT, 10, -10)
        lv.label(btn_hourly).set_text("Reload")

        btn_hourly.add_event_cb(lambda x: self.do_load(), lv.EVENT.CLICKED, None)

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
        
