"""A full-screen RGB565 surface for native (C) renderers, presented by LVGL.

Apps import it as `mpos.ui.native_display`; it is firmware infrastructure and
is not copied into an app folder.

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

try:
    from mpos.ui.render_guard import has_render_headroom
except ImportError:
    # A firmware from before the render guard: nothing to check against.
    def has_render_headroom():
        return True


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
        # A device that renders on its own task hands over whichever of its
        # buffers is finished, so the surface can be pointed at more than one.
        self._buffers = [self.buffer]
        self._descriptors = [self._make_descriptor(self.buffer)]
        self._current = 0
        self._descriptor = self._descriptors[0]

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

    # -- lifecycle --------------------------------------------------------

    def _make_descriptor(self, buffer):
        """An image descriptor over `buffer`, of this surface's size."""
        return lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": self.width,
                "h": self.height,
                "stride": self.stride,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": self.stride * self.height,
            "data": buffer,
        })

    def add_buffer(self, buffer):
        """Register another buffer of this size; returns its index.

        A device that renders on its own task publishes frames into its own
        buffers, and the activity shows whichever one is finished. Both are the
        same size and format, so switching between them is a pointer change.
        Index 0 is always the buffer the surface was created with.
        """
        needed = self.width * self.height * self.bytes_per_pixel
        if len(buffer) < needed:
            raise ValueError("buffer holds %d bytes, %d needed" % (
                len(buffer), needed))
        self._buffers.append(buffer)
        self._descriptors.append(self._make_descriptor(buffer))
        return len(self._buffers) - 1

    def select_buffer(self, index):
        """Show buffer `index` from now on."""
        if index == self._current:
            return
        self._current = index
        self.buffer = self._buffers[index]
        self._descriptor = self._descriptors[index]
        self.image.set_src(self._descriptor)

    def begin(self):
        """Start presenting. The image is part of the activity's screen."""
        self._active = True
        self.frames = 0
        self.bands = 0
        self.invalidate_all()

    def end(self):
        """Stop presenting: the panel belongs to someone else from now on."""
        self._active = False

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

        A flush is a whole LVGL pass (layout, drawing, font composition) run
        on top of the caller's stack, and this is the one place such a pass
        starts *inside* a native engine: an engine that presents from its own
        tick calls back into Python from deep C frames. The render guard
        cannot skip that pass from where it sits, so check the headroom here.
        When the stack is too full, leave the invalidation pending: LVGL's
        refresh timer draws it from a shallow point. A skipped flush costs one
        frame of latency, not the frame itself - and an overflow here does not
        raise, it resets or hangs the board.

        Returns True when the pass ran, False when it was left for the refresh
        timer. A caller that owns the pixels (a buffer borrowed from another
        task) must keep them alive until it gets a True.
        """
        if not has_render_headroom():
            return False
        lv.refr_now(None)
        return True

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
