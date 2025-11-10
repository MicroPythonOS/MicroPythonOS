from mpos.apps import Activity
import lvgl as lv

class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()
        #cont.set_size(320, 240)
        #cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        #cont.set_scroll_dir(lv.DIR.VER)

        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        fonts = [
            (lv.font_montserrat_16, "Montserrat 16"),
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_dejavu_16_persian_hebrew, "DejaVu 16 Persian/Hebrew"),
        ]

        dsc = lv.font_glyph_dsc_t()
        y = 4

        for font, name in fonts:
            title = lv.label(screen)
            title.set_text(name)
            title.set_style_text_font(lv.font_montserrat_16, 0)
            title.set_pos(4, y)
            y += title.get_height() + 20

            line_height = font.get_line_height() + 4
            x = 4

            for cp in range(0x20, 0xFFFF + 1):
                if font.get_glyph_dsc(font, dsc, cp, cp):
                    lbl = lv.label(screen)
                    lbl.set_style_text_font(font, 0)
                    lbl.set_text(chr(cp))
                    lbl.set_pos(x, y)

                    x += 20
                    if x + 20 > screen.get_width():
                        x = 4
                        y += line_height

            y += line_height

        screen.set_height(y + 20)
        self.setContentView(screen)
