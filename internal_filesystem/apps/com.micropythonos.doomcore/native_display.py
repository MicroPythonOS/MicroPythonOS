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
    """An RGB565 framebuffer shown by an image widget.

    ``width`` and ``height`` default to the whole display. A surface smaller than
    the display is centred, which is how a 320x200 engine gets letterboxed on a
    320x240 panel.

    ``buffer`` lets the caller own the pixels: an engine that insists on its own
    framebuffer is wrapped with no allocation and no copy. The buffer is not
    copied into or out of, so the engine may write to it between frames.
    """

    bytes_per_pixel = 2

    def __init__(self, screen, display=None, buffer=None, width=None, height=None):
        if display is None:
            display = mpos.ui.main_display
        self.display = display
        screen_width = display.get_horizontal_resolution()
        screen_height = display.get_vertical_resolution()
        if width is None:
            width = screen_width
        if height is None:
            height = screen_height
        if width < 1 or height < 1:
            raise ValueError("surface size must be positive")
        if width > screen_width or height > screen_height:
            raise ValueError("surface is larger than the display")
        self.width = width
        self.height = height
        self.stride = width * self.bytes_per_pixel

        # One band is what one of the display driver's draw buffers can hold, so
        # a band is a single blit and a single SPI transfer.
        draw_buffer = getattr(display, "_frame_buffer1", None)
        if draw_buffer and width > 0:
            rows = len(draw_buffer) // self.stride
        else:
            rows = self.height
        if rows < 1:
            rows = 1
        if rows > self.height:
            rows = self.height
        self.rows_per_band = rows
        self.band_count = (self.height + rows - 1) // rows

        if buffer is None:
            self.buffer = bytearray(width * height * self.bytes_per_pixel)
        else:
            needed = width * height * self.bytes_per_pixel
            if len(buffer) < needed:
                raise ValueError("buffer holds %d bytes, %d needed" % (
                    len(buffer), needed))
            self.buffer = buffer
        self._descriptor = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": self.width,
                "h": self.height,
                "stride": self.stride,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": self.stride * self.height,
            "data": self.buffer,
        })

        self.image = lv.image(screen)
        self.image.set_src(self._descriptor)
        self._image_x = (screen_width - width) // 2
        self._image_y = (screen_height - height) // 2
        self.image.set_pos(self._image_x, self._image_y)
        self.image.set_size(self.width, self.height)
        self.image.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.image.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self._area = lv.area_t()
        self._active = False
        self.frames = 0
        self.bands = 0
        self._direct_cmd = None

    # -- lifecycle --------------------------------------------------------

    def begin(self):
        """Start presenting. The image is part of the activity's screen."""
        self._active = True
        self.frames = 0
        self.bands = 0
        self.invalidate_all()

    # -- direct presenting ------------------------------------------------

    def direct_start(self):
        """Stop feeding LVGL and hand bands to the panel bus itself.

        LVGL copies a changed band into its own draw buffer and then DMAs
        that, so its ``flush()`` adds a 128 KB copy per frame and waits for the
        panel before returning. A renderer that redraws the whole frame every
        time can skip both: each band goes to the bus as it is finished, and the
        transfer of one band runs while the next is converted.

        The window is set *once*, for the whole surface: the controller's write
        pointer walks through it, so the bands must be sent in order and cover
        it completely (they do). Setting the window per band costs ~6 ms,
        because a parameter transfer waits for the queued colour transfer.

        The band is the surface itself rather than a copy. The bus swaps RGB565
        in place, which leaves the surface byte-swapped, so LVGL must not redraw
        the image until ``direct_stop()``; the renderer rewrites every band on
        the next frame.

        No completion callback is involved - that belongs to the display driver
        and taking it over is how a native renderer hangs LVGL.
        """
        if self._direct_cmd is not None:
            return
        x1 = self._image_x
        y1 = self._image_y
        self._direct_cmd = self.display._set_memory_location(
            x1, y1, x1 + self.width - 1, y1 + self.height - 1)

    def direct_stop(self):
        """Hand the panel back to LVGL (call before anything invalidates)."""
        self._direct_cmd = None

    @property
    def direct_active(self):
        return self._direct_cmd is not None

    def present_band_direct(self, y, rows):
        """Send the rows ``y``..``y+rows`` of the surface, in order."""
        if y + rows > self.height:
            rows = self.height - y
        start = y * self.stride
        self.display._data_bus.tx_color(
            self._direct_cmd,
            memoryview(self.buffer)[start:start + rows * self.stride],
            self._image_x, self._image_y + y,
            self._image_x + self.width - 1, self._image_y + y + rows - 1,
            self.display._rotation, False)
        self.bands += 1

    # -- presenting -------------------------------------------------------

    def invalidate_band(self, band):
        y1 = band * self.rows_per_band
        y2 = y1 + self.rows_per_band - 1
        if y2 >= self.height:
            y2 = self.height - 1
        area = self._area
        area.x1 = self._image_x
        area.y1 = self._image_y + y1
        area.x2 = self._image_x + self.width - 1
        area.y2 = self._image_y + y2
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

    def present_area(self, x1, y1, x2, y2, render, flush=True):
        """Render the bands that intersect a rectangle and flush just that.

        The rectangle is in surface coordinates (0..width-1, 0..height-1), not
        screen coordinates: the caller does not need to know where the image was
        placed. The renderer still fills whole bands of rows (that is the buffer
        layout it works in), but only the requested rectangle is invalidated, so
        the panel is not sent rows the caller knows are unchanged.
        """
        if not self._active:
            return
        if x1 < 0:
            x1 = 0
        if y1 < 0:
            y1 = 0
        if x2 > self.width - 1:
            x2 = self.width - 1
        if y2 > self.height - 1:
            y2 = self.height - 1
        if x1 > x2 or y1 > y2:
            return

        first = y1 // self.rows_per_band
        last = y2 // self.rows_per_band
        if last >= self.band_count:
            last = self.band_count - 1
        for band in range(first, last + 1):
            render(band)
            self.bands += 1
        self.frames += 1

        area = self._area
        area.x1 = self._image_x + x1
        area.y1 = self._image_y + y1
        area.x2 = self._image_x + x2
        area.y2 = self._image_y + y2
        self.image.invalidate_area(area)
        if flush:
            self.flush()
