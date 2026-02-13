from mpos import Activity

"""

Create simple calendar application. On main screen, it should have
current time, date, and month overview. Current date and dates with
events should be highlighted. There should be list of upcoming events.

When date is clicked, dialog with adding event for that date should be
displayed. Multi-day events should be supported.

Data should be read/written to emacs org compatible text file.


"""

import time
import os

try:
    import lvgl as lv
except ImportError:
    pass

from mpos import Activity, MposKeyboard


ORG_FILE = f"data/calendar.org"   # adjust for your device
MAX_UPCOMING = 8


# ------------------------------------------------------------
# Small date helpers (no datetime module assumed)
# ------------------------------------------------------------

def is_leap_year(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    if m == 2:
        return 29 if is_leap_year(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def ymd_to_int(y, m, d):
    return y * 10000 + m * 100 + d


def int_to_ymd(v):
    y = v // 10000
    m = (v // 100) % 100
    d = v % 100
    return y, m, d


def weekday_name(idx):
    # MicroPython localtime(): 0=Mon..6=Sun typically
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if 0 <= idx < 7:
        return names[idx]
    return "???"


def first_weekday_of_month(y, m):
    # brute-force using time.mktime if available
    # Some ports support it, some don't.
    # If it fails, we fallback to "Monday".
    try:
        # localtime tuple: (y,m,d,h,mi,s,wd,yd)
        t = time.mktime((y, m, 1, 0, 0, 0, 0, 0))
        wd = time.localtime(t)[6]
        return wd
    except Exception:
        return 0


# ------------------------------------------------------------
# Org event model + parser/writer
# ------------------------------------------------------------

class Event:
    def __init__(self, title, start_ymd, end_ymd, start_time=None, end_time=None):
        self.title = title
        self.start = start_ymd  # int yyyymmdd
        self.end = end_ymd      # int yyyymmdd
        self.start_time = start_time  # "HH:MM" or None
        self.end_time = end_time      # "HH:MM" or None

    def is_multi_day(self):
        return self.end != self.start

    def occurs_on(self, ymd):
        return self.start <= ymd <= self.end

    def start_key(self):
        return self.start


class OrgCalendarStore:
    def __init__(self, path):
        self.path = path

    def load(self):
        if not self._exists(self.path):
            return []

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception:
            # fallback without encoding kw if unsupported
            with open(self.path, "r") as f:
                lines = f.read().splitlines()

        events = []
        current_title = None
        # FIXME this likely does not work

        for line in lines:
            line = line.strip()

            if line.startswith("** "):
                current_title = line[3:].strip()
                continue

            if not line.startswith("<"):
                continue

            ev = self._parse_timestamp_line(current_title, line)
            if ev:
                events.append(ev)

        events.sort(key=lambda e: e.start_key())
        return events

    def save_append(self, event):
        # Create file if missing
        if not self._exists(self.path):
            self._write_text("* Events\n")

        # Append event
        out = []
        out.append("** " + event.title)

        if event.start == event.end:
            y, m, d = int_to_ymd(event.start)
            wd = weekday_name(self._weekday_for_ymd(y, m, d))
            if event.start_time and event.end_time:
                out.append("<%04d-%02d-%02d %s %s-%s>" % (
                    y, m, d, wd, event.start_time, event.end_time
                ))
            else:
                out.append("<%04d-%02d-%02d %s>" % (y, m, d, wd))
        else:
            y1, m1, d1 = int_to_ymd(event.start)
            y2, m2, d2 = int_to_ymd(event.end)
            wd1 = weekday_name(self._weekday_for_ymd(y1, m1, d1))
            wd2 = weekday_name(self._weekday_for_ymd(y2, m2, d2))
            out.append("<%04d-%02d-%02d %s>--<%04d-%02d-%02d %s>" % (
                y1, m1, d1, wd1,
                y2, m2, d2, wd2
            ))

        out.append("")  # blank line
        self._append_text("\n".join(out) + "\n")

    # --------------------

    def _parse_timestamp_line(self, title, line):
        if not title:
            return None

        # Single-day: <2026-02-05 Thu>
        # With time:  <2026-02-05 Thu 10:00-11:00>
        # Range:      <2026-02-10 Tue>--<2026-02-14 Sat>

        if "--<" in line:
            a, b = line.split("--", 1)
            s = self._parse_one_timestamp(a)
            e = self._parse_one_timestamp(b)
            if not s or not e:
                return None
            return Event(title, s["ymd"], e["ymd"], None, None)

        s = self._parse_one_timestamp(line)
        if not s:
            return None

        return Event(title, s["ymd"], s["ymd"], s.get("start_time"), s.get("end_time"))

    def _parse_one_timestamp(self, token):
        token = token.strip()
        if not (token.startswith("<") and token.endswith(">")):
            return None

        inner = token[1:-1].strip()
        parts = inner.split()

        # Expect YYYY-MM-DD ...
        if len(parts) < 2:
            return None

        date_s = parts[0]
        try:
            y = int(date_s[0:4])
            m = int(date_s[5:7])
            d = int(date_s[8:10])
        except Exception:
            return None

        ymd = ymd_to_int(y, m, d)

        # Optional time part like 10:00-11:00
        start_time = None
        end_time = None
        if len(parts) >= 3 and "-" in parts[2]:
            t = parts[2]
            if len(t) == 11 and t[2] == ":" and t[5] == "-" and t[8] == ":":
                start_time = t[0:5]
                end_time = t[6:11]

        return {
            "ymd": ymd,
            "start_time": start_time,
            "end_time": end_time
        }

    def _exists(self, path):
        try:
            os.stat(path)
            return True
        except Exception:
            return False

    def _append_text(self, s):
        with open(self.path, "a") as f:
            f.write(s)

    def _write_text(self, s):
        with open(self.path, "w") as f:
            f.write(s)

    def _weekday_for_ymd(self, y, m, d):
        try:
            t = time.mktime((y, m, d, 0, 0, 0, 0, 0))
            return time.localtime(t)[6]
        except Exception:
            return 0


# ------------------------------------------------------------
# Calendar Activity
# ------------------------------------------------------------

class Main(Activity):

    def __init__(self):
        super().__init__()

        self.store = OrgCalendarStore(ORG_FILE)
        self.events = []

        self.timer = None

        # UI
        self.screen = None
        self.lbl_time = None
        self.lbl_date = None
        self.lbl_month = None

        self.grid = None
        self.day_buttons = []

        self.upcoming_list = None

        # Current month shown
        self.cur_y = 0
        self.cur_m = 0
        self.today_ymd = 0

    # --------------------

    def onCreate(self):
        self.screen = lv.obj()
        #self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Top labels
        self.lbl_time = lv.label(self.screen)
        self.lbl_time.set_style_text_font(lv.font_montserrat_20, 0)
        self.lbl_time.align(lv.ALIGN.TOP_LEFT, 6, 4)

        self.lbl_date = lv.label(self.screen)
        self.lbl_date.align(lv.ALIGN.TOP_LEFT, 6, 40)

        self.lbl_month = lv.label(self.screen)
        self.lbl_month.align(lv.ALIGN.TOP_RIGHT, -6, 10)

        # Upcoming events list
        self.upcoming_list = lv.list(self.screen)
        self.upcoming_list.set_size(lv.pct(90), 60)
        self.upcoming_list.align_to(self.lbl_date, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 10)

        # Month grid container
        self.grid = lv.obj(self.screen)
        self.grid.set_size(lv.pct(90), 60)
        self.grid.set_style_border_width(1, 0)
        self.grid.set_style_pad_all(0, 0)
        self.grid.set_style_radius(6, 0)
        self.grid.align_to(self.upcoming_list, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 10)

        self.setContentView(self.screen)

        self.reload_data()
        print("My events == ", self.events)
        self.build_month_view()
        self.refresh_upcoming()

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 30000, None)
        self.tick(0)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None

    # --------------------

    def reload_data(self):
        print("Loading...")
        self.events = self.store.load()
        # FIXME
        #self.events = [ Event("Test event", 20260207, 20260208) ]

    def tick(self, t):
        now = time.localtime()
        y, m, d = now[0], now[1], now[2]
        hh, mm, ss = now[3], now[4], now[5]
        wd = weekday_name(now[6])

        self.today_ymd = ymd_to_int(y, m, d)

        self.lbl_time.set_text("%02d:%02d" % (hh, mm))
        self.lbl_date.set_text("%04d-%02d-%02d %s" % (y, m, d, wd))

        # Month label
        self.lbl_month.set_text("%04d-%02d" % (self.cur_y, self.cur_m))

        # Re-highlight today (cheap)
        self.update_day_highlights()

    # --------------------

    def build_month_view(self):
        now = time.localtime()
        self.cur_y, self.cur_m = now[0], now[1]

        # Determine size
        d = lv.display_get_default()
        w = d.get_horizontal_resolution()

        cell = w // 8
        grid_w = cell * 7 + 8
        grid_h = cell * 6 + 8

        self.grid.set_size(grid_w, grid_h)

        # Clear old buttons
        for b in self.day_buttons:
            b.delete()
        self.day_buttons = []
        self.day_of_btn = {}

        first_wd = first_weekday_of_month(self.cur_y, self.cur_m)  # 0=Mon
        dim = days_in_month(self.cur_y, self.cur_m)

        # LVGL grid is easiest as absolute positioning here
        for day in range(1, dim + 1):
            idx = (first_wd + (day - 1))
            row = idx // 7
            col = idx % 7

            btn = lv.button(self.grid)
            btn.set_size(cell - 2, cell - 2)
            btn.set_pos(4 + col * cell, 4 + row * cell)
            btn.add_event_cb(lambda e, dd=day: self.on_day_clicked(dd), lv.EVENT.CLICKED, None)

            lbl = lv.label(btn)
            lbl.set_text(str(day))
            lbl.center()

            self.day_buttons.append(btn)
            self.day_of_btn[btn] = day

        self.update_day_highlights()

    def update_day_highlights(self):
        for btn in self.day_buttons:
            day = self.day_of_btn.get(btn, None)
            if day is None:
                continue

            ymd = ymd_to_int(self.cur_y, self.cur_m, day)

            has_event = self.day_has_event(ymd)
            is_today = (ymd == self.today_ymd)
            #print(ymd, has_event, is_today)

            if is_today:
                btn.set_style_bg_color(lv.palette_main(lv.PALETTE.BLUE), 0)
            elif has_event:
                btn.set_style_bg_color(lv.palette_main(lv.PALETTE.GREEN), 0)
            else:
                btn.set_style_bg_color(lv.palette_main(lv.PALETTE.GREY), 0)

    def day_has_event(self, ymd):
        for e in self.events:
            if e.occurs_on(ymd):
                return True
        return False

    # --------------------

    def refresh_upcoming(self):
        self.upcoming_list.clean()

        now = time.localtime()
        today = ymd_to_int(now[0], now[1], now[2])

        upcoming = []
        for e in self.events:
            if e.end >= today:
                upcoming.append(e)

        upcoming.sort(key=lambda e: e.start)

        for e in upcoming[:MAX_UPCOMING]:
            y1, m1, d1 = int_to_ymd(e.start)
            y2, m2, d2 = int_to_ymd(e.end)

            if e.start == e.end:
                date_s = "%04d-%02d-%02d" % (y1, m1, d1)
            else:
                date_s = "%04d-%02d-%02d..%04d-%02d-%02d" % (y1, m1, d1, y2, m2, d2)

            txt = date_s + " " + e.title
            self.upcoming_list.add_text(txt)

        self.upcoming_list.add_text("that's all folks")

    # --------------------

    def on_day_clicked(self, day):
        print("Day clicked")
        ymd = ymd_to_int(self.cur_y, self.cur_m, day)
        self.open_add_dialog(ymd)

    def open_add_dialog(self, ymd):
        y, m, d = int_to_ymd(ymd)

        dlg = lv.obj(self.screen)
        dlg.set_size(lv.pct(100), 480)
        dlg.center()
        dlg.set_style_bg_color(lv.color_hex(0x8f8f8f), 0)
        dlg.set_style_border_width(2, 0)
        dlg.set_style_radius(10, 0)

        title = lv.label(dlg)
        title.set_text("Add event")
        title.align(lv.ALIGN.TOP_MID, 0, 8)

        date_lbl = lv.label(dlg)
        date_lbl.set_text("%04d-%02d-%02d" % (y, m, d))
        date_lbl.align_to(title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        # Title input
        ti = lv.textarea(dlg)
        ti.set_size(220, 32)
        ti.align_to(date_lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        ti.set_placeholder_text("Title")
        keyboard = MposKeyboard(dlg)
        keyboard.set_textarea(ti)
        #keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # End date offset (days)
        end_lbl = lv.label(dlg)
        end_lbl.set_text("Duration days:")
        end_lbl.align_to(ti, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        dd = lv.dropdown(dlg)
        dd.set_options("1\n2\n3\n4\n5\n6\n7\n10\n14\n21\n30")
        dd.set_selected(0)
        dd.set_size(70, 32)
        dd.align_to(end_lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

        # Buttons
        btn_cancel = lv.button(dlg)
        btn_cancel.set_size(90, 30)
        btn_cancel.align(lv.ALIGN.TOP_LEFT, 12, 10)
        btn_cancel.add_event_cb(lambda e: dlg.delete(), lv.EVENT.CLICKED, None)
        lc = lv.label(btn_cancel)
        lc.set_text("Cancel")
        lc.center()

        btn_add = lv.button(dlg)
        btn_add.set_size(90, 30)
        btn_add.align(lv.ALIGN.TOP_RIGHT, -12, 10)

        def do_add(e):
            title_s = ti.get_text()
            if not title_s or title_s.strip() == "":
                return

            dur_s = 1 # dd.get_selected_str() FIXME
            try:
                dur = int(dur_s)
            except Exception:
                dur = 1

            end_ymd = self.add_days(ymd, dur - 1)

            ev = Event(title_s.strip(), ymd, end_ymd, None, None)
            self.events.append(ev)
            self.store.save_append(ev) # FIXME

            # Reload + refresh UI
            # FIXME: common code?
            #self.reload_data()
            self.update_day_highlights()
            self.refresh_upcoming()

            dlg.delete()

        btn_add.add_event_cb(do_add, lv.EVENT.CLICKED, None)
        la = lv.label(btn_add)
        la.set_text("Add")
        la.center()

    # --------------------

    def add_days(self, ymd, days):
        # simple date add (forward only), no datetime dependency
        y, m, d = int_to_ymd(ymd)

        while days > 0:
            d += 1
            dim = days_in_month(y, m)
            if d > dim:
                d = 1
                m += 1
                if m > 12:
                    m = 1
                    y += 1
            days -= 1

        return ymd_to_int(y, m, d)

