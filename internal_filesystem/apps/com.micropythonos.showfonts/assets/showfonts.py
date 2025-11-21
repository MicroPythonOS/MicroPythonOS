from mpos.apps import Activity
import lvgl as lv

class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()

        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        self.addAllFonts(screen)
        #self.addAllGlyphs(screen)
        self.setContentView(screen)

    def addAllFonts(self, screen):
        fonts = [
            (lv.font_montserrat_10, "Montserrat 10"),
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_montserrat_16, "Montserrat 16"), # +6
            (lv.font_montserrat_22, "Montserrat 22"), # +6
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_montserrat_30, "Montserrat 30"), # +8
            (lv.font_montserrat_38, "Montserrat 38"), # +8
            (lv.font_montserrat_48, "Montserrat 48"), # +10
            (lv.font_dejavu_16_persian_hebrew, "DejaVu 16 Persian/Hebrew"),
        ]

        dsc = lv.font_glyph_dsc_t()

        y = 0
        for font, name in fonts:
            x = 0
            title = lv.label(screen)
            title.set_text(name + ":")
            title.set_style_text_font(lv.font_montserrat_16, 0)
            title.set_pos(x, y)
            y += title.get_height() + 20

            line_height = font.get_line_height() + 4

            for cp in range(0x20, 0xFF):
                if font.get_glyph_dsc(font, dsc, cp, cp+1):
                    lbl = lv.label(screen)
                    lbl.set_style_text_font(font, 0)
                    lbl.set_text(chr(cp))
                    lbl.set_pos(x, y)

                    width = font.get_glyph_width(cp, cp+1)
                    x += width
                    if x + width * 2 > screen.get_width():
                        x = 0
                        y += line_height

            y += line_height*2

        screen.set_height(y + 20)



    def addAllGlyphs(self, screen):
        fonts = [
            (lv.font_montserrat_16, "Montserrat 16"),
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_dejavu_16_persian_hebrew, "DejaVu 16 Persian/Hebrew"),
        ]

        dsc = lv.font_glyph_dsc_t()
        y = 40

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
