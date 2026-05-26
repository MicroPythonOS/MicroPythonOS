from mpos import Activity
import lvgl as lv

from font_manager import FontManager


class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        import os
        mydir = os.path.dirname(os.path.abspath(__file__))
        self._ttf_font = FontManager.getFont(size=42, ttf=f"M:{mydir}/Rancourt-SmallCaps.ttf")

        self.addAllFontsTitles(screen)
        self.addAllGlyphs(screen)

        self.setContentView(screen)

    def addAllFontsTitles(self, screen):
        fonts = FontManager.listFonts()
        fonts.append((self._ttf_font, "TTF Rancourt 42"))

        for font_info in fonts:
            if isinstance(font_info, tuple):
                font = font_info[0]
                name = font_info[1]
            else:
                font = font_info["font"]
                name = font_info["name"]
            title = lv.label(screen)
            self.labelSelectable(title)
            title.set_width(lv.pct(99))
            title.set_style_text_font(font, lv.PART.MAIN)
            bitcoin_symbol = "\uf15a"
            bitcoin_symbol_in_circle = "\uf379"
            thumbs_up_symbol = "\uf164"
            diacritics = "æ ø å Æ Ø Å"
            supported_latin = "Æ æ Ð ð ß Þ þ"
            title.set_text(
                "{}: ABC 123 xyz ❤️ ☺️ !@#$%^&*( {} {} ₿ {} {} {} 丯 丰 {} {}".format(
                    name,
                    lv.SYMBOL.OK,
                    lv.SYMBOL.BACKSPACE,
                    bitcoin_symbol,
                    bitcoin_symbol_in_circle,
                    thumbs_up_symbol,
                    diacritics,
                    supported_latin,
                )
            )

    def addAllGlyphs(self, screen, emoji=True):
        dsc = lv.font_glyph_dsc_t()

        display_font = FontManager.getFont(size=16, family="Montserrat")
        lookup_font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        name = "Montserrat 16"

        title = lv.label(screen)
        title.set_text(name)
        title.set_style_text_font(display_font, lv.PART.MAIN)

        font_height = display_font.get_line_height()
        print("font_height: ", font_height)
        line_height = font_height + 4
        x = 4
        lbl = lv.label(screen)
        lbl.set_width(lv.pct(99))
        lbl.set_style_text_font(display_font, lv.PART.MAIN)
        alltext = ""
        for cp in range(0x20, 0xF800):
            if lookup_font.get_glyph_dsc(lookup_font, dsc, cp, cp):
                alltext = alltext + chr(cp) + " "

                x += 20
                if x + 20 > screen.get_width():
                    x = 4

        if emoji:
            FontManager._ensure_emoji_map()
            emoji_cps = sorted(FontManager._emoji_map.keys())
            for cp in emoji_cps:
                alltext = alltext + chr(cp) + " "

        lbl.set_text(alltext)
        self.labelSelectable(lbl)

    def labelSelectable(self, label):
        label.add_event_cb(self._focus_obj, lv.EVENT.FOCUSED, None)
        label.add_event_cb(self._defocus_obj, lv.EVENT.DEFOCUSED, None)
        lv.group_get_default().add_obj(label)

    @staticmethod
    def _focus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        target.set_style_border_width(1, lv.PART.MAIN)
        target.scroll_to_view(True)

    @staticmethod
    def _defocus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_width(0, lv.PART.MAIN)
