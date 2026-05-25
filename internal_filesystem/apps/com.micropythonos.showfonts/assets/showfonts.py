from mpos import Activity
import lvgl as lv
import os

CP_VARIATION_SELECTOR_TEXT = 0xFE0E
CP_VARIATION_SELECTOR_EMOJI = 0xFE0F

EMOJI_PNG_DIR = "openmoji-72x72-color"
EMOJI_PNG_SRC_PREFIX = "M:apps/com.micropythonos.showfonts/assets/openmoji-72x72-color/"
EMOJI_PNG_DIR_CANDIDATES = (
    EMOJI_PNG_DIR,
    "./" + EMOJI_PNG_DIR,
    "assets/" + EMOJI_PNG_DIR,
    "apps/com.micropythonos.showfonts/assets/" + EMOJI_PNG_DIR,
    "/apps/com.micropythonos.showfonts/assets/" + EMOJI_PNG_DIR,
    "M:apps/com.micropythonos.showfonts/assets/" + EMOJI_PNG_DIR,
)
UNKNOWN_EMOJI_LOG_THRESHOLD = 0x2300


class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()

        # Make the screen focusable so it can be scrolled with the arrow keys
        lv.group_get_default().add_obj(screen)

        self._emoji_map = {}
        self._emoji_font = None
        self._emoji_font_small = None
        self._ttf_font = None
        self._imgfont_scaled_src_cache = {}
        self._imgfont_source_size_cache = {}
        self._imgfont_empty_src_cache = {}
        self._unknown_emoji_codepoints_logged = {}
        self._init_imagefont()
        self._init_ttf_font()

        y = 0
        y = self.addImageFontDemo(screen, y)
        y = self.addAllFontsTitles(y, screen)
        self.addAllGlyphs(screen, y)
        self.setContentView(screen)

    def addAllFontsTitles(self, start_y, screen):
        fonts = [
            (lv.font_montserrat_8, "Montserrat 8"),  # almost too small to read
            (lv.font_montserrat_10, "Montserrat 10"),  # +2
            (lv.font_montserrat_12, "Montserrat 12"),  # +2 (default font, great for launcher and small labels)
            (lv.font_unscii_8, "Unscii 8"),
            (lv.font_montserrat_14, "Montserrat 14"),  # +2
            (lv.font_montserrat_16, "Montserrat 16"),  # +2
            #(lv.font_Noto_Sans_sat_emojis_compressed,
            #                        "Noto Sans 16SF"), # 丰 and 😀
            (lv.font_montserrat_18, "Montserrat 18"),  # +2
            (lv.font_montserrat_20, "Montserrat 20"),  # +2
            (lv.font_montserrat_24, "Montserrat 24"),  # +4
            (lv.font_unscii_16, "Unscii 16"),
            (lv.font_montserrat_28, "Montserrat 28"),  # +4
        ]
        if self._ttf_font is not None:
            fonts.append((self._ttf_font, "TTF PrincessSofia 24"))

        y = start_y
        for font, name in fonts:
            title = lv.label(screen)
            title.set_style_text_font(font, lv.PART.MAIN)
            # Custom symbols:
            bitcoin_symbol = "\uf15a"
            bitcoin_symbol_in_circle = "\uf379"
            thumbs_up_symbol = "\uf164"
            diacritics = "æ ø å Æ Ø Å"
            #latin = "Æ æ \tⱭ ɑ \tɅ ʌ \tꞴ ꞵ \tÐ ð \tƐ ɛ \tƏ ə \tƎ ə \tƔ ɣ \tƢ ƣ \tƖ ɩ \tꞍ ɥ \tꟚ ꟛ \tŊ ŋ \tŒ œ \tƆ ɔ \tꟋ ɤ \tKʼ ĸ \tƦ ʀ \tẞ ß \tƩ ʃ \tƜ ɯ \tƱ ʊ \tꞶ ꞷ \tƲ ʋ \tǷ ƿ Ȝ ȝ \tϴ θ \tƷ ʒ \tƸ ƹ \tÞ þ \tȢ ȣ \tꞳ ꭓ \tɁ ʔ ɂ \t꟎ ʕ ꟏ \tǀ \tǁ \tǂ \tǃ \tʘ \tʻ \tʼ \tꞋ ꞌ \tƧ ƨ \tꜪ ꜫ \tꜬ ꜭ \tƼ ƽ \tƄ ƅ \t7 \t"
            supported_latin = "Æ æ Ð ð ß Þ þ 7"
            title.set_text(f"{name}: 2357 !@#$%^&*( {lv.SYMBOL.OK} {lv.SYMBOL.BACKSPACE} ₿ {bitcoin_symbol} {bitcoin_symbol_in_circle} {thumbs_up_symbol} 丯 丰 {diacritics} {supported_latin}")
            title.set_pos(0, y)
            y += font.get_line_height() + 4

        return y

    def addImageFontDemo(self, screen, start_y):
        y = start_y

        title = lv.label(screen)
        title.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
        title.set_text("Imagefont demo")
        title.set_pos(0, y)
        y += lv.font_montserrat_14.get_line_height() + 4

        demo_small = lv.label(screen)
        demo_small.set_style_text_font(self._emoji_font_small, lv.PART.MAIN)
        demo_small.set_text(self._normalize_emoji_text("18px: A \u2639 \u263A == \U0001F642/\U0001F600 A"))
        demo_small.set_pos(0, y)
        y += self._emoji_font_small.get_line_height() + 12

        demo = lv.label(screen)
        demo.set_style_text_font(self._emoji_font, lv.PART.MAIN)
        demo.set_text(self._normalize_emoji_text("36px: ❤️ \U0001F929 \u2639/\u263A == \U0001F642/\U0001F600 A"))
        demo.set_pos(0, y)
        y += self._emoji_font.get_line_height() + 12
        print("height: " + str(self._emoji_font.get_line_height()))

        demo_big = lv.label(screen)
        demo_big.set_style_text_font(self._emoji_font_big, lv.PART.MAIN)
        demo_big.set_text(self._normalize_emoji_text("72px: A \u2639/\u263A == \U0001F642/\U0001F600 A"))
        demo_big.set_pos(0, y)
        y += self._emoji_font_big.get_line_height() + 12

        return y

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
            title.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
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
                    lbl.set_style_text_font(font, lv.PART.MAIN)
                    lbl.set_text(chr(cp))
                    lbl.set_pos(x, y)

                    x += 20
                    if x + 20 > screen.get_width():
                        x = 4
                        y += line_height

            y += line_height

        screen.set_height(y + 20)

    def _init_imagefont(self):
        self._emoji_map = self._build_emoji_map_from_png_dir()
        self._emoji_font_big = lv.imgfont_create(72, self._imgfont_path_cb, None)
        self._emoji_font_big.fallback = lv.font_montserrat_28
        self._emoji_font = lv.imgfont_create(36, self._imgfont_path_cb, None)
        self._emoji_font.fallback = lv.font_montserrat_28
        self._emoji_font_small = lv.imgfont_create(18, self._imgfont_path_cb, None)
        self._emoji_font_small.fallback = lv.font_montserrat_16

    def _build_emoji_map_from_png_dir(self):
        emoji_map = {}
        dir_path = None
        entries = None
        for candidate in EMOJI_PNG_DIR_CANDIDATES:
            entries = self._list_dir_names(candidate)
            if entries is not None:
                dir_path = candidate
                break

        if entries is None:
            print("showfonts: could not list emoji dir candidates (cwd=" + self._safe_getcwd() + ")")
            return emoji_map

        for name in entries:
            if not name.lower().endswith(".png"):
                continue

            codepoint_hex = name[:-4]
            try:
                codepoint = int(codepoint_hex, 16)
            except Exception:
                print("showfonts: skip non-hex emoji file: " + name)
                continue

            emoji_map[codepoint] = EMOJI_PNG_SRC_PREFIX + name

        print("showfonts: loaded " + str(len(emoji_map)) + " emoji png mappings from " + dir_path)
        return emoji_map

    def _list_dir_names(self, path):
        try:
            names = []
            for entry in os.ilistdir(path):
                if isinstance(entry, tuple):
                    names.append(entry[0])
                else:
                    names.append(entry)
            return names
        except Exception:
            pass

        try:
            return os.listdir(path)
        except Exception:
            return None

    def _safe_getcwd(self):
        try:
            return os.getcwd()
        except Exception:
            return "?"

    def _normalize_emoji_text(self, text):
        text = text.replace(chr(CP_VARIATION_SELECTOR_TEXT), "")
        text = text.replace(chr(CP_VARIATION_SELECTOR_EMOJI), "")
        return text

    def _init_ttf_font(self):
        try:
            self._ttf_font = lv.tiny_ttf_create_file("M:PrincessSofia-Regular.ttf", 72*2)
        except Exception:
            self._ttf_font = None

    def _imgfont_path_cb(self, font, unicode_cp, unicode_next, offset_y, user_data):
        if unicode_cp == CP_VARIATION_SELECTOR_TEXT or unicode_cp == CP_VARIATION_SELECTOR_EMOJI:
            offset_y.__dereference__(0)
            target_height = self._font_pixel_height(font)
            return self._get_empty_imgfont_src(target_height)

        if unicode_cp in self._emoji_map:
            offset_y.__dereference__(0)
            src = self._emoji_map[unicode_cp]
            target_height = self._font_pixel_height(font)
            return self._get_scaled_imgfont_src(src, target_height)

        self._log_unknown_emoji_codepoint(unicode_cp)
        return None

    def _log_unknown_emoji_codepoint(self, unicode_cp):
        if unicode_cp < UNKNOWN_EMOJI_LOG_THRESHOLD:
            return
        if unicode_cp in self._unknown_emoji_codepoints_logged:
            return

        self._unknown_emoji_codepoints_logged[unicode_cp] = True
        print("showfonts: unknown emoji codepoint 0x{:X}".format(unicode_cp))

    def _get_empty_imgfont_src(self, target_height):
        target_height = max(1, int(target_height))
        if target_height in self._imgfont_empty_src_cache:
            return self._imgfont_empty_src_cache[target_height]

        empty = lv.obj(lv.layer_top())
        try:
            empty.add_flag(lv.obj.FLAG.HIDDEN)
            empty.set_size(1, target_height)
            src = lv.snapshot_take(empty, lv.COLOR_FORMAT.ARGB8888)
        finally:
            empty.delete()

        self._imgfont_empty_src_cache[target_height] = src
        return src

    def _font_pixel_height(self, font):
        try:
            return max(1, int(font.get_line_height()))
        except Exception:
            pass
        try:
            return max(1, int(font.line_height))
        except Exception:
            return 1

    def _get_scaled_imgfont_src(self, src, target_height):
        key = (src, target_height)
        if key in self._imgfont_scaled_src_cache:
            return self._imgfont_scaled_src_cache[key]

        try:
            src_w, src_h = self._get_image_size(src)
            if src_h <= 0:
                return src

            target_width = max(1, round(src_w * target_height / src_h))
            scaled_src = self._render_scaled_image_src(src, target_width, target_height)
            if scaled_src is not None:
                self._imgfont_scaled_src_cache[key] = scaled_src
                return scaled_src
        except Exception:
            pass

        return src

    def _get_image_size(self, src):
        if src in self._imgfont_source_size_cache:
            return self._imgfont_source_size_cache[src]

        probe = lv.image(lv.layer_top())
        try:
            header = lv.image_header_t()
            probe.decoder_get_info(src, header)
            size = (int(header.w), int(header.h))
        finally:
            probe.delete()

        self._imgfont_source_size_cache[src] = size
        return size

    def _render_scaled_image_src(self, src, target_width, target_height):
        renderer = lv.image(lv.layer_top())
        try:
            renderer.add_flag(lv.obj.FLAG.HIDDEN)
            renderer.set_size(target_width, target_height)
            renderer.set_inner_align(lv.image.ALIGN.CONTAIN)
            renderer.set_src(src)

            return lv.snapshot_take(renderer, lv.COLOR_FORMAT.ARGB8888)
        finally:
            renderer.delete()
