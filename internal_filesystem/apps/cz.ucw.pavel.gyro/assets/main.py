"""
xxx


"""

import time
import os
import math

try:
    import lvgl as lv
except ImportError:
    pass

from mpos import Activity, MposKeyboard, SensorManager

# -----------------------------
# Utilities
# -----------------------------

def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v

def to_rad(deg):
    return deg * math.pi / 180.0

def to_deg(rad):
    return rad * 180.0 / math.pi

# -----------------------------
# Calibration + heading
# -----------------------------

class Gyro:
    def reset(self):
        pass

class TiltGyro(Gyro):
    def __init__(self):
        super().__init__()
        self.heading = 0
        self.last = time.time()
        self.smooth = 0.0

    def heading_tilted(self):
        """
        Returns heading 0..360

        iio is in rads/second
        """
        t = time.time()
        # pp: val[1] seems to be rotation "away" and "towards" the user, like pitch in plane ... or maybe roll?
        # val[2] sseems to be rotation -- as useful for compass on table
        v = self.val[2]
        coef = 1.0
        self.smooth = self.smooth * (1-coef) + v * coef
        self.heading -= self.smooth * (t - self.last)
        self.last = t
        self.angvel = -self.smooth
        return self.heading

# -----------------------------
# Canvas (LVGL)
# -----------------------------

class Canvas:
    """
    LVGL canvas + layer drawing Canvas.

    This matches ports where:
      - lv.canvas has init_layer() / finish_layer()
      - primitives are drawn via lv.draw_* into lv.layer_t
    """

    def __init__(self, scr, canvas):
        self.scr = scr

        # Screen size
        self.W = scr.get_width()
        self.H = scr.get_height()

        # Bottom button bar
        self.margin = 2
        self.bar_h = 39

        # Canvas drawing area (everything above button bar)
        self.draw_w = self.W
        self.draw_h = self.H - (self.bar_h + self.margin * 2)

        self.canvas = canvas

        # Background: white (change if you want dark theme)
        self.canvas.set_style_bg_color(lv.color_white(), lv.PART.MAIN)

        # Buffer: your working example uses 4 bytes/pixel
        # Reality filter: this depends on LV_COLOR_DEPTH; but your example proves it works.
        self.buf = bytearray(self.draw_w * self.draw_h * 4)
        self.canvas.set_buffer(self.buf, self.draw_w, self.draw_h, lv.COLOR_FORMAT.NATIVE)

        # Layer used for draw engine
        self.layer = lv.layer_t()
        self.canvas.init_layer(self.layer)

        # Persistent draw descriptors (avoid allocations)
        self._line_dsc = lv.draw_line_dsc_t()
        lv.draw_line_dsc_t.init(self._line_dsc)
        self._line_dsc.width = 1
        self._line_dsc.color = lv.color_black()
        self._line_dsc.round_end = 1
        self._line_dsc.round_start = 1

        self._label_dsc = lv.draw_label_dsc_t()
        lv.draw_label_dsc_t.init(self._label_dsc)
        self._label_dsc.color = lv.color_black()
        self._label_dsc.font = lv.font_montserrat_24

        self._rect_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(self._rect_dsc)
        self._rect_dsc.bg_opa = lv.OPA.TRANSP
        self._rect_dsc.border_opa = lv.OPA.COVER
        self._rect_dsc.border_width = 1
        self._rect_dsc.border_color = lv.color_black()

        self._fill_dsc = lv.draw_rect_dsc_t()
        lv.draw_rect_dsc_t.init(self._fill_dsc)
        self._fill_dsc.bg_opa = lv.OPA.COVER
        self._fill_dsc.bg_color = lv.color_black()
        self._fill_dsc.border_width = 1

        # Clear once
        self.clear()

    # ----------------------------
    # Layer lifecycle
    # ----------------------------

    def _begin(self):
        # Start drawing into the layer
        self.canvas.init_layer(self.layer)

    def _end(self):
        # Commit drawing
        self.canvas.finish_layer(self.layer)

    # ----------------------------
    # Public API: drawing
    # ----------------------------

    def clear(self):
        # Clear the canvas background
        self.canvas.fill_bg(lv.color_white(), lv.OPA.COVER)

    def text(self, x, y, s, fg = lv.color_black()):
        self._begin()

        dsc = lv.draw_label_dsc_t()
        lv.draw_label_dsc_t.init(dsc)
        dsc.text = str(s)
        dsc.font = lv.font_montserrat_24
        dsc.color = lv.color_black()

        area = lv.area_t()
        area.x1 = x
        area.y1 = y
        area.x2 = x + self.W
        area.y2 = y + self.H

        lv.draw_label(self.layer, dsc, area)

        self._end()

    def line(self, x1, y1, x2, y2, fg = lv.color_black()):
        self._begin()

        dsc = self._line_dsc
        dsc.p1 = lv.point_precise_t()
        dsc.p2 = lv.point_precise_t()
        dsc.p1.x = int(x1)
        dsc.p1.y = int(y1)
        dsc.p2.x = int(x2)
        dsc.p2.y = int(y2)

        lv.draw_line(self.layer, dsc)

        self._end()

    def circle(self, x, y, r, fg = lv.color_black()):
        # Rounded rectangle trick (works everywhere)
        self._begin()

        a = lv.area_t()
        a.x1 = int(x - r)
        a.y1 = int(y - r)
        a.x2 = int(x + r)
        a.y2 = int(y + r)

        dsc = self._rect_dsc
        dsc.radius = lv.RADIUS_CIRCLE
        dsc.border_color = fg

        lv.draw_rect(self.layer, dsc, a)

        self._end()

    def fill_circle(self, x, y, r, fg = lv.color_black(), bg = lv.color_white()):
        self._begin()

        a = lv.area_t()
        a.x1 = int(x - r)
        a.y1 = int(y - r)
        a.x2 = int(x + r)
        a.y2 = int(y + r)

        dsc = self._rect_dsc
        dsc.radius = lv.RADIUS_CIRCLE
        dsc.border_color = fg
        dsc.bg_color = bg

        lv.draw_rect(self.layer, dsc, a)

        self._end()

    def fill_rect(self, x, y, sx, sy, fg = lv.color_black(), bg = lv.color_white()):
        self._begin()

        a = lv.area_t()
        a.x1 = x
        a.y1 = y
        a.x2 = x+sx
        a.y2 = y+sy

        dsc = self._fill_dsc
        dsc.border_color = fg
        dsc.bg_color = bg

        lv.draw_rect(self.layer, dsc, a)

        self._end()

    def update(self):
        # Nothing needed; drawing is committed per primitive.
        # If you want, you can change the implementation so that:
        # - draw ops happen between clear() and update()
        # But then you must ensure the app calls update() once per frame.
        pass

