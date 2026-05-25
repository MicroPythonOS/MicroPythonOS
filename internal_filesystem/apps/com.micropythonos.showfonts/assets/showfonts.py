from mpos import Activity
import lvgl as lv

from font_manager import FontManager


class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self._emoji_font_small = FontManager.getFont(size=18)
        self._emoji_font = FontManager.getFont(size=36)
        self._emoji_font_big = FontManager.getFont(size=72)
        self._ttf_font = FontManager.getFont(size=24, ttf="M:PrincessSofia-Regular.ttf")

        self.addImageFontDemo(screen)
        self.addAllFontsTitles(screen)
        self.addAllGlyphs(screen)

        self.setContentView(screen)

    def addAllFontsTitles(self, screen):
        fonts = FontManager.listFonts()
        fonts.append((self._ttf_font, "TTF PrincessSofia 24"))

        for font_info in fonts:
            if isinstance(font_info, tuple):
                font = font_info[0]
                name = font_info[1]
            else:
                font = font_info["font"]
                name = font_info["name"]
            title = lv.label(screen)
            lv.group_get_default().add_obj(title)
            title.set_width(lv.pct(99))
            title.set_style_text_font(font, lv.PART.MAIN)
            bitcoin_symbol = "\uf15a"
            bitcoin_symbol_in_circle = "\uf379"
            thumbs_up_symbol = "\uf164"
            diacritics = "æ ø å Æ Ø Å"
            supported_latin = "Æ æ Ð ð ß Þ þ 7"
            title.set_text(
                "{}: 2 p 3 g 5 j 7 !@#$%^&*( {} {} ₿ {} {} {} 丯 丰 {} {}".format(
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

    def addImageFontDemo(self, screen):

        title = lv.label(screen)
        title_font = FontManager.getFont(size=14)
        title.set_style_text_font(title_font, lv.PART.MAIN)
        title.set_text("Imagefont demo")

        demo_small = lv.label(screen)
        demo_small.set_style_text_font(self._emoji_font_small, lv.PART.MAIN)
        demo_small.set_text(FontManager.normalizeEmojiText("18px: A \u2639 \u263A == \U0001F642/\U0001F600 A"))

        demo = lv.label(screen)
        demo.set_style_text_font(self._emoji_font, lv.PART.MAIN)
        demo.set_text(FontManager.normalizeEmojiText("36px: ❤️ \U0001F929 \u2639/\u263A == \U0001F642/\U0001F600 A"))

        demo_big = lv.label(screen)
        demo_big.set_style_text_font(self._emoji_font_big, lv.PART.MAIN)
        demo_big.set_text(FontManager.normalizeEmojiText("72px: A \u2639/\u263A == \U0001F642/\U0001F600 A"))


    def addAllGlyphs(self, screen):
        dsc = lv.font_glyph_dsc_t()

        display_font = FontManager.getFont(size=16, family="Montserrat")
        lookup_font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        name = "Montserrat 16"

        title = lv.label(screen)
        title.set_text(name)
        title.set_style_text_font(display_font, lv.PART.MAIN)

        line_height = display_font.get_line_height() + 4
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

        lbl.set_text(alltext)
        lv.group_get_default().add_obj(lbl)

