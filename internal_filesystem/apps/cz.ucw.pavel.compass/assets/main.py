"""
Robot translated that from bwatch/magcali.js

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

class Compass:
    def __init__(self):
        self.reset()

    def reset(self):
        self.vmin = [10000.0, 10000.0, 10000.0]
        self.vmax = [-10000.0, -10000.0, -10000.0]

    def step(self, v):
        """
        Update min/max. Returns True if calibration box changed ("bad" in JS).
        """
        bad = False
        for i in range(3):
            if v[i] < self.vmin[i]:
                self.vmin[i] = v[i]
                bad = True
            if v[i] > self.vmax[i]:
                self.vmax[i] = v[i]
                bad = True
        return bad

    def compensated(self, v):
        """
        Returns:
          vh = v - center
          sc = scaled to [-1..+1]
        """
        vh = [0.0, 0.0, 0.0]
        sc = [0.0, 0.0, 0.0]

        for i in range(3):
            center = (self.vmin[i] + self.vmax[i]) / 2.0
            vh[i] = v[i] - center

            denom = (self.vmax[i] - self.vmin[i])
            if denom == 0:
                sc[i] = 0.0
            else:
                sc[i] = (v[i] - self.vmin[i]) / denom * 2.0 - 1.0

        return vh, sc

    def heading_flat(self):
        """
        Equivalent of:
          heading = atan2(sc[1], sc[0]) * 180/pi - 90

        Compute heading based on last update(). This will only work well
        on flat surface.
        """
        vh, sc = self.compensated(self.val)
        
        h = to_deg(math.atan2(sc[1], sc[0])) - 90.0
        while h < 0:
            h += 360.0
        while h >= 360.0:
            h -= 360.0
        return h


class TiltCompass(Compass):
    def __init__(self):
        super().__init__()

    def tilt_calibrate(self):
        """
        JS tiltCalibrate(min,max)
        vmin/vmax are dicts with x,y,z
        """
        vmin = self.vmin
        vmax = self.vmax
        
        offset = ( (vmax[0] + vmin[0]) / 2.0,
                   (vmax[1] + vmin[1]) / 2.0,
                   (vmax[2] + vmin[2]) / 2.0 )
        delta = ( (vmax[0] - vmin[0]) / 2.0,
                  (vmax[1] - vmin[1]) / 2.0,
                  (vmax[2] - vmin[2]) / 2.0 )

        avg = (delta[0] + delta[1] + delta[2]) / 3.0

        # Avoid division by zero
        scale = (
            avg / delta[0] if delta[0] else 1.0,
            avg / delta[1] if delta[1] else 1.0,
            avg / delta[2] if delta[2] else 1.0,
        )

        self.offset = offset
        self.scale = scale

    def heading_tilted(self):
        """
        Returns heading 0..360
        """
        mag_xyz = self.val
        acc_xyz = self.acc
        
        if mag_xyz is None or acc_xyz is None:
            return None

        self.tilt_calibrate()

        mx, my, mz = mag_xyz
        ax, ay, az = acc_xyz

        dx = (mx - self.offset[0]) * self.scale[0]
        dy = (my - self.offset[1]) * self.scale[1]
        dz = (mz - self.offset[2]) * self.scale[2]

        # JS:
        # phi = atan(-g.x/-g.z)
        # theta = atan(-g.y/(-g.x*sinphi-g.z*cosphi))
        # ...
        # psi = atan2(yh,xh)
        #
        # Keep the same structure.

        # Avoid pathological az=0
        if az == 0:
            az = 1e-9

        phi = math.atan((-ax) / (-az))
        cosphi = math.cos(phi)
        sinphi = math.sin(phi)

        denom = (-ax * sinphi - az * cosphi)
        if denom == 0:
            denom = 1e-9

        theta = math.atan((-ay) / denom)
        costheta = math.cos(theta)
        sintheta = math.sin(theta)

        xh = dy * costheta + dx * sinphi * sintheta + dz * cosphi * sintheta
        yh = dz * sinphi - dx * cosphi

        psi = to_deg(math.atan2(yh, xh))
        if psi < 0:
            psi += 360.0
        return psi

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

class UCompass(TiltCompass):
    # val (+vfirst, vmin, vmax) -- vector from magnetometer
    # acc -- vector from accelerometer

    # FIXME: we need to scale acc to similar values we used on watch;
    # 90 degrees should correspond to outer circle

    def __init__(self):
        super().__init__()

        self.accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        self.magn = SensorManager.get_default_sensor(SensorManager.TYPE_MAGNETIC_FIELD)

        self.val = None
        self.vfirst = None

    def update(self):
        v = SensorManager.read_sensor_once(self.magn)
        sc = 1000
        v = [float(v[1]) * sc, -float(v[0]) * sc, float(v[2]) * sc]
        self.val = v

        if self.vfirst is None:
            self.vfirst = self.val[:]

        acc = SensorManager.read_sensor_once(self.accel)
        acc = ( -acc[1], -acc[0], acc[2] )
        self.acc = acc

class Main(PagedCanvas):
    def __init__(self):
        super().__init__()

        self.cal = UCompass()

        self.bad = False

        self.heading = 0.0
        self.heading2 = None

        self.Ypos = 40
        self.brg = None  # bearing target, degrees or None

    def draw(self):
        pass

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 50, None)

    def update(self):
        self.c.clear()
        st = 14
        y = 2*st

        self.cal.update()
        if self.cal.val is None:
            self.c.text(0, y, f"No compass data")
            y += st
            return

        self.bad = self.cal.step(self.cal.val)
        self.heading = self.cal.heading_flat()

        acc = self.cal.acc

        #self.c.text(0, y, f"Compass, raw is {self.cal.val}, bad is {self.bad}, acc is {acc}")
        y += st

        self.heading2 = self.cal.heading_tilted()

        if self.page == 0:
            self.draw_top(acc)
        elif self.page == 1:
            self.draw_values()
        elif self.page == 2:
            self.c.text(0, y, f"Resetting calibration")
            self.page = 0
            self.cal.reset()

    def build_buttons(self):
        self.template_buttons(["Graph", "Values", "Reset"])

    def draw_values(self):
        self.c.text(0, 28, f"""