# ----------------------------
# App logic
# ----------------------------

class PagedCanvas(Activity):
    def __init__(self):
        super().__init__()
        self.page = 0
        self.pages = 3

    def onCreate(self):
        self.scr = lv.obj()
        scr = self.scr

        # Screen size
        self.W = scr.get_width()
        self.H = scr.get_height()

        # Bottom button bar
        self.margin = 2
        self.bar_h = 39

        # Canvas drawing area (everything above button bar)
        self.draw_w = self.W
        self.draw_h = self.H - (self.bar_h + self.margin * 2)

        # Canvas
        self.canvas = lv.canvas(self.scr)
        self.canvas.set_size(self.draw_w, self.draw_h)
        self.canvas.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.canvas.set_style_border_width(0, 0)
        
        self.c = Canvas(self.scr, self.canvas)
        
        # Build buttons
        self.build_buttons()
        self.setContentView(self.c.scr)

    # ----------------------------
    # Button bar
    # ----------------------------

    def _make_btn(self, parent, x, y, w, h, label):
        b = lv.button(parent)
        b.set_pos(x, y)
        b.set_size(w, h)

        l = lv.label(b)
        l.set_text(label)
        l.center()

        return b

    def _btn_cb(self, evt, tag):
        self.page = tag

    def template_buttons(self, names):
        margin = self.margin
        y = self.H - self.bar_h - margin

        num = len(names)
        if num == 0:
            self.buttons = []
            return

        w = (self.W - margin * (num + 1)) // num
        h = self.bar_h
        x0 = margin

        self.buttons = []

        for i, label in enumerate(names):
            x = x0 + (w + margin) * i
            btn = self._make_btn(self.scr, x, y, w, h, label)

            # capture index correctly
            btn.add_event_cb(
                lambda evt, idx=i: self._btn_cb(evt, idx),
                lv.EVENT.CLICKED,
                None
            )

            self.buttons.append(btn)

    def build_buttons(self):
        self.template_buttons(["Pg0", "Pg1", "Pg2", "Pg3", "..."])

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 1000, None)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None
            
    def tick(self, t):
        self.update()
        self.draw()

    def update(self):
        pass

    def draw_page_example(self):
        ui = self.c
        ui.clear()

        st = 28
        y = 2*st
        ui.text(0, y, "Hello world, page is %d" % self.page)
        y += st

    def draw(self):
        self.draw_page_example()

    def handle_buttons(self):
        ui = self.c

