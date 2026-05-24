from mpos import Activity
import lvgl as lv


class ShowFonts(Activity):
    def onCreate(self):
        screen = lv.obj()

        # Make the screen focusable so it can be scrolled with the arrow keys
        lv.group_get_default().add_obj(screen)

        self._emoji_map = {}
        self._emoji_font = None
        self._emoji_font_small = None
        self._imgfont_scaled_src_cache = {}
        self._imgfont_source_size_cache = {}
        self._init_imagefont()

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
        demo_small.set_text("16px: A 😀 A")
        demo_small.set_pos(0, y)
        y += self._emoji_font_small.get_line_height() + 12

        demo = lv.label(screen)
        demo.set_style_text_font(self._emoji_font, lv.PART.MAIN)
        demo.set_text("32px: A 😀 A")
        demo.set_pos(0, y)
        y += self._emoji_font.get_line_height() + 12
        print("height: " + str(self._emoji_font.get_line_height()))

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
        emoji_path = self._pick_emoji_png_path()
        self._emoji_map = {ord("😀"): emoji_path} if emoji_path else {}
        self._emoji_font = lv.imgfont_create(74, self._imgfont_path_cb, None)
        self._emoji_font.fallback = lv.font_montserrat_28
        self._emoji_font_small = lv.imgfont_create(28, self._imgfont_path_cb, None) # smaller than this results in a blank image?!
        self._emoji_font_small.fallback = lv.font_montserrat_16

    def _pick_emoji_png_path(self):
        candidates = [
            "M:apps/com.micropythonos.showfonts/res/mipmap-mdpi/icon_64x64.png",
            "M:/apps/com.micropythonos.showfonts/res/mipmap-mdpi/icon_64x64.png",
            "/apps/com.micropythonos.showfonts/res/mipmap-mdpi/icon_64x64.png",
            "M:apps/com.micropythonos.file_manager/res/mipmap-mdpi/icon_64x64.png",
            "M:/apps/com.micropythonos.file_manager/res/mipmap-mdpi/icon_64x64.png",
            "/home/user/projects/MicroPythonOS/claude/MicroPythonOS/internal_filesystem/apps/com.micropythonos.showfonts/res/mipmap-mdpi/icon_64x64.png",
        ]
        for path in candidates:
            try:
                probe = lv.image(lv.layer_top())
                probe.set_src(path)
                probe.delete()
                return path
            except Exception:
                pass
        return None

    def _imgfont_path_cb(self, font, unicode_cp, unicode_next, offset_y, user_data):
        if unicode_cp in self._emoji_map:
            offset_y.__dereference__(0)
            src = self._emoji_map[unicode_cp]
            target_height = self._font_pixel_height(font)
            return self._get_scaled_imgfont_src(src, target_height)
        return None

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

            scale = max(1, round(target_height * 256 / src_h))
            target_width = max(1, round(src_w * target_height / src_h))
            scaled_src = self._render_scaled_image_src(src, src_w, src_h, target_width, target_height, scale)
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

    def _render_scaled_image_src(self, src, src_w, src_h, target_width, target_height, scale):
        renderer = lv.image(lv.layer_top())
        try:
            renderer.add_flag(lv.obj.FLAG.HIDDEN)
            renderer.set_src(src)
            renderer.set_size(src_w, src_h)
            renderer.set_scale(scale)

            scaled_w = max(1, round(src_w * scale / 256))
            scaled_h = max(1, round(src_h * scale / 256))
            budget_w = max(src_w, target_width, scaled_w) + 8
            budget_h = max(src_h, target_height, scaled_h) + 8
            buffer_size = budget_w * budget_h * 4
            buffer = bytearray(buffer_size)
            tmp_dsc = lv.image_dsc_t()
            result = lv.snapshot_take_to_buf(renderer, lv.COLOR_FORMAT.ARGB8888, tmp_dsc, buffer, buffer_size)
            if result != lv.RESULT.OK:
                return None

            snapshot_width = int(tmp_dsc.header.w)
            snapshot_height = int(tmp_dsc.header.h)
            snapshot_stride = int(tmp_dsc.header.stride)
            if snapshot_width <= 0 or snapshot_height <= 0 or snapshot_stride < snapshot_width * 4:
                return None

            required_size = snapshot_stride * snapshot_height
            if required_size > len(buffer):
                return None

            if snapshot_width == target_width and snapshot_height == target_height and snapshot_stride == target_width * 4:
                data = buffer
            else:
                bounds = self._find_nontransparent_bounds_argb8888(
                    buffer,
                    snapshot_width,
                    snapshot_height,
                    snapshot_stride,
                )
                data = self._crop_argb8888_center(
                    buffer,
                    bounds[0],
                    bounds[1],
                    bounds[2],
                    bounds[3],
                    snapshot_stride,
                    target_width,
                    target_height,
                )

            return lv.image_dsc_t({
                "header": {
                    "magic": lv.IMAGE_HEADER_MAGIC,
                    "w": target_width,
                    "h": target_height,
                    "stride": target_width * 4,
                    "cf": lv.COLOR_FORMAT.ARGB8888,
                },
                "data_size": len(data),
                "data": data,
            })
        finally:
            renderer.delete()

    def _find_nontransparent_bounds_argb8888(
        self,
        src,
        src_width,
        src_height,
        src_stride,
    ):
        min_x = src_width
        min_y = src_height
        max_x = -1
        max_y = -1

        for y in range(src_height):
            row_start = y * src_stride
            for x in range(src_width):
                alpha_index = row_start + x * 4 + 3
                if src[alpha_index] == 0:
                    continue
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y

        if max_x < min_x or max_y < min_y:
            return (0, 0, src_width, src_height)

        return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)

    def _crop_argb8888_center(
        self,
        src,
        src_x,
        src_y,
        src_width,
        src_height,
        src_stride,
        dst_width,
        dst_height,
    ):
        dst = bytearray(dst_width * dst_height * 4)

        copy_width = min(src_width, dst_width)
        copy_height = min(src_height, dst_height)

        crop_src_x = src_x + max(0, (src_width - copy_width) // 2)
        crop_src_y = src_y + max(0, (src_height - copy_height) // 2)
        dst_x = max(0, (dst_width - copy_width) // 2)
        dst_y = max(0, (dst_height - copy_height) // 2)

        row_bytes = copy_width * 4
        for row in range(copy_height):
            src_index = (crop_src_y + row) * src_stride + crop_src_x * 4
            dst_index = ((dst_y + row) * dst_width + dst_x) * 4
            dst[dst_index:dst_index + row_bytes] = src[src_index:src_index + row_bytes]

        return dst
