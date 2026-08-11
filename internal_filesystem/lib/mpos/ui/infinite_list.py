import lvgl as lv


class InfiniteList:
    """Virtual scrollable list that only renders visible items.

    Uses a flex column container with scroll event handler to dynamically
    load/unload items as the user scrolls. Follows the LVGL scroll_7
    example pattern.

    Usage::

        items = [("Item 1",), ("Item 2",), ...]
        lst = InfiniteList(screen)
        lst.set_size(lv.pct(100), lv.pct(70))
        lst.center()
        lst.set_data(items, lambda container, idx, item: create_button(...))
    """

    def __init__(self, parent, load_margin=200, unload_margin=600):
        self._container = lv.obj(parent)
        self._container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self._container.set_scroll_dir(lv.DIR.VER)

        self._load_margin = load_margin
        self._unload_margin = unload_margin

        self._items = []
        self._render_cb = None
        self._first = -1
        self._last = -1
        self._scroll_running = False

        self._container.add_event_cb(self._on_scroll, lv.EVENT.SCROLL, None)

    @property
    def obj(self):
        return self._container

    def __len__(self):
        return len(self._items)

    @property
    def item_count(self):
        return len(self._items)

    @property
    def rendered_count(self):
        return self._container.get_child_count()

    @property
    def rendered_range(self):
        return (self._first, self._last)

    def set_size(self, w, h):
        self._container.set_size(w, h)

    def align(self, *args, **kwargs):
        self._container.align(*args, **kwargs)

    def center(self):
        self._container.center()

    def set_style_pad_all(self, value, selector=lv.PART.MAIN):
        self._container.set_style_pad_all(value, selector)

    def set_list_style(self):
        self._container.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self._container.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        self._container.set_style_radius(8, lv.PART.MAIN)
        self._container.set_style_border_width(2, lv.PART.MAIN)
        self._container.set_style_border_color(lv.color_hex(0xCCCCCC), lv.PART.MAIN)
        self._container.set_style_border_post(True, lv.PART.MAIN)
        self._container.set_style_pad_hor(16, lv.PART.MAIN)
        self._container.set_style_pad_ver(0, lv.PART.MAIN)
        self._container.set_style_pad_gap(0, lv.PART.MAIN)
        self._container.set_style_clip_corner(True, lv.PART.MAIN)

    def set_dimension(self, size):
        pass

    def move_to_index(self, index):
        pass

    def set_data(self, items, render_cb):
        self.clean()
        self._items = list(items)
        self._render_cb = render_cb
        if not self._items:
            return

        visible = self._visible_count()
        n_init = max(3, visible + 3)
        n_init = min(n_init, len(self._items))

        self._first = 0
        self._last = n_init - 1
        for i in range(n_init):
            self._render_cb(self._container, i, self._items[i])
        self._container.update_layout()

    def clean(self):
        self._container.clean()
        self._first = -1
        self._last = -1

    def _visible_count(self):
        return 15

    def _on_scroll(self, event):
        if self._scroll_running:
            return
        if not self._items:
            return
        self._scroll_running = True
        try:
            self._update()
        finally:
            self._scroll_running = False

    def _update(self):
        c = self._container
        n = len(self._items)

        # Load items near the bottom edge.
        while self._last < n - 1 and c.get_scroll_bottom() < self._load_margin:
            self._last += 1
            self._render_cb(c, self._last, self._items[self._last])
            c.update_layout()

        # Load items near the top edge.
        while self._first > 0 and c.get_scroll_top() < self._load_margin:
            self._first -= 1
            bottom_before = c.get_scroll_bottom()
            item = self._render_cb(c, self._first, self._items[self._first])
            item.move_to_index(0)
            c.update_layout()
            bottom_after = c.get_scroll_bottom()
            c.scroll_by(0, bottom_before - bottom_after, False)

        # Delete items far below the viewport.
        while c.get_scroll_bottom() > self._unload_margin and self._last > self._first:
            c.get_child(c.get_child_count() - 1).delete()
            c.update_layout()
            self._last -= 1

        # Delete items far above the viewport.
        while c.get_scroll_top() > self._unload_margin and self._first < self._last:
            bottom_before = c.get_scroll_bottom()
            c.get_child(0).delete()
            c.update_layout()
            bottom_after = c.get_scroll_bottom()
            c.scroll_by(0, bottom_before - bottom_after, False)
            self._first += 1