# ----------------------------
# App logic
# ----------------------------

class UGyro(TiltGyro):
    def __init__(self):
        super().__init__()

        self.accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        self.magn = SensorManager.get_default_sensor(SensorManager.TYPE_MAGNETIC_FIELD)
        self.gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)

        self.val = None
        self.vfirst = None

        self.heading = 45

    def update(self):
        acc = SensorManager.read_sensor_once(self.accel)
        sc = 1/9.81
        acc = ( -acc[0] * sc, acc[1] * sc, acc[2] * sc )
        self.acc = acc

        self.val = SensorManager.read_sensor_once(self.gyro)

class Main(PagedCanvas):
    def __init__(self):
        super().__init__()

        self.cal = UGyro()

        self.heading = 0.0

        self.Ypos = 40

    def draw(self):
        pass

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 50, None)

    def update(self):
        self.c.clear()

        y = 20
        st = 20

        self.cal.update()
        if self.cal.val is None:
            self.c.text(0, y, f"No compass data")
            y += st
            return

        self.heading = self.cal.heading_tilted()

        if self.page == 0:
            self.draw_top(self.cal.acc)
        if self.page == 1:
            self.draw_values()
        elif self.page == 2:
            self.c.text(0, y, f"Resetting calibration")
            self.page = 0
            self.cal.reset()

    def build_buttons(self):
        self.template_buttons(["Pg0", "Pg1", "Pg2"])

    def draw_values(self):
        x, y, z = self.cal.acc[0], self.cal.acc[1], self.cal.acc[2]
        total = math.sqrt(x*x+y*y+z*z)
        s = ""
        if x > .6:
            s += ", left"
        if x < -.6:
            s += ", right"
        if y > .6:
            s += ", up"
        if y < -.6:
            s += ", down"
        if z > .6:
            s += ", below"
        if z < -.6:
            s += ", above"
            
        self.c.text(0, 7, f"""
^ Up -> Right
|| Acc
X {self.cal.acc[0]:.2f} Y {self.cal.acc[1]:.2f} Z {self.cal.acc[2]:.2f}
{total*100:.2f}% {s}
X {self.cal.val[0]:.2f} Y {self.cal.val[1]:.2f} Z {self.cal.val[2]:.2f}
""")

    def _px_per_deg(self):
        # JS used deg->px: (deg/90)*(width/2.1)
        s = min(self.c.W, self.c.H)
        return (s / 2.1) / 90.0

    def _degrees_to_pixels(self, deg):
        return deg * self._px_per_deg()

    # ---- TOP VIEW ----

    def draw_top(self, acc):
        heading=self.heading
        heading2=self.cal.angvel
        vmin=0
        vmax=20
        v=self.cal.val

        cx = self.c.W // 2
        cy = self.c.H // 2

        # Crosshair
        self.c.line(0, cy, self.c.W, cy)
        self.c.line(cx, 0, cx, self.c.H)

        # Circles (30/60/90 deg)
        for rdeg in (30, 60, 90):
            r = int(self._degrees_to_pixels(rdeg))
            self.c.circle(cx, cy, r)

        # Accel circle
        if acc is not None:
            self._draw_accel(acc)

        # Heading arrow(s)
        self._draw_heading_arrow(heading, color=lv.color_make(255, 0, 0))
        self.c.text(265, 22, "%d°" % int(heading))
        if heading2 is not None:
            self._draw_heading_arrow(heading2, color=lv.color_make(255, 255, 255), size = 100)
            self.c.text(10, 22, "%d°" % int(heading2))

    def _draw_heading_arrow(self, heading, color, size = 80):
        cx = self.c.W / 2.0
        cy = self.c.H / 2.0

        rad = -to_rad(heading)
        x2 = cx + math.sin(rad - 0.1) * size
        y2 = cy - math.cos(rad - 0.1) * size
        x3 = cx + math.sin(rad + 0.1) * size
        y3 = cy - math.cos(rad + 0.1) * size

        poly = [
            int(cx), int(cy),
            int(x2), int(y2),
            int(x3), int(y3),
        ]

        self.c.line(poly[0], poly[1], poly[2], poly[3])
        self.c.line(poly[2], poly[3], poly[4], poly[5])
        self.c.line(poly[4], poly[5], poly[0], poly[1])

    def _draw_accel(self, acc):
        ax, ay, az = acc
        cx = self.c.W / 2.0
        cy = self.c.H / 2.0

        x2 = cx + ax * self.c.W
        y2 = cy + ay * self.c.W

        self.c.circle(int(x2), int(y2), int(self.c.W / 8))
