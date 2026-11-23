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
LABEL_FONT = lv.font_montserrat_18
RECT_RADIUS = 4

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
        self._outline(0, 0, stick, self.height)
        self._outline(stick, 0, self.width - stick, menu)
        self._outline(stick, menu, self.width - stick, use - menu)
        self._outline(stick, use, self.width - stick, self.height - use)

        self._label(STICK_HINT, stick // 2, self.height // 2)

        column = stick + (self.width - stick) // 2
        self._label(MENU_TEXT, column, menu // 2)
        self._label(USE_TEXT, column, (menu + use) // 2)
        self._label(FIRE_TEXT, column, (use + self.height) // 2)

    def _outline(self, x, y, width, height):
        panel_x, panel_y, panel_width, panel_height = (
            self.activity.game_rect_to_panel(x, y, width, height))
        rect = lv.obj(self.activity.screen)
        rect.set_pos(panel_x, panel_y)
        rect.set_size(panel_width, panel_height)
        rect.remove_flag(lv.obj.FLAG.CLICKABLE)
        rect.remove_flag(lv.obj.FLAG.SCROLLABLE)
        rect.set_style_pad_all(0, lv.PART.MAIN)
        rect.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        rect.set_style_border_width(1, lv.PART.MAIN)
        rect.set_style_border_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        rect.set_style_border_opa(BORDER_OPA, lv.PART.MAIN)
        rect.set_style_radius(RECT_RADIUS, lv.PART.MAIN)
        self._objects.append(rect)

    def _label(self, text, x, y):
        label = lv.label(self.activity.screen)
        label.set_text(text)
        label.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_text_opa(LABEL_OPA, lv.PART.MAIN)
        label.set_style_text_font(LABEL_FONT, lv.PART.MAIN)
        if self._rotated:
            label.set_style_transform_rotation(900, lv.PART.MAIN)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        # Measure the text, then centre it on the point. align() only stores an
        # offset that LVGL resolves at layout time, which would depend on the
        # parent's size rather than on the point we want.
        label.update_layout()
        panel_x, panel_y = self.activity.game_to_panel(x, y)
        label.set_pos(panel_x - label.get_width() // 2,
                      panel_y - label.get_height() // 2)
        self._objects.append(label)

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
