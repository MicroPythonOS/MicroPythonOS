"""Outlines, labels and the control list for Duke's screen.

Nothing here is clickable: the activity keeps receiving the fingers and
``DukeTouch`` does the hit testing. ``TouchOverlay`` draws the same rectangles
``DukeTouch`` uses, so the picture cannot disagree with the hit areas.
``ControlsOverlay`` is the keyboard list a desktop shows instead, because a
keyboard has none of the pad's labels.

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


class _Overlay:
    """Objects that come and go together, placed in the game's own frame."""

    def __init__(self, activity):
        self.activity = activity
        self._rotated = activity._rotated
        self._objects = []
        self._visible = None

    def _panel(self, x, y, width, height):
        return self.activity.game_rect_to_panel(x, y, width, height)

    def _label(self, text, opa=LABEL_OPA):
        label = lv.label(self.activity.screen)
        label.set_text(text)
        label.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_text_opa(opa, lv.PART.MAIN)
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


class TouchOverlay(_Overlay):
    """Outlines for the stick and the six buttons, plus their labels."""

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

    def __init__(self, activity):
        super().__init__(activity)
        self._build()

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


class ControlsOverlay(_Overlay):
    """The keyboard's key list, over the picture until dismissed.

    A badge needs none of this: its controls are the action pad's own labels,
    which ``TouchOverlay`` draws over the pad. A desktop keyboard has no such
    labels, and the mapping is not guessable (jump is B, the menu is Esc), so
    the list is shown at launch and on demand with F1.

    Two columns of labels rather than padded spaces: the UI font is
    proportional, so spaces would not line the actions up.
    """

    TITLE = "DUKE NUKEM 3D - CONTROLS"
    ROWS = (
        ("Arrows", "walk / turn"),
        ("A", "fire"),
        ("B", "jump"),
        ("X or Z", "crouch"),
        ("Y / Space", "use / open"),
        ("Home", "next weapon"),
        ("Esc", "menu"),
        ("F1", "show / hide"),
    )
    KEY_COLUMN = 20
    ACTION_COLUMN = 132
    ROW_TOP = 40
    ROW_HEIGHT = 18
    TITLE_SIZES = (18, 16, 14, 12, 10)
    BODY_SIZES = (16, 14, 12, 10, 8)
    GAP = 6

    def __init__(self, activity):
        super().__init__(activity)
        self._build()

    def _build(self):
        width, height = self.activity._game_frame()
        background = lv.obj(self.activity.screen)
        x, y, panel_width, panel_height = self._panel(0, 0, width, height)
        background.set_pos(x, y)
        background.set_size(panel_width, panel_height)
        background.remove_flag(lv.obj.FLAG.CLICKABLE)
        background.remove_flag(lv.obj.FLAG.SCROLLABLE)
        background.set_style_pad_all(0, lv.PART.MAIN)
        background.set_style_radius(0, lv.PART.MAIN)
        background.set_style_border_width(0, lv.PART.MAIN)
        background.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        background.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self._objects.append(background)

        self._title = self._label(self.TITLE, opa=lv.OPA.COVER)
        self._keys = []
        self._actions = []
        for index, (key, action) in enumerate(self.ROWS):
            self._keys.append(self._label(key, opa=lv.OPA.COVER))
            self._actions.append(self._label(action, opa=lv.OPA.COVER))
            row_y = self.ROW_TOP + index * self.ROW_HEIGHT
            self._place(self._keys[-1], self.KEY_COLUMN, row_y)
            self._place(self._actions[-1], self.ACTION_COLUMN, row_y)
        self._fit_fonts(width)
        self.set_visible(True)

    def _place(self, label, game_x, game_y):
        x, y, _width, _height = self._panel(game_x, game_y, 1, 1)
        label.set_pos(x, y)

    def _fit_fonts(self, width):
        for size in self.TITLE_SIZES:
            font = getattr(lv, "font_montserrat_%d" % size, None)
            if font is None:
                continue
            self._title.set_style_text_font(font, lv.PART.MAIN)
            self._title.update_layout()
            if self._title.get_width() <= width - 2 * self.GAP:
                break
        self._place(self._title,
                    (width - self._title.get_width()) // 2, self.GAP)

        for size in self.BODY_SIZES:
            font = getattr(lv, "font_montserrat_%d" % size, None)
            if font is None:
                continue
            if not self._body_fits(font, width):
                continue
            for label in self._keys + self._actions:
                label.set_style_text_font(font, lv.PART.MAIN)
            return

    def _body_fits(self, font, width):
        """One size for the whole list: the widest key and action must fit."""
        key_room = self.ACTION_COLUMN - self.KEY_COLUMN - self.GAP
        action_room = width - self.ACTION_COLUMN - self.GAP
        for key, action in zip(self._keys, self._actions):
            key.set_style_text_font(font, lv.PART.MAIN)
            action.set_style_text_font(font, lv.PART.MAIN)
            key.update_layout()
            action.update_layout()
            if (key.get_width() > key_room or action.get_width() > action_room
                    or key.get_height() > self.ROW_HEIGHT):
                return False
        return True
