from mpos import Activity
import lvgl as lv
import time

from mpos import DisplayMetrics, FontManager


class ShowFonts(Activity):
    _BASE_GLYPH_SCAN_RANGES = (
        (0x20, 0x7F),
        (0xA0, 0x180),
        (0x2000, 0x2070),
        (0x20A0, 0x20D0),
        (0x2100, 0x2150),
        (0x2190, 0x2200),
        (0x2200, 0x2300),
        (0x2300, 0x2400),
        (0x2460, 0x2500),
        (0x25A0, 0x2600),
        (0x2600, 0x2700),
        (0x2B00, 0x2C00),
        (0xF000, 0xF800),
    )

    def _now_ms(self):
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)

    def _elapsed_ms(self, start_ms):
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(self._now_ms(), start_ms)
        return self._now_ms() - start_ms

    def _log_timing(self, label, start_ms):
        print("[showfonts][timing] {}: {} ms".format(label, self._elapsed_ms(start_ms)))

    def _build_glyph_text(self, lookup_font, emoji):
        cache_key = (id(lookup_font), bool(emoji))
        cache = getattr(self, "_glyph_text_cache", None)
        if cache is not None and cache_key in cache:
            return cache[cache_key]

        dsc = lv.font_glyph_dsc_t()
        parts = []

        scan_start = self._now_ms()
        for start_cp, end_cp in self._BASE_GLYPH_SCAN_RANGES:
            for cp in range(start_cp, end_cp):
                if lookup_font.get_glyph_dsc(lookup_font, dsc, cp, cp):
                    parts.append(chr(cp))
        self._log_timing("addAllGlyphs/base glyph scan", scan_start)

        if emoji:
            emoji_start = self._now_ms()
            emoji_cps = FontManager.getEmojiCodepoints()
            for cp in emoji_cps:
                parts.append(chr(cp))
            self._log_timing("addAllGlyphs/emoji append", emoji_start)

        join_start = self._now_ms()
        alltext = " ".join(parts)
        self._log_timing("addAllGlyphs/join", join_start)
        print("[showfonts][timing] addAllGlyphs/glyph count: {}".format(len(parts)))

        if cache is None:
            self._glyph_text_cache = {}
            cache = self._glyph_text_cache
        cache[cache_key] = alltext
        return alltext

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        #screen.set_style_margin_all(DisplayMetrics.pct_of_width(1), lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self.setContentView(screen)

    def onResume(self, screen):
        title = lv.label(screen)
        title.set_text("ShowFonts")

        resume_start = self._now_ms()

        emojilabel = lv.label(screen)
        emojifont = FontManager.getFont(size=16, emoji=True)
        print("emoji font height: ", emojifont.get_line_height()) # 16 gives height 20
        emojilabel.set_style_text_font(emojifont, lv.PART.MAIN)
        text = "😊 "
        text += "👍 👍🏻" # neutral thumbs up, light thumbs up
        text += "🤦 🤦🏻 🤦‍♀️ 🤦🏻‍♀️" # neutral facepalm, light facepalm, neutral woman facepalm, light woman facepalm
        emojilabel.set_text(text)

        emojilabel2 = lv.label(screen)
        emojifont2 = FontManager.getFont(size=30, emoji=True) # 32 givs height 33 is the maximum because Montserrat 28 is the maximum (TTF can go bigger)
        print("emoji2 font height: ", emojifont2.get_line_height())
        emojilabel2.set_style_text_font(emojifont2, lv.PART.MAIN)
        text = "test 👍 👍🏻" # neutral thumbs up, light thumbs up
        text += "🤦 🤦🏻 🤦‍♀️ 🤦🏻‍♀️" # neutral facepalm, light facepalm, neutral woman facepalm, light woman facepalm
        emojilabel2.set_text(text)

        self.addAllFontsTitles(screen)
        self._log_timing("addAllFontsTitles", resume_start)

        glyphs_start = self._now_ms()
        self.addAllGlyphs(screen)
        self._log_timing("addAllGlyphs", glyphs_start)
        self._log_timing("onResume total", resume_start)
        #lv.log_register_print_cb(ShowFonts.log_callback) # Show FPS to demonstrate that emoji fonts are 3-4x slower

    def onPause(self, screen): # Activity goes background
        #lv.log_register_print_cb(None)
        pass

    def addAllFontsTitles(self, screen):
        section_start = self._now_ms()
        import os
        ttf_start = self._now_ms()
        mydir = os.path.dirname(os.path.abspath(__file__))
        self._ttf_font = FontManager.getFont(size=42, ttf=f"M:{mydir}/Rancourt-SmallCaps.ttf", emoji=True)
        self._log_timing("addAllFontsTitles/getFont TTF", ttf_start)
        #self._ttf_font56 = FontManager.getFont(size=56, ttf=f"M:{mydir}/Rancourt-SmallCaps.ttf")
        #self._ttf_font72 = FontManager.getFont(size=72, ttf=f"M:{mydir}/Rancourt-SmallCaps.ttf")
        #fonts.append((self._ttf_font56, "TTF Rancourt 56"))
        #fonts.append((self._ttf_font72, "TTF Rancourt 72"))
        title = lv.label(screen)
        self.labelSelectable(title)
        title.set_width(lv.pct(99))
        title.set_style_text_font(self._ttf_font, lv.PART.MAIN)
        title.set_text("Rancourt 42 TTF test with minimal glyphs 👍")

        listfonts_start = self._now_ms()
        fonts = FontManager.listFonts()
        self._log_timing("addAllFontsTitles/listFonts", listfonts_start)

        render_start = self._now_ms()
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
                "{}: ABC 123 xyz !@#$%^&*( {} {} ₿ {} {} {} 丯 丰 {} {}".format(
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
        self._log_timing("addAllFontsTitles/render labels", render_start)
        self._log_timing("addAllFontsTitles total", section_start)


    def addAllGlyphs(self, screen, emoji=True):
        section_start = self._now_ms()

        getfont_start = self._now_ms()
        display_font = FontManager.getFont(size=16, family="Montserrat", emoji=emoji)
        lookup_font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        self._log_timing("addAllGlyphs/getFont", getfont_start)
        name = "Montserrat 16"

        title = lv.label(screen)
        title.set_text(name)
        title.set_style_text_font(display_font, lv.PART.MAIN)

        font_height = display_font.get_line_height()
        print("font_height: ", font_height)
        lbl = lv.label(screen)
        lbl.set_width(lv.pct(99))
        lbl.set_style_text_font(display_font, lv.PART.MAIN)
        alltext = self._build_glyph_text(lookup_font, emoji)

        set_text_start = self._now_ms()
        lbl.set_text(alltext)
        self._log_timing("addAllGlyphs/set_text", set_text_start)
        self.labelSelectable(lbl)
        self._log_timing("addAllGlyphs total", section_start)

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

    @staticmethod
    # Custom log callback to capture FPS
    def log_callback(level, log_str):
        # Convert log_str to string if it's a bytes object
        log_str = log_str.decode() if isinstance(log_str, bytes) else log_str
        # Optional: Print for debugging
        # print(f"Level: {level}, Log: {log_str}")
        # Log message format: "sysmon: 25 FPS (refr_cnt: 8 | redraw_cnt: 1), ..."
        if "sysmon:" in log_str and "FPS" in log_str:
            try:
                # Extract FPS value (e.g., "25" from "sysmon: 25 FPS ...")
                fps_part = log_str.split("FPS")[0].split("sysmon:")[1].strip()
                print(f"Current FPS: {fps_part}")
            except (IndexError, ValueError):
                pass
