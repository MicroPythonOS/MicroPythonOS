import lvgl as lv
from micropython import const  # NOQA
import micropython  # NOQA  # NOQA
import keypad_framework

KEY_UNKNOWN = 0
KEY_BACKSPACE = 8  # LV_KEY_BACKSPACE
KEY_TAB = 9  # LV_KEY_NEXT
KEY_CLEAR = 12
KEY_RETURN = 13  # LV_KEY_ENTER
KEY_PAUSE = 19  #
KEY_ESCAPE = 27  # LV_KEY_ESC
KEY_SPACE = 32  # " "
KEY_EXCLAIM = 33  # !
KEY_QUOTEDBL = 34  # "
KEY_HASH = 35  # #
KEY_DOLLAR = 36  # $
KEY_AMPERSAND = 38  # &
KEY_QUOTE = 39  # '
KEY_LEFTPAREN = 40  # (
KEY_RIGHTPAREN = 41  # )
KEY_ASTERISK = 42  # *
KEY_PLUS = 43  # +
KEY_COMMA = 44  # ,
KEY_MINUS = 45  # -
KEY_PERIOD = 46  # .
KEY_SLASH = 47  # /

KEY_0 = 48  # 0
KEY_1 = 49  # 1
KEY_2 = 50  # 2
KEY_3 = 51  # 3
KEY_4 = 52  # 4
KEY_5 = 53  # 5
KEY_6 = 54  # 6
KEY_7 = 55  # 7
KEY_8 = 56  # 8
KEY_9 = 57  # 9

KEY_COLON = 58  # :
KEY_SEMICOLON = 59  # ;
KEY_LESS = 60  # <
KEY_EQUALS = 61  # =
KEY_GREATER = 62  # >
KEY_QUESTION = 63  # ?
KEY_AT = 64  # @
KEY_LEFTBRACKET = 91  # [
KEY_BACKSLASH = 92  # \
KEY_RIGHTBRACKET = 93  # ]
KEY_CARET = 94  # ^
KEY_UNDERSCORE = 95  # _
KEY_BACKQUOTE = 96  # `
KEY_a = 97  # a
KEY_z = 122  # z
KEY_DELETE = 127  # LV_KEY_DEL

# Numeric keypad
# if MOD_KEY_NUM then it's numbers.

KEYPAD_0 = 256  # 0/INS
KEYPAD_1 = 257  # 1/END         LV_KEY_END
KEYPAD_2 = 258  # 2/DOWN        LV_KEY_DOWN
KEYPAD_3 = 259  # 3/PAGEDOWN
KEYPAD_4 = 260  # 4/LEFT        LV_KEY_LEFT
KEYPAD_5 = 261  # 5
KEYPAD_6 = 262  # 6/RIGHT       LV_KEY_RIGHT
KEYPAD_7 = 263  # 7/HOME        LV_KEY_HOME
KEYPAD_8 = 264  # 8/UP          LV_KEY_UP
KEYPAD_9 = 265  # 9/PAGEUP
KEYPAD_PERIOD = 266  # ./DEL    LV_KEY_DEL
KEYPAD_DIVIDE = 267  # /
KEYPAD_MULTIPLY = 268   # *
KEYPAD_MINUS = 269  # -
KEYPAD_PLUS = 270  # +
KEYPAD_ENTER = 271  # LV_KEY_ENTER
KEYPAD_EQUALS = 272  # =

# Arrows + Home/End pad

KEY_UP = 273  # LV_KEY_UP
KEY_DOWN = 274  # LV_KEY_DOWN
KEY_RIGHT = 275  # LV_KEY_RIGHT
KEY_LEFT = 276  # LV_KEY_LEFT
KEY_INSERT = 277
KEY_HOME = 278  # LV_KEY_HOME
KEY_END = 279  # LV_KEY_END
KEY_PAGEUP = 280
KEY_PAGEDOWN = 281

KEY_F1 = 282 
KEY_F2 = 283 
KEY_F3 = 284 
KEY_F4 = 285 
KEY_F5 = 286 
KEY_F6 = 287 
KEY_F7 = 288 
KEY_F8 = 289 
KEY_F9 = 290 
KEY_F10 = 291
KEY_F11 = 292
KEY_F12 = 293
KEY_F13 = 294
KEY_F14 = 295
KEY_F15 = 296

KEY_NUMLOCK = 300
KEY_CAPSLOCK = 301
KEY_SCROLLOCK = 302
KEY_RSHIFT = 303
KEY_LSHIFT = 304
KEY_RCTRL = 305
KEY_LCTRL = 306
KEY_RALT = 307
KEY_LALT = 308
KEY_RMETA = 309
KEY_LMETA = 310

