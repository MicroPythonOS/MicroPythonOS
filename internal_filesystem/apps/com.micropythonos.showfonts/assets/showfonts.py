from mpos.apps import Activity
import lvgl as lv

class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()

        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        y=0
        y = self.addAllFontsTitles(screen)
        #self.addAllFonts(screen)
        self.addAllGlyphs(screen, y)
        self.setContentView(screen)


    def addAllFontsTitles(self, screen):
        fonts = [
            (lv.font_montserrat_8, "Montserrat 8"), # almost too small to read
            (lv.font_montserrat_10, "Montserrat 10"), # +2
            (lv.font_montserrat_12, "Montserrat 12"), # +2 (default font, great for launcher and small labels)
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_montserrat_14, "Montserrat 14"), # +2
            (lv.font_montserrat_16, "Montserrat 16"), # +2
            #(lv.font_Noto_Sans_sat_emojis_compressed,
            #                        "Noto Sans 16SF"), # 丰 and 😀
            (lv.font_montserrat_18, "Montserrat 18"), # +2
            (lv.font_montserrat_20, "Montserrat 20"), # +2
            (lv.font_montserrat_24, "Montserrat 24"), # +4
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_montserrat_28_compressed, "Montserrat 28"), # +4
            (lv.font_montserrat_34, "Montserrat 34"), # +6
            (lv.font_montserrat_40, "Montserrat 40"), # +6
            (lv.font_montserrat_48, "Montserrat 48"), # +8
       ]

        y = 0
        for font, name in fonts:
            title = lv.label(screen)
            title.set_style_text_font(font, 0)
            title.set_text(f"{name}: 2357 !@#$%^&*( {lv.SYMBOL.OK} {lv.SYMBOL.BACKSPACE} 丰 😀")
            title.set_pos(0, y)
            y += font.get_line_height() + 4

        return y

    def addAllFonts(self, screen):
        fonts = [
            (lv.font_montserrat_10, "Montserrat 10"),
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_montserrat_16, "Montserrat 16"), # +4
            (lv.font_montserrat_22, "Montserrat 22"), # +6
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_montserrat_30, "Montserrat 30"), # +8
            (lv.font_montserrat_38, "Montserrat 38"), # +8
            (lv.font_montserrat_48, "Montserrat 48"), # +10
        ]

        dsc = lv.font_glyph_dsc_t()

        y = 0
        for font, name in fonts:
            x = 0
            title = lv.label(screen)
            title.set_text(name + ": 2357 !@#$%^&*(")
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



    def addAllGlyphs(self, screen, start_y):
        fonts = [
            #(lv.font_Noto_Sans_sat_emojis_compressed,
            #                        "Noto Sans 16SF"), # 丰 and 😀
            (lv.font_montserrat_16, "Montserrat 16"),
            #(lv.font_unscii_16, "Unscii 16"),
            #(lv.font_unscii_8, "Unscii 8"),
        ]

        dsc = lv.font_glyph_dsc_t()
        y = start_y

        for font, name in fonts:
            title = lv.label(screen)
            title.set_text(name)
            title.set_style_text_font(lv.font_montserrat_16, 0)
            title.set_pos(4, y)
            y += title.get_height() + 20

            line_height = font.get_line_height() + 4
            x = 4
            for cp in range(0x20, 0x1F9FF):
            #for cp in range(0x20, 35920 + 1):
            #for cp in range(0x20, 0xFFFF + 1):
                if font.get_glyph_dsc(font, dsc, cp, cp):
                    #print(f"{cp} : {chr(cp)}", end="")
                    #print(f"{chr(cp)},", end="")
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
