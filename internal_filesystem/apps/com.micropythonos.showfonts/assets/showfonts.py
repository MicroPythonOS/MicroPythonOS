from mpos import Activity
import lvgl as lv

from font_manager import FontManager


class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()

        self._emoji_font_small = FontManager.getFont(size=18)
        self._emoji_font = FontManager.getFont(size=36)
        self._emoji_font_big = FontManager.getFont(size=72)
        self._ttf_font = FontManager.getFont(size=24, ttf="M:PrincessSofia-Regular.ttf")

        y = 0
        y = self.addImageFontDemo(screen, y)
        y = self.addAllFontsTitles(y, screen)
        self.addAllGlyphs(screen, y)
        self.setContentView(screen)

    def addAllFontsTitles(self, start_y, screen):
        fonts = FontManager.listFonts()
        fonts.append((self._ttf_font, "TTF PrincessSofia 24"))

        y = start_y
        for font_info in fonts:
            if isinstance(font_info, tuple):
                font = font_info[0]
                name = font_info[1]
            else:
                font = font_info["font"]
                name = font_info["name"]
            title = lv.label(screen)
            title.set_style_text_font(font, lv.PART.MAIN)
            bitcoin_symbol = "\uf15a"
            bitcoin_symbol_in_circle = "\uf379"
            thumbs_up_symbol = "\uf164"
            diacritics = "æ ø å Æ Ø Å"
            supported_latin = "Æ æ Ð ð ß Þ þ 7"
            title.set_text(
                "{}: 2357 !@#$%^&*( {} {} ₿ {} {} {} 丯 丰 {} {}".format(
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
            title.set_pos(0, y)
            y += font.get_line_height() + 4

        return y

    def addImageFontDemo(self, screen, start_y):
        y = start_y

        title = lv.label(screen)
        title_font = FontManager.getFont(size=14)
        title.set_style_text_font(title_font, lv.PART.MAIN)
        title.set_text("Imagefont demo")
        title.set_pos(0, y)
        y += title_font.get_line_height() + 4

        demo_small = lv.label(screen)
        demo_small.set_style_text_font(self._emoji_font_small, lv.PART.MAIN)
        demo_small.set_text(FontManager.normalizeEmojiText("18px: A \u2639 \u263A == \U0001F642/\U0001F600 A"))
        demo_small.set_pos(0, y)
        y += self._emoji_font_small.get_line_height() + 12

        demo = lv.label(screen)
        demo.set_style_text_font(self._emoji_font, lv.PART.MAIN)
        demo.set_text(FontManager.normalizeEmojiText("36px: ❤️ \U0001F929 \u2639/\u263A == \U0001F642/\U0001F600 A"))
        demo.set_pos(0, y)
        y += self._emoji_font.get_line_height() + 12

        demo_big = lv.label(screen)
        demo_big.set_style_text_font(self._emoji_font_big, lv.PART.MAIN)
        demo_big.set_text(FontManager.normalizeEmojiText("72px: A \u2639/\u263A == \U0001F642/\U0001F600 A"))
        demo_big.set_pos(0, y)
        y += self._emoji_font_big.get_line_height() + 12

        return y

    def addAllGlyphs(self, screen, start_y):
        dsc = lv.font_glyph_dsc_t()
        y = start_y

        display_font = FontManager.getFont(size=16, family="Montserrat")
        lookup_font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        name = "Montserrat 16"

        title = lv.label(screen)
        title.set_text(name)
        title.set_style_text_font(display_font, lv.PART.MAIN)
        title.set_pos(4, y)
        y += title.get_height() + 20

        line_height = display_font.get_line_height() + 4
        x = 4
        for cp in range(0x20, 0xF800):
            if lookup_font.get_glyph_dsc(lookup_font, dsc, cp, cp):
                lbl = lv.label(screen)
                lbl.set_style_text_font(display_font, lv.PART.MAIN)
                lbl.set_text(chr(cp))
                lbl.set_pos(x, y)

                x += 20
                if x + 20 > screen.get_width():
                    x = 4
                    y += line_height

        y += line_height

        screen.set_height(y + 20)