# Left "Windows" key
KEY_LSUPER = 311

# Right "Windows" key
KEY_RSUPER = 312

# Alt Gr" key 
KEY_MODE = 313
# Multi-key compose key
KEY_COMPOSE = 314

KEY_HELP = 315 
KEY_PRINT = 316 
KEY_SYSREQ = 317 
KEY_BREAK = 318 
KEY_MENU = 319 
# Power Macintosh power key
KEY_POWER = 320
# Some european keyboards
KEY_EURO = 321
#  Atari keyboard has Undo
KEY_UNDO = 322

MOD_KEY_NONE = 0x0000
MOD_KEY_LSHIFT = 0x0001
MOD_KEY_RSHIFT = 0x0002
MOD_KEY_LCTRL = 0x0040
MOD_KEY_RCTRL = 0x0080
MOD_KEY_LALT = 0x0100
MOD_KEY_RALT = 0x0200
MOD_KEY_LMETA = 0x0400
MOD_KEY_RMETA = 0x0800
MOD_KEY_NUM = 0x1000
MOD_KEY_CAPS = 0x2000
MOD_KEY_MODE = 0x4000
MOD_KEY_CTRL = MOD_KEY_LCTRL | MOD_KEY_RCTRL
MOD_KEY_SHIFT = MOD_KEY_LSHIFT | MOD_KEY_RSHIFT
MOD_KEY_ALT = MOD_KEY_LALT | MOD_KEY_RALT
MOD_KEY_META = MOD_KEY_LMETA | MOD_KEY_RMETA

# SDL keycode ranges
SDL_NAV_KEY_START = 1073741897   # Insert
SDL_NAV_KEY_END = 1073741906     # Down Arrow
SDL_FUNC_KEY_START = 1073741882  # F1
SDL_FUNC_KEY_END = 1073741893    # F12
SDL_KEYPAD_KEY_START = 1073741908 # Keypad /
SDL_KEYPAD_KEY_END = 1073741923   # Keypad .

# Shift key mappings for QWERTY layout
SHIFT_KEY_MAP = {
    KEY_1: KEY_EXCLAIM,         # 1 -> !
    KEY_2: KEY_AT,             # 2 -> @
    KEY_3: KEY_HASH,           # 3 -> #
    KEY_4: KEY_DOLLAR,         # 4 -> $
    KEY_5: 37,                 # 5 -> % (ASCII 37)
    KEY_6: KEY_CARET,          # 6 -> ^
    KEY_7: KEY_AMPERSAND,      # 7 -> &
    KEY_8: KEY_ASTERISK,       # 8 -> *
    KEY_9: KEY_LEFTPAREN,      # 9 -> (
    KEY_0: KEY_RIGHTPAREN,     # 0 -> )
    KEY_MINUS: KEY_UNDERSCORE, # - -> _
    KEY_EQUALS: KEY_PLUS,      # = -> +
    KEY_LEFTBRACKET: 123,      # [ -> { (ASCII 123)
    KEY_RIGHTBRACKET: 125,     # ] -> } (ASCII 125)
    KEY_BACKSLASH: 124,        # \ -> | (ASCII 124)
    KEY_SEMICOLON: KEY_COLON,  # ; -> :
    KEY_QUOTE: KEY_QUOTEDBL,   # ' -> "
    KEY_COMMA: KEY_LESS,       # , -> <
    KEY_PERIOD: KEY_GREATER,   # . -> >
    KEY_SLASH: KEY_QUESTION,   # / -> ?
    KEY_BACKQUOTE: 126,        # ` -> ~ (ASCII 126)
}


