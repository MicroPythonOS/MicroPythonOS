"""Outlines and labels for Duke's touch controls.

Nothing here is clickable: the activity keeps receiving the fingers and
``DukeTouch`` does the hit testing. This module draws the same rectangles
``DukeTouch`` uses, so the picture cannot disagree with the hit areas.

The frame is 320x200 on a 320x240 landscape panel, so the picture is centred;
every rect goes through ``NativeActivity.game_rect_to_panel()`` instead of being
placed in raw panel pixels.
"""

import lvgl as lv

from duke_controls import BUTTONS, button_rect, STICK_WIDTH

BORDER_OPA = lv.OPA._40
LABEL_OPA = lv.OPA._70
RECT_RADIUS = 5

# Largest first: a label that does not fit its cell would run into its
# neighbour, so the overlay picks the largest font whose labels all fit.
FONT_SIZES = (24, 20, 18, 16, 14, 12, 10, 8)
FONT_FILL_PERCENT = 80

STICK_TEXT = "WALK/TURN"


class TouchOverlay:
    """Outlines for the stick and the six buttons, plus their labels."""

    def __init__(self, activity):
        self.activity = activity
        self._rotated = activity._rotated
        self._objects = []
        self._visible = None
        self._build()

    def _build(self):
        game_height = self.activity._game_frame()[1]
        panels = []
        panels.append(self._outline(*self._panel(0, 0, STICK_WIDTH, game_height)))
        for label, column, row, _key, _hold in BUTTONS:
            panels.append(self._outline(
                *self._panel(*button_rect(column, row))))

        labels = [self._label(STICK_TEXT)]
        labels.extend(self._label(button[0]) for button in BUTTONS)
        self._fit_font(labels, panels)
        for label, panel in zip(labels, panels):
            self._centre(label, panel)
        self.set_visible(True)

    def _panel(self, x, y, width, height):
        return self.activity.game_rect_to_panel(x, y, width, height)

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
        return (x, y, width, height)

    def _label(self, text):
        label = lv.label(self.activity.screen)
        label.set_text(text)
        label.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_text_opa(LABEL_OPA, lv.PART.MAIN)
        if self._rotated:
            # The core transposed the picture for the portrait panel; the label
            # has to turn with it or it reads sideways once the badge is held
            # landscape. Both pivots default to the top-left corner, so turning
            # there would swing the text away from its centre.
            label.set_style_transform_rotation(900, lv.PART.MAIN)
            label.set_style_transform_pivot_x(lv.pct(50), lv.PART.MAIN)
            label.set_style_transform_pivot_y(lv.pct(50), lv.PART.MAIN)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._objects.append(label)
        return label

    def _fit_font(self, labels, panels):
        smallest = None
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

    @staticmethod
    def _centre(label, panel):
        label.update_layout()
        panel_x = panel[0] + panel[2] // 2
        panel_y = panel[1] + panel[3] // 2
        label.set_pos(panel_x - label.get_width() // 2,
                      panel_y - label.get_height() // 2)

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

    @property
    def visible(self):
        return bool(self._visible)