Acccelerometer
X {self.cal.acc[0]:.2f} Y {self.cal.acc[1]:.2f} Z {self.cal.acc[2]:.2f}
Magnetometer      
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
        heading2=self.heading2
        vmin=self.cal.vmin
        vmax=self.cal.vmax
        vfirst=self.cal.vfirst
        v=self.cal.val
        bad=self.bad

        cx = self.c.W // 2
        cy = self.c.H // 2

        # Crosshair
        self.c.line(0, cy, self.c.W, cy)
        self.c.line(cx, 0, cx, self.c.H)

        # Circles (30/60/90 deg)
        for rdeg in (30, 60, 90):
            r = int(self._degrees_to_pixels(rdeg))
            self.c.circle(cx, cy, r)

        # Calibration box + current point
        self._draw_calib_box(vmin, vmax, vfirst, v, bad)

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

    def _draw_calib_box(self, vmin, vmax, vfirst, v, bad):
        if v is None or vfirst is None:
            return

        scale = 0.15

        boxW = (vmax[0] - vmin[0]) * scale
        boxH = -(vmax[1] - vmin[1]) * scale
        boxX = (vmin[0] - vfirst[0]) * scale + self.c.W / 2.0
        boxY = -(vmin[1] - vfirst[1]) * scale + self.c.H / 2.0

        x = (v[0] - vfirst[0]) * scale + self.c.W / 2.0
        y = -(v[1] - vfirst[1]) * scale + self.c.H / 2.0

        # box rect
        if bad:
            bg = lv.color_make(255, 0, 0)
        else:
            bg = lv.color_make(0, 150, 0)

        x1 = int(boxX)
        y1 = int(boxY)
        x2 = int(boxX + boxW)
        y2 = int(boxY + boxH)

        # normalize coords
        xa = min(x1, x2)
        xb = max(x1, x2)
        ya = min(y1, y2)
        yb = max(y1, y2)

        self.c.fill_rect(xa, ya, xb - xa, yb - ya, bg = bg)

        # point
        self.c.fill_circle(int(x), int(y), 3, bg = lv.color_make(255, 255, 0))

