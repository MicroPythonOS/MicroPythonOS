"""Doom's legal notices, in one module instead of three text files.

The package is flat: every file is an inode and every littlefs directory costs
about 8 KiB of metadata, so the GPL notice, the shareware WAD notice and the
credits live here as strings and a small screen renders them. The AppStore
listing repeats the source and license URLs, which is the part a user sees
before installing.

Do not hide these behind ``__debug__``: mpy-cross removes those blocks from a
release build.
"""

import lvgl as lv

from mpos import Activity, DisplayMetrics

SOURCE_URL = "https://github.com/MicroPythonOS/MicroPythonOS/tree/main/c_mpos/doom"
GPL_URL = "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html"

GPL_NOTICE = """Doom for MicroPythonOS is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License, or (at your option) any later version.

It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

The complete corresponding source is the public repository at %s, which is the written offer for the GPL source.""" % SOURCE_URL

SHAREWARE_NOTICE = """This package includes DOOM1.WAD, the shareware episode of Doom ("Knee-Deep in the Dead"), Copyright (c) 1993-1996 id Software, Inc.

DOOM is a registered trademark of id Software, Inc. The shareware episode is distributed free of charge in its original, unmodified form; it may not be sold. The full game requires the retail WAD, which is not included.

Doom is built from doomgeneric, a portable Doom port, and the engine sources are Chocolate Doom's. See the source repository for their copyright notices and licenses."""

CREDITS = """Engine: doomgeneric and Chocolate Doom contributors.
Original game: id Software.
MicroPythonOS port: the MicroPythonOS project (engine build, flash-resident core loader, native module, input and display integration)."""

SECTIONS = (
    ("License - GNU GPL v2 or later", GPL_NOTICE),
    ("DOOM1.WAD - shareware", SHAREWARE_NOTICE),
    ("Credits", CREDITS),
)


def start(parent):
    """Open the licenses screen on top of ``parent``."""
    from mpos import Intent

    parent.startActivity(Intent(
        activity_class=DoomLicenses, app_fullname="com.micropythonos.doom"))


class DoomLicenses(Activity):

    def onCreate(self):
        screen = lv.obj()
        screen.add_flag(lv.obj.FLAG.SCROLLABLE)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(3), lv.PART.MAIN)

        width = DisplayMetrics.pct_of_width(94)
        for title, body in SECTIONS:
            heading = lv.label(screen)
            heading.set_text(title)
            heading.set_style_text_decor(lv.TEXT_DECOR.UNDERLINE, lv.PART.MAIN)
            heading.set_style_pad_top(DisplayMetrics.pct_of_width(3), lv.PART.MAIN)

            text = lv.label(screen)
            text.set_text(body)
            text.set_width(width)
            text.set_long_mode(lv.label.LONG_MODE.WRAP)
            text.set_style_text_line_space(2, lv.PART.MAIN)

        self.setContentView(screen)
