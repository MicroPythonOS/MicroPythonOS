"""Doom's touch map: thin outlines and word labels over the game picture.

The zones belong to ``ThumbZones``; this file only shows them, using the same
layout values the input path uses so the drawing cannot drift from the hit
areas. Nothing here is clickable: the activity's screen keeps receiving the
pointer, so the zones work exactly as before.

The picture is rotated by the engine on a portrait panel, so the rects are
placed through ``NativeActivity.game_rect_to_panel()`` and every label is
turned with the picture.
"""

import lvgl as lv

BORDER_OPA = lv.OPA._50
LABEL_OPA = lv.OPA._80
RECT_RADIUS = 4

# Every size the firmware ships, largest first. The overlay takes the largest
# one that still fits every zone, so a small panel or a scaled picture gets a
# smaller font instead of a label that runs over the neighbouring zone.
FONT_SIZES = (28, 24, 20, 18, 16, 14, 12, 10, 8)
# How much of its zone a label may use; the rest is the gap to the outline.
FONT_FILL_PERCENT = 85

# The stick is anchored under the thumb, so it has no arrows to aim at: the
# label says what the area does, and a touch anywhere in it starts the drag
# from that point.
STICK_HINT = "TURN/WALK"
MENU_TEXT = "MENU"
USE_TEXT = "OPEN/USE"
FIRE_TEXT = "FIRE/ENTER"


class TouchOverlay:
    """Outlines for the stick and the three action bands, plus their labels."""

    def __init__(self, activity, zones, width, height):
        self.activity = activity
        self.zones = zones
        self.width = width
        self.height = height
        self._objects = []
        self._visible = True
        self._rotated = activity._surface.height > activity._surface.width
        self._build()

    def _build(self):
        stick = self.zones.stick_width
        menu = self.zones.menu_bottom
        use = self.zones.use_bottom
        regions = (
            (0, 0, stick, self.height),
            (stick, 0, self.width - stick, menu),
            (stick, menu, self.width - stick, use - menu),
            (stick, use, self.width - stick, self.height - use),
        )
        panels = []
        for region in regions:
            panel = self.activity.game_rect_to_panel(*region)
            self._outline(*panel)
            panels.append(panel)

        labels = (
            self._label(STICK_HINT),
            self._label(MENU_TEXT),
            self._label(USE_TEXT),
            self._label(FIRE_TEXT),
        )
        self._fit_font(labels, panels)
        for label, panel in zip(labels, panels):
            self._centre(label, panel)

    def _fit_font(self, labels, panels):
        """The largest shipped font whose labels all fit their zones."""
        smallest = None
        # Keep a gap to the outline when the zone allows one; on a tiny panel
        # edge-to-edge text is still better than a size that does not fit.
        for fill in (FONT_FILL_PERCENT, 100):
            for size in FONT_SIZES:
                font = getattr(lv, "font_montserrat_%d" % size, None)
                if font is None:
                    continue
                smallest = font
                if self._all_fit(labels, panels, font, fill):
                    return font
        for label in labels:
            if smallest is not None:
                label.set_style_text_font(smallest, lv.PART.MAIN)
            label.update_layout()
        return smallest

    def _all_fit(self, labels, panels, font, fill):
        for label, panel in zip(labels, panels):
            label.set_style_text_font(font, lv.PART.MAIN)
            label.update_layout()
            if not self._fits(label, panel, fill):
                return False
        return True

    def _fits(self, label, panel, fill):
        width, height = panel[2], panel[3]
        if self._rotated:
            # A turned label's own width is the panel's height.
            width, height = height, width
        return (label.get_width() * 100 <= width * fill
                and label.get_height() * 100 <= height * fill)

    def _centre(self, label, panel):
        label.update_layout()
        panel_x = panel[0] + panel[2] // 2
        panel_y = panel[1] + panel[3] // 2
        label.set_pos(panel_x - label.get_width() // 2,
                      panel_y - label.get_height() // 2)

    def _outline(self, x, y, width, height):
        rect = lv.obj(self.activity.screen)
        rect.set_pos(x, y)
        rect.set_size(width, height)
        rect.remove_flag(lv.obj.FLAG.CLICKABLE)
        rect.remove_flag(lv.obj.FLAG.SCROLLABLE)
        rect.set_style_pad_all(0, lv.PART.MAIN)
        rect.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        rect.set_style_border_width(1, lv.PART.MAIN)
        rect.set_style_border_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        rect.set_style_border_opa(BORDER_OPA, lv.PART.MAIN)
        rect.set_style_radius(RECT_RADIUS, lv.PART.MAIN)
        self._objects.append(rect)

    def _label(self, text):
        label = lv.label(self.activity.screen)
        label.set_text(text)
        label.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_text_opa(LABEL_OPA, lv.PART.MAIN)
        if self._rotated:
            label.set_style_transform_rotation(900, lv.PART.MAIN)
        # The default pivot is the label's top-left corner, so a turned label
        # swings half its own size (tens of pixels) away from its position.
        # Turning it about its centre keeps the centre where it is put.
        label.set_style_transform_pivot_x(lv.pct(50), lv.PART.MAIN)
        label.set_style_transform_pivot_y(lv.pct(50), lv.PART.MAIN)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._objects.append(label)
        return label

    def set_visible(self, visible):
        visible = bool(visible)
        if visible == self._visible:
            return
        self._visible = visible
        for obj in self._objects:
            if visible:
                obj.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                obj.add_flag(lv.obj.FLAG.HIDDEN)
