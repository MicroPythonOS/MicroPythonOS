import lvgl as lv
import os


CP_VARIATION_SELECTOR_TEXT = 0xFE0E
CP_VARIATION_SELECTOR_EMOJI = 0xFE0F


class FontManager:
    _DEFAULT_SIZE = 12
    _DEBUG = False
    _UNKNOWN_EMOJI_LOG_THRESHOLD = 0x2300
    _EMOJI_PNG_DIR = "openmoji-72x72-color"
    _EMOJI_PNG_SRC_PREFIX = "M:apps/com.micropythonos.showfonts/assets/openmoji-72x72-color/"
    _EMOJI_PNG_DIR_CANDIDATES = (
        _EMOJI_PNG_DIR,
        "./" + _EMOJI_PNG_DIR,
        "assets/" + _EMOJI_PNG_DIR,
        "apps/com.micropythonos.showfonts/assets/" + _EMOJI_PNG_DIR,
        "/apps/com.micropythonos.showfonts/assets/" + _EMOJI_PNG_DIR,
        "M:apps/com.micropythonos.showfonts/assets/" + _EMOJI_PNG_DIR,
    )

    _emoji_map = None
    _builtin_font_records = None
    _composed_font_cache = {}
    _ttf_font_cache = {}
    _imgfont_scaled_src_cache = {}
    _imgfont_source_size_cache = {}
    _imgfont_empty_src_cache = {}
    _unknown_emoji_codepoints_logged = {}

    @classmethod
    def getFont(cls, size=None, ttf=None, family=None, emoji=True):
        target_size = cls._normalize_size(size)

        if ttf is None:
            base_font = cls._get_builtin_font(target_size, family)
        else:
            base_font = cls._get_ttf_font(ttf, target_size)

        if not emoji:
            return base_font

        return cls._get_composed_font(base_font)

    @classmethod
    def normalizeEmojiText(cls, text):
        text = text.replace(chr(CP_VARIATION_SELECTOR_TEXT), "")
        text = text.replace(chr(CP_VARIATION_SELECTOR_EMOJI), "")
        return text

    @classmethod
    def _normalize_size(cls, size):
        if size is None:
            return cls._DEFAULT_SIZE
        try:
            return max(1, int(size))
        except Exception:
            return cls._DEFAULT_SIZE

    @classmethod
    def _get_builtin_font(cls, size, family=None):
        builtin_fonts = cls._get_builtin_font_records()
        search_fonts = []

        if family is not None:
            for record in builtin_fonts:
                if record["family"] == family:
                    search_fonts.append(record)

        if not search_fonts:
            montserrat_fonts = []
            for record in builtin_fonts:
                if record["family"] == "Montserrat":
                    montserrat_fonts.append(record)
            search_fonts = montserrat_fonts if montserrat_fonts else builtin_fonts

        if search_fonts:
            best = search_fonts[0]
            best_key = (abs(best["size"] - size), 1 if best["size"] > size else 0)
            for candidate in search_fonts[1:]:
                key = (abs(candidate["size"] - size), 1 if candidate["size"] > size else 0)
                if key < best_key:
                    best_key = key
                    best = candidate
            return best["font"]
        fallback_records = cls._get_builtin_font_records()
        if fallback_records:
            return fallback_records[0]["font"]
        return lv.font_montserrat_12

    @classmethod
    def listFonts(cls):
        fonts = []
        for record in cls._get_builtin_font_records():
            composed_font = cls._get_composed_font(record["font"], record["size"])
            fonts.append(
                {
                    "name": "{} {}".format(record["family"], record["size"]),
                    "family": record["family"],
                    "size": record["size"],
                    "font": composed_font,
                    "base_font": record["font"],
                }
            )
        return fonts

    @classmethod
    def _get_builtin_font_records(cls):
        if cls._builtin_font_records is not None:
            return cls._builtin_font_records

        candidates = (
            ("Montserrat", 8, "font_montserrat_8"),
            ("Montserrat", 10, "font_montserrat_10"),
            ("Montserrat", 12, "font_montserrat_12"),
            ("Montserrat", 14, "font_montserrat_14"),
            ("Montserrat", 16, "font_montserrat_16"),
            ("Montserrat", 18, "font_montserrat_18"),
            ("Montserrat", 20, "font_montserrat_20"),
            ("Montserrat", 24, "font_montserrat_24"),
            ("Montserrat", 28, "font_montserrat_28"),
            ("Unscii", 8, "font_unscii_8"),
            ("Unscii", 16, "font_unscii_16"),
        )

        records = []
        for family, size, attr in candidates:
            if hasattr(lv, attr):
                records.append(
                    {
                        "family": family,
                        "size": size,
                        "font": getattr(lv, attr),
                    }
                )

        cls._builtin_font_records = records
        return cls._builtin_font_records

    @classmethod
    def _get_composed_font(cls, base_font, size=None):
        if base_font is None:
            return None

        font_id = cls._font_identity(base_font)
        emoji_size = size if size is not None else cls._font_pixel_height(base_font)
        cache_key = (font_id, int(emoji_size))
        if cache_key in cls._composed_font_cache:
            return cls._composed_font_cache[cache_key]

        emoji_font = cls._create_emoji_font(emoji_size)
        if emoji_font is None:
            return base_font

        try:
            # Do not mutate builtin font fallback: builtins may live in readonly memory.
            emoji_font.fallback = base_font
        except Exception as err:
            cls._debug("compose fallback set failed: " + repr(err))
            return base_font

        cls._composed_font_cache[cache_key] = emoji_font
        return emoji_font

    @classmethod
    def _font_identity(cls, font):
        try:
            return int(id(font))
        except Exception:
            return repr(font)

    @classmethod
    def _debug(cls, message):
        if cls._DEBUG:
            print("font_manager: " + message)

    @classmethod
    def _get_ttf_font(cls, ttf_path, size):
        key = (ttf_path, size)
        if key in cls._ttf_font_cache:
            return cls._ttf_font_cache[key]

        try:
            font = lv.tiny_ttf_create_file(ttf_path, size)
            cls._ttf_font_cache[key] = font
            return font
        except Exception:
            return cls._get_builtin_font(size)

    @classmethod
    def _create_emoji_font(cls, size):
        size = max(1, int(size))
        cls._ensure_emoji_map()

        try:
            return lv.imgfont_create(size, cls._imgfont_path_cb, None)
        except Exception:
            return None

    @classmethod
    def _ensure_emoji_map(cls):
        if cls._emoji_map is None:
            cls._emoji_map = cls._build_emoji_map_from_png_dir()

    @classmethod
    def _build_emoji_map_from_png_dir(cls):
        emoji_map = {}
        dir_path = None
        entries = None

        for candidate in cls._EMOJI_PNG_DIR_CANDIDATES:
            entries = cls._list_dir_names(candidate)
            if entries is not None:
                dir_path = candidate
                break

        if entries is None:
            print("font_manager: could not list emoji dir candidates (cwd=" + cls._safe_getcwd() + ")")
            return emoji_map

        for name in entries:
            if not name.lower().endswith(".png"):
                continue

            codepoint_hex = name[:-4]
            try:
                codepoint = int(codepoint_hex, 16)
            except Exception:
                print("font_manager: skip non-hex emoji file: " + name)
                continue

            emoji_map[codepoint] = cls._EMOJI_PNG_SRC_PREFIX + name

        print("font_manager: loaded " + str(len(emoji_map)) + " emoji png mappings from " + str(dir_path))
        return emoji_map

    @classmethod
    def _list_dir_names(cls, path):
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

    @classmethod
    def _safe_getcwd(cls):
        try:
            return os.getcwd()
        except Exception:
            return "?"

    @classmethod
    def _imgfont_path_cb(cls, font, unicode_cp, unicode_next, offset_y, user_data):
        if unicode_cp == CP_VARIATION_SELECTOR_TEXT or unicode_cp == CP_VARIATION_SELECTOR_EMOJI:
            offset_y.__dereference__(0)
            target_height = cls._font_pixel_height(font)
            return cls._get_empty_imgfont_src(target_height)

        if unicode_cp in cls._emoji_map:
            offset_y.__dereference__(0)
            src = cls._emoji_map[unicode_cp]
            target_height = cls._font_pixel_height(font)
            return cls._get_scaled_imgfont_src(src, target_height)

        cls._log_unknown_emoji_codepoint(unicode_cp)
        return None

    @classmethod
    def _log_unknown_emoji_codepoint(cls, unicode_cp):
        if unicode_cp < cls._UNKNOWN_EMOJI_LOG_THRESHOLD:
            return
        if unicode_cp in cls._unknown_emoji_codepoints_logged:
            return

        cls._unknown_emoji_codepoints_logged[unicode_cp] = True
        #print("font_manager: unknown emoji codepoint 0x{:X}".format(unicode_cp))

    @classmethod
    def _get_empty_imgfont_src(cls, target_height):
        target_height = max(1, int(target_height))
        if target_height in cls._imgfont_empty_src_cache:
            return cls._imgfont_empty_src_cache[target_height]

        empty = lv.obj(lv.layer_top())
        try:
            empty.add_flag(lv.obj.FLAG.HIDDEN)
            empty.set_size(1, target_height)
            src = lv.snapshot_take(empty, lv.COLOR_FORMAT.ARGB8888)
        finally:
            empty.delete()

        cls._imgfont_empty_src_cache[target_height] = src
        return src

    @classmethod
    def _font_pixel_height(cls, font):
        try:
            return max(1, int(font.get_line_height()))
        except Exception:
            pass
        try:
            return max(1, int(font.line_height))
        except Exception:
            return 1

    @classmethod
    def _get_scaled_imgfont_src(cls, src, target_height):
        key = (src, target_height)
        if key in cls._imgfont_scaled_src_cache:
            return cls._imgfont_scaled_src_cache[key]

        try:
            src_w, src_h = cls._get_image_size(src)
            if src_h <= 0:
                return src

            target_width = max(1, round(src_w * target_height / src_h))
            scaled_src = cls._render_scaled_image_src(src, target_width, target_height)
            if scaled_src is not None:
                cls._imgfont_scaled_src_cache[key] = scaled_src
                return scaled_src
        except Exception:
            pass

        return src

    @classmethod
    def _get_image_size(cls, src):
        if src in cls._imgfont_source_size_cache:
            return cls._imgfont_source_size_cache[src]

        probe = lv.image(lv.layer_top())
        try:
            header = lv.image_header_t()
            probe.decoder_get_info(src, header)
            size = (int(header.w), int(header.h))
        finally:
            probe.delete()

        cls._imgfont_source_size_cache[src] = size
        return size

    @classmethod
    def _render_scaled_image_src(cls, src, target_width, target_height):
        renderer = lv.image(lv.layer_top())
        try:
            renderer.add_flag(lv.obj.FLAG.HIDDEN)
            renderer.set_size(target_width, target_height)
            renderer.set_inner_align(lv.image.ALIGN.CONTAIN)
            renderer.set_src(src)

            return lv.snapshot_take(renderer, lv.COLOR_FORMAT.ARGB8888)
        finally:
            renderer.delete()
