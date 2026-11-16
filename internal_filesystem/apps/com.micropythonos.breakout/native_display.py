"""A full-screen RGB565 surface for native (C) renderers, presented by LVGL.

This file also ships inside com.micropythonos.breakout as `native_display.py`,
because an app released through the AppStore has to run on firmware that was
built before this module existed. The two copies must stay identical:
tests/test_graphical_native_display.py checks that they are.

Why not write the display's framebuffers directly
-------------------------------------------------
The first version of this did exactly that: the C renderer drew into
``main_display._frame_buffer1`` and pushed it with ``_data_bus.tx_color``. It
works, and a copy is saved, but two owners write the same panel. LVGL keeps
refreshing its own widget tree into the same DMA buffers and flushing them
between the game's chunks, so the screen alternates between game content and
LVGL's (mostly empty) screen. That is the flicker, and the interleaved flushes
also eat most of the frame rate.

LVGL 9 will not let an app pause its display refresh: the refresh timer pauses
itself at the start of every pass and resumes itself once there is work, so an
external ``pause()`` is undone by the next invalidation. Taking over the bus
callback instead leaves LVGL waiting forever for ``flush_ready``. The supported
place to plug a native renderer in is the draw pipeline, not the panel.

What this does
--------------
``NativeDisplay`` owns one ordinary RGB565 buffer and an ``lv_image`` widget
that displays it. A native renderer draws into the buffer at full speed, the
app says which bands of rows changed, and LVGL blits and flushes exactly those
bands. There is one writer of the panel (LVGL), so there is nothing to flicker
between, and the SPI transfer still overlaps the next band's blit because the
display driver is double buffered.

The band loop::

    pump.present(bands, render)

calls ``render(band)`` for every band in ``bands`` and then invalidates that
band. Bands are ``pump.rows_per_band`` rows tall, which is what one display
buffer holds, so one band is one blit and one flush. A renderer that only moves
a small object should only report the bands that object touches: at 320x240 a
full screen is 153600 bytes over an 80MHz SPI bus (~25ms), while one band is
about 4.6ms.

Call ``present`` from the task handler's finished callback (or an app timer) and
it flushes immediately with ``lv.refr_now``: waiting for LVGL's 33ms refresh
period would quantize the frame rate to 30fps.
"""

import lvgl as lv

import mpos.ui


class NativeDisplay:
    """An RGB565 framebuffer shown by a full-screen image widget."""

    def __init__(self, screen, display=None):
        if display is None:
            display = mpos.ui.main_display
        self.display = display
        self.width = display.get_horizontal_resolution()
        self.height = display.get_vertical_resolution()

        # One band is what one of the display driver's draw buffers can hold, so
        # a band is a single blit and a single SPI transfer.
        draw_buffer = getattr(display, "_frame_buffer1", None)
        if draw_buffer and self.width > 0:
            rows = len(draw_buffer) // (self.width * 2)
        else:
            rows = self.height
        if rows < 1:
            rows = 1
        if rows > self.height:
            rows = self.height
        self.rows_per_band = rows
        self.band_count = (self.height + rows - 1) // rows

        self.buffer = bytearray(self.width * self.height * 2)
        self._descriptor = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": self.width,
                "h": self.height,
                "stride": self.width * 2,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": len(self.buffer),
            "data": self.buffer,
        })

        self.image = lv.image(screen)
        self.image.set_src(self._descriptor)
        self.image.set_pos(0, 0)
        self.image.set_size(self.width, self.height)
        self.image.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.image.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self._area = lv.area_t()
        self._active = False
        self.frames = 0
        self.bands = 0

    # -- lifecycle --------------------------------------------------------

    def begin(self):
        """Start presenting. The image is part of the activity's screen."""
        self._active = True
        self.frames = 0
        self.bands = 0
        self.invalidate_all()

    def end(self):
        self._active = False

    # -- presenting -------------------------------------------------------

    def invalidate_band(self, band):
        y1 = band * self.rows_per_band
        y2 = y1 + self.rows_per_band - 1
        if y2 >= self.height:
            y2 = self.height - 1
        area = self._area
        area.x1 = 0
        area.y1 = y1
        area.x2 = self.width - 1
        area.y2 = y2
        self.image.invalidate_area(area)

    def invalidate_all(self):
        self.image.invalidate()

    def flush(self):
        """Draw and push the invalidated areas right now.

        Waiting for LVGL's refresh period would quantize the frame rate to
        30fps, so an app that needs its frame out immediately calls this.
        """
        lv.refr_now(None)

    def present(self, bands, render, flush=True):
        """Render and flush ``bands``; ``render(band)`` fills one band.

        ``bands`` may be a generator that reports dirty bands one at a time, so
        a renderer can hand over "whatever changed" without building a list.
        Nothing is drawn while the surface is not active: an activity that is
        paused must not touch the panel another one is drawing.
        """
        if not self._active:
            return
        dirty = False
        for band in bands:
            render(band)
            self.invalidate_band(band)
            self.bands += 1
            dirty = True
        self.frames += 1
        if flush and dirty:
            self.flush()

    def present_all(self, render, flush=True):
        """Render and flush every band: a full screen redraw."""
        self.present(range(self.band_count), render, flush=flush)