class MposSDLKeyboard(keypad_framework.KeypadDriver):

    def __init__(self, *args, **kwargs):  # NOQA
        super().__init__()
        self.__last_key = -1
        self.__current_state = self.RELEASED

        self.group = lv.group_create()
        self.group.set_default()  # NOQA
        self.set_group(self.group)
        self.set_mode(lv.INDEV_MODE.EVENT)  # NOQA

        self._py_disp_drv._data_bus.register_keypad_callback(self._keypad_cb)  # NOQA

        self.paste_text_callback = None

    def set_paste_text_callback(self, callback):
        self.paste_text_callback = callback

    def set_mode(self, mode):
        self._indev_drv.set_mode(mode)  # NOQA

    def _keypad_cb(self, *args):
        if len(args) == 5:  # Special case for paste
            _, state, key, mod, clipboard_text = args
            print(f"got clipboard paste arg: {clipboard_text}")
            if self.paste_text_callback and state == 1 and key == 118 and mod & MOD_KEY_CTRL:  # CTRL-V
                self.paste_text_callback(clipboard_text)
            return
        else:
            _, state, key, mod = args
        #print(f"mpos_sdl_keyboard.py _keypad_cb got {_}, {state} {key} {mod}")

        # Skip modifier keys and SDL-specific large keycodes (>= 2^30), except keypad, nav, and func keys
        if (key in {KEY_LSHIFT, KEY_RSHIFT, KEY_LCTRL, KEY_RCTRL, KEY_LALT, KEY_RALT,
                    KEY_LMETA, KEY_RMETA, KEY_LSUPER, KEY_RSUPER, KEY_MODE, KEY_COMPOSE,
                    KEY_NUMLOCK, KEY_CAPSLOCK, KEY_SCROLLOCK} or
                (key >= 1 << 30 and not (SDL_NAV_KEY_START <= key <= SDL_NAV_KEY_END or
                                         SDL_FUNC_KEY_START <= key <= SDL_FUNC_KEY_END or
                                         SDL_KEYPAD_KEY_START <= key <= SDL_KEYPAD_KEY_END))):
            self.__last_key = -1  # Do not send modifier keys to LVGL
            return

        if key == KEY_PAUSE:
            return

        # Handle numeric keypad keys (SDL keycodes and original KEYPAD_* range)
        if (KEYPAD_0 <= key <= KEYPAD_EQUALS or
                SDL_KEYPAD_KEY_START <= key <= SDL_KEYPAD_KEY_END):
            if mod & MOD_KEY_NUM:
                mapping = {
                    KEYPAD_0: KEY_0,
                    KEYPAD_1: KEY_1,
                    KEYPAD_2: KEY_2,
                    KEYPAD_3: KEY_3,
                    KEYPAD_4: KEY_4,
                    KEYPAD_5: KEY_5,
                    KEYPAD_6: KEY_6,
                    KEYPAD_7: KEY_7,
                    KEYPAD_8: KEY_8,
                    KEYPAD_9: KEY_9,
                    KEYPAD_PERIOD: KEY_PERIOD,
                    KEYPAD_DIVIDE: KEY_SLASH,
                    KEYPAD_MULTIPLY: KEY_ASTERISK,
                    KEYPAD_MINUS: KEY_MINUS,
                    KEYPAD_PLUS: KEY_PLUS,
                    KEYPAD_ENTER: KEY_EQUALS,
                    KEYPAD_EQUALS: KEY_EQUALS,
                    1073741908: KEY_SLASH,      # Keypad /
                    1073741909: KEY_ASTERISK,   # Keypad *
                    1073741910: KEY_MINUS,      # Keypad -
                    1073741911: KEY_PLUS,       # Keypad +
                    1073741912: lv.KEY.ENTER,   # Keypad ENTER
                    1073741913: KEY_1,          # Keypad 1
                    1073741914: KEY_2,          # Keypad 2
                    1073741915: KEY_3,          # Keypad 3
                    1073741916: KEY_4,          # Keypad 4
                    1073741917: KEY_5,          # Keypad 5
                    1073741918: KEY_6,          # Keypad 6
                    1073741919: KEY_7,          # Keypad 7
                    1073741920: KEY_8,          # Keypad 8
                    1073741921: KEY_9,          # Keypad 9
                    1073741922: KEY_0,          # Keypad 0
                    1073741923: KEY_PERIOD      # Keypad .
                }
            else:
                mapping = {
                    KEYPAD_0: KEY_INSERT,
                    KEYPAD_1: lv.KEY.END,  # NOQA
                    KEYPAD_2: lv.KEY.DOWN,  # NOQA
                    KEYPAD_3: lv.KEY.PREV,  # NOQA
                    KEYPAD_4: lv.KEY.LEFT,  # NOQA
                    KEYPAD_5: KEY_5,
                    KEYPAD_6: lv.KEY.RIGHT,  # NOQA
                    KEYPAD_7: lv.KEY.HOME,  # NOQA
                    KEYPAD_8: lv.KEY.UP,  # NOQA
                    KEYPAD_9: lv.KEY.NEXT,  # NOQA
                    KEYPAD_PERIOD: lv.KEY.DEL,  # NOQA
                    KEYPAD_DIVIDE: KEY_SLASH,
                    KEYPAD_MULTIPLY: KEY_ASTERISK,
                    KEYPAD_MINUS: KEY_MINUS,
                    KEYPAD_PLUS: KEY_PLUS,
                    KEYPAD_ENTER: lv.KEY.ENTER,  # NOQA
                    KEYPAD_EQUALS: KEY_EQUALS,
                    1073741908: KEY_SLASH,      # Keypad /
                    1073741909: KEY_ASTERISK,   # Keypad *
                    1073741910: KEY_MINUS,      # Keypad -
                    1073741911: KEY_PLUS,       # Keypad +
                    1073741912: lv.KEY.ENTER,   # Keypad ENTER
                    1073741913: lv.KEY.END,     # Keypad 1
                    1073741914: lv.KEY.DOWN,    # Keypad 2
                    1073741915: lv.KEY.PREV,    # Keypad 3
                    1073741916: lv.KEY.LEFT,    # Keypad 4
                    1073741917: KEY_5,          # Keypad 5
                    1073741918: lv.KEY.RIGHT,   # Keypad 6
                    1073741919: lv.KEY.HOME,    # Keypad 7
                    1073741920: lv.KEY.UP,      # Keypad 8
                    1073741921: lv.KEY.NEXT,    # Keypad 9
                    1073741922: KEY_INSERT,     # Keypad 0
                    1073741923: lv.KEY.DEL      # Keypad .
                }

            self.__last_key = mapping[key]
            # Apply Shift for keypad symbols if applicable
            if mod & MOD_KEY_SHIFT and self.__last_key in SHIFT_KEY_MAP:
                self.__last_key = SHIFT_KEY_MAP[self.__last_key]
        else:
            mapping = {
                KEY_BACKSPACE: lv.KEY.BACKSPACE,  # NOQA
                KEY_TAB: lv.KEY.NEXT,  # NOQA
                KEY_RETURN: lv.KEY.ENTER,  # NOQA
                KEY_ESCAPE: lv.KEY.ESC,  # NOQA
                KEY_DELETE: lv.KEY.DEL,  # NOQA
                KEY_UP: lv.KEY.UP,  # NOQA
                KEY_DOWN: lv.KEY.DOWN,  # NOQA
                KEY_RIGHT: lv.KEY.RIGHT,  # NOQA
                KEY_LEFT: lv.KEY.LEFT,  # NOQA
                KEY_HOME: lv.KEY.HOME,  # NOQA
                KEY_END: lv.KEY.END,  # NOQA
                KEY_PAGEDOWN: lv.KEY.PREV,  # NOQA
                KEY_PAGEUP: lv.KEY.NEXT,  # NOQA
                1073741897: KEY_INSERT,     # SDL Insert
                1073741898: lv.KEY.HOME,    # SDL Home
                1073741899: lv.KEY.PREV,    # SDL PageUp
                1073741900: lv.KEY.DEL,     # SDL Delete (unconfirmed)
                1073741901: lv.KEY.END,     # SDL End
                1073741902: lv.KEY.NEXT,    # SDL PageDown
                1073741903: lv.KEY.RIGHT,   # SDL Right Arrow
                1073741904: lv.KEY.LEFT,    # SDL Left Arrow
                1073741905: lv.KEY.DOWN,    # SDL Down Arrow
                1073741906: lv.KEY.UP,      # SDL Up Arrow
                1073741882: KEY_F1,         # SDL F1
                1073741883: KEY_F2,         # SDL F2
                1073741884: KEY_F3,         # SDL F3
                1073741885: KEY_F4,         # SDL F4
                1073741886: KEY_F5,         # SDL F5
                1073741887: KEY_F6,         # SDL F6
                1073741888: KEY_F7,         # SDL F7
                1073741889: KEY_F8,         # SDL F8
                1073741890: KEY_F9,         # SDL F9
                1073741891: KEY_F10,        # SDL F10
                1073741892: KEY_F11,        # SDL F11
                1073741893: KEY_F12         # SDL F12
            }

            # Handle Shift or Caps Lock for letters and symbols
            if mod & (MOD_KEY_SHIFT | MOD_KEY_CAPS) and KEY_a <= key <= KEY_z:
                # Convert lowercase to uppercase
                self.__last_key = key - 32  # ASCII lowercase to uppercase
            elif mod & MOD_KEY_SHIFT and key in SHIFT_KEY_MAP:
                # Apply Shift mapping for numbers and punctuation
                self.__last_key = SHIFT_KEY_MAP[key]
            else:
                # Use standard mapping or key as-is
                self.__last_key = mapping.get(key, key)

        if state:
            self.__current_state = self.PRESSED
        else:
            self.__current_state = self.RELEASED

        try:
            micropython.schedule(MposSDLKeyboard.read, self)
        except Exception as e:
            print(f"mpos_sdl_keyboard.py failed to call micropython.schedule: {e}")

    def _get_key(self):
        return self.__current_state, self.__last_key
