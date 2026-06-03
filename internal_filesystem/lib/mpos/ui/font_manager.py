import lvgl as lv
import os


CP_VARIATION_SELECTOR_TEXT = 0xFE0E
CP_VARIATION_SELECTOR_EMOJI = 0xFE0F


class FontManager:
    _DEFAULT_SIZE = 12
    _DEBUG = False
    _UNKNOWN_EMOJI_LOG_THRESHOLD = 0x203C
    _EMOJI_TIERS = (
        {"max_height": 20, "dir": "20x20"},
        {"max_height": 9999, "dir": "56x56"},
    )

    _EMOJI_DIR_CANDIDATE_FORMATS = (
        "builtin/res/emojis/{dir}",
        "./builtin/res/emojis/{dir}",
        "M:builtin/res/emojis/{dir}",
    )

    # Multiple caches are intentional here: emoji rendering on ESP32 is very
    # expensive, so we avoid repeated filesystem scans, repeated image decode
    # probes, and repeated per-codepoint fallback walks.
    _emoji_maps = {}
    _builtin_font_records = None
    _composed_font_cache = {}
    _ttf_font_cache = {}
    _imgfont_scaled_src_cache = {}
    _imgfont_source_size_cache = {}
    _imgfont_empty_src_cache = {}
    _emoji_src_lookup_cache = {}
    _unknown_emoji_codepoints_logged = {}
    _emoji_similarity_group_members_by_cp = None

    # Paste/update emoji similarity groups here as CSV with header: group_id,emoji
    _EMOJI_SIMILARITY_GROUPS_CSV = """group_id,emoji
hearts,❤️
hearts,♥️
hearts,❣️
hearts,💞
hearts,💖
hearts,💗
hearts,💓
hearts,💘
hearts,💝
hearts,💕
hearts,💔
hearts,💙
hearts,💜
hearts,💚
hearts,💛
hearts,🖤
tears_laughing,😂
tears_laughing,🤣
good_hand,👍
good_hand,👏
good_hand,👌
good_hand,🙌
smile_grin,😀
smile_grin,😃
smile_beam,😁
smile_beam,😄
smile_love,😍
smile_love,😻
smile_love,😹
smile_love,😈
tongue_group,😋
tongue_group,😛
sad_cry,😢
sad_cry,😥
sad_cry,😪
sad_cry,😓
music_group,🎶
music_group,🎵
checkmarks,✅
checkmarks,✔️
exclamation,‼️
exclamation,❗
angry,🔴
angry,😡
angry,😤
flower_group,🌹
flower_group,🌸
flower_group,🌷
flower_group,🎊
flower_group,🌺
flower_group,🌼
flower_group,🌻
birthday_cakes,🎂
birthday_cakes,👑
"""

    @classmethod
    def getFont(cls, size=None, ttf=None, family=None, emoji=False):
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
    def listFonts(cls, emojis=False):
        fonts = []
        for record in cls._get_builtin_font_records():
            font = record["font"]
            if emojis:
                font = cls._get_composed_font(font)
            fonts.append(
                {
                    "name": "{} {}".format(record["family"], record["size"]),
                    "family": record["family"],
                    "size": record["size"],
                    "font": font,
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
            # Keep imgfont as primary and route unknown glyphs to the base font.
            # This avoids mutating builtin fonts, which may be readonly.
            emoji_font.fallback = base_font
            emoji_font.base_line = cls._font_base_line(base_font)
            emoji_font.underline_position = cls._font_underline_position(base_font)
            emoji_font.underline_thickness = cls._font_underline_thickness(base_font)
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

        cls._assert_ttf_exists(ttf_path)
        font = lv.tiny_ttf_create_file(ttf_path, size)
        cls._ttf_font_cache[key] = font
        return font

    @classmethod
    def _assert_ttf_exists(cls, ttf_path):
        path = ttf_path
        if isinstance(path, str) and path.startswith("M:"):
            path = path[2:]
        try:
            os.stat(path)
        except OSError:
            raise OSError("TTF file not found: {}".format(ttf_path))

    @classmethod
    def getEmojiCodepoints(cls):
        cls._ensure_emoji_maps()
        all_cps = set()
        for m in cls._emoji_maps.values():
            all_cps.update(m.keys())
        return sorted(all_cps)

    @classmethod
    def _create_emoji_font(cls, size):
        size = max(1, int(size))
        cls._ensure_emoji_maps()

        try:
            font = lv.imgfont_create(size, cls._imgfont_path_cb, None)
        except Exception:
            return None
        if font is None:
            return None

        # Push the same codepoint accept/exclude ranges that _get_emoji_src
        # checks down into the C-level imgfont. Once set, LVGL stops calling
        # our Python _imgfont_path_cb for codepoints that are guaranteed to
        # have no emoji glyph (ASCII, CJK, PUA, etc.) — turning the per-glyph
        # cost from "Python call + return" into a pair of int compares in C.
        # This is the actual fix for the scrolling slowdown: composed-font
        # text where most glyphs are non-emoji now stays in C end-to-end.
        try:
            cp_min, cp_max = cls._emoji_codepoint_bounds()
            lv.imgfont_set_range(font, cp_min, cp_max, 0xE000, 0xF8FF)
        except AttributeError:
            # Older LVGL build without lv_imgfont_set_range — that's OK, the
            # fast path is just a nice-to-have. Behaviour falls back to the
            # pre-patch composed-font path (correct, just slower).
            cls._debug("imgfont_set_range unavailable — emoji filter not applied")
        except Exception as err:
            cls._debug("imgfont_set_range failed: " + repr(err))

        return font

    @classmethod
    def _emoji_codepoint_bounds(cls):
        """Smallest / largest codepoint present across all loaded emoji maps.
        Recomputed on demand and cached — the maps are immutable after init.
        Falls back to a safe wide range if no emojis are loaded yet, so we
        never narrow the filter in a way that would hide future glyphs."""
        bounds = cls.__dict__.get("_emoji_cp_bounds")
        if bounds is not None:
            return bounds
        lo = None
        hi = None
        for emap in cls._emoji_maps.values():
            for cp in emap:
                if lo is None or cp < lo: lo = cp
                if hi is None or cp > hi: hi = cp
        if lo is None:
            # No emojis loaded — accept everything so behaviour matches the
            # unpatched code path. Caller should re-create the font once
            # maps are populated.
            return (0, 0xFFFFFFFF)
        bounds = (lo, hi)
        cls._emoji_cp_bounds = bounds
        return bounds

    @classmethod
    def _ensure_emoji_maps(cls):
        for tier in cls._EMOJI_TIERS:
            dir_name = tier["dir"]
            if dir_name not in cls._emoji_maps:
                cls._emoji_maps[dir_name] = cls._build_emoji_map_from_png_dir(dir_name)

    @classmethod
    def _emoji_src_prefix(cls, dir_name):
        return "M:builtin/res/emojis/" + dir_name + "/"

    @classmethod
    def _build_emoji_map_from_png_dir(cls, dir_name):
        emoji_map = {}
        dir_path = None
        entries = None

        for fmt in cls._EMOJI_DIR_CANDIDATE_FORMATS:
            candidate = fmt.format(dir=dir_name)
            entries = cls._list_dir_names(candidate)
            if entries is not None:
                dir_path = candidate
                break

        if entries is None:
            print("font_manager: could not list emoji dir '{}' (cwd={})".format(dir_name, cls._safe_getcwd()))
            return emoji_map

        prefix = cls._emoji_src_prefix(dir_name)
        for name in entries:
            if not name.lower().endswith(".png"):
                continue

            name_without_ext = name[:-4]
            is_fe0f_variant = name_without_ext.endswith("-FE0F")
            codepoint_hex = name_without_ext[:-5] if is_fe0f_variant else name_without_ext
            try:
                codepoint = int(codepoint_hex, 16)
            except Exception:
                print("font_manager: skip non-hex emoji file: " + name)
                continue

            if not is_fe0f_variant and codepoint in emoji_map:
                continue

            emoji_map[codepoint] = prefix + name

        print("font_manager: loaded {} emoji png mappings from {}".format(len(emoji_map), dir_path))
        return emoji_map

    @classmethod
    def _get_emoji_src(cls, codepoint, target_height):
        if codepoint < cls._UNKNOWN_EMOJI_LOG_THRESHOLD:
            return None
        if 0xE000 <= codepoint <= 0xF8FF:
            return None

        cls._ensure_emoji_maps()

        preferred_dir = cls._get_preferred_emoji_dir(target_height)
        cache_key = (int(codepoint), preferred_dir)
        if cache_key in cls._emoji_src_lookup_cache:
            return cls._emoji_src_lookup_cache[cache_key]

        src = cls._lookup_emoji_src_for_codepoint(codepoint, preferred_dir)
        if src is not None:
            cls._emoji_src_lookup_cache[cache_key] = src
            return src

        cls._ensure_emoji_similarity_groups()
        similar_codepoints = cls._emoji_similarity_group_members_by_cp.get(codepoint)
        if similar_codepoints is None:
            cls._emoji_src_lookup_cache[cache_key] = None
            return None

        for fallback_cp in similar_codepoints:
            if fallback_cp == codepoint:
                continue
            src = cls._lookup_emoji_src_for_codepoint(fallback_cp, preferred_dir)
            if src is not None:
                cls._debug(
                    "emoji fallback 0x{:X} -> 0x{:X}".format(codepoint, fallback_cp)
                )
                cls._emoji_src_lookup_cache[cache_key] = src
                return src

        cls._emoji_src_lookup_cache[cache_key] = None
        return None

    @classmethod
    def _get_preferred_emoji_dir(cls, target_height):
        for tier in cls._EMOJI_TIERS:
            if target_height <= tier["max_height"]:
                return tier["dir"]
        return None

    @classmethod
    def _lookup_emoji_src_for_codepoint(cls, codepoint, preferred_dir=None):
        if preferred_dir is not None:
            preferred_map = cls._emoji_maps.get(preferred_dir, {})
            if codepoint in preferred_map:
                return preferred_map[codepoint]

            # For large emoji requests, explicitly fall back to 20x20.
            # The renderer will upscale it to target_height.
            if preferred_dir == "56x56":
                fallback_map = cls._emoji_maps.get("20x20", {})
                if codepoint in fallback_map:
                    return fallback_map[codepoint]

        for tier in cls._EMOJI_TIERS:
            dir_name = tier["dir"]
            emoji_map = cls._emoji_maps.get(dir_name, {})
            if codepoint in emoji_map:
                return emoji_map[codepoint]
        return None

    @classmethod
    def _ensure_emoji_similarity_groups(cls):
        if cls._emoji_similarity_group_members_by_cp is not None:
            return

        groups = {}
        for raw_line in cls._EMOJI_SIMILARITY_GROUPS_CSV.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split(",", 1)
            if len(parts) != 2:
                continue

            group_id = parts[0].strip()
            emoji_text = parts[1].strip()
            if group_id == "group_id" and emoji_text == "emoji":
                continue

            emoji_text = cls.normalizeEmojiText(emoji_text)
            if len(emoji_text) != 1:
                continue

            codepoint = ord(emoji_text)
            group = groups.get(group_id)
            if group is None:
                group = []
                groups[group_id] = group

            if codepoint not in group:
                group.append(codepoint)

        members_by_cp = {}
        for group_members in groups.values():
            members_tuple = tuple(group_members)
            for codepoint in group_members:
                members_by_cp[codepoint] = members_tuple

        cls._emoji_similarity_group_members_by_cp = members_by_cp

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
        baseline = cls._font_base_line(font)
        if unicode_cp == CP_VARIATION_SELECTOR_TEXT or unicode_cp == CP_VARIATION_SELECTOR_EMOJI:
            offset_y.__dereference__(-baseline)
            return cls._get_empty_imgfont_src(cls._font_pixel_height(font))

        src = cls._get_emoji_src(unicode_cp, cls._font_pixel_height(font))
        if src is not None:
            offset_y.__dereference__(-baseline)
            return cls._get_scaled_imgfont_src(src, cls._font_pixel_height(font))

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

        buf = bytearray(4)
        dsc = cls._build_argb8888_dsc(buf, 1, target_height)

        cls._imgfont_empty_src_cache[target_height] = dsc
        return dsc

    @classmethod
    def _build_argb8888_dsc(cls, buf, width, height):
        width = int(width)
        height = int(height)
        stride = width * 4
        try:
            return lv.image_dsc_t(
                {
                    "header": {
                        "magic": lv.IMAGE_HEADER_MAGIC,
                        "w": width,
                        "h": height,
                        "stride": stride,
                        "cf": lv.COLOR_FORMAT.ARGB8888,
                    },
                    "data_size": len(buf),
                    "data": buf,
                }
            )
        except Exception:
            dsc = lv.image_dsc_t()
            dsc.data = buf
            dsc.header.w = width
            dsc.header.h = height
            dsc.header.cf = lv.COLOR_FORMAT.ARGB8888
            return dsc

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
    def _font_base_line(cls, font):
        try:
            return int(font.base_line)
        except Exception:
            return 0

    @classmethod
    def _font_underline_position(cls, font):
        try:
            return int(font.underline_position)
        except Exception:
            return 0

    @classmethod
    def _font_underline_thickness(cls, font):
        try:
            return int(font.underline_thickness)
        except Exception:
            return 0

    @classmethod
    def _get_scaled_imgfont_src(cls, src, target_height):
        key = (src, target_height)
        cached = cls._imgfont_scaled_src_cache.get(key)
        if cached is not None:
            return cached[0]

        try:
            src_w, src_h = cls._get_image_size(src)
            if src_h <= 0:
                return src

            if target_height == src_h and target_height == src_w:
                cls._imgfont_scaled_src_cache[key] = (src, None)
                return src

            target_width = max(1, round(src_w * target_height / src_h))
            dsc, buf = cls._render_scaled_image_src(
                src, src_w, src_h, target_width, target_height
            )
            if dsc is not None:
                cls._imgfont_scaled_src_cache[key] = (dsc, buf)
                return dsc
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
    def _render_scaled_image_src(cls, src, src_w, src_h, target_width, target_height):
        renderer = lv.image(lv.layer_top())
        try:
            renderer.add_flag(lv.obj.FLAG.HIDDEN)
            renderer.set_size(src_w, src_h)
            renderer.set_inner_align(lv.image.ALIGN.CENTER)
            renderer.set_src(src)

            bpp = 4
            src_buf = bytearray(src_w * src_h * bpp)
            src_dsc = lv.image_dsc_t()
            lv.snapshot_take_to_buf(
                renderer, lv.COLOR_FORMAT.ARGB8888, src_dsc, src_buf, len(src_buf)
            )

            if int(src_dsc.header.w) <= 0 or int(src_dsc.header.h) <= 0:
                return None, None

            if target_width == src_w and target_height == src_h:
                return src_dsc, src_buf

            buf = bytearray(target_width * target_height * bpp)
            for y in range(target_height):
                src_y = (y * src_h) // target_height
                src_row = src_y * src_w
                dst_row = y * target_width
                for x in range(target_width):
                    src_x = (x * src_w) // target_width
                    src_idx = (src_row + src_x) * bpp
                    dst_idx = (dst_row + x) * bpp
                    buf[dst_idx] = src_buf[src_idx]
                    buf[dst_idx + 1] = src_buf[src_idx + 1]
                    buf[dst_idx + 2] = src_buf[src_idx + 2]
                    buf[dst_idx + 3] = src_buf[src_idx + 3]

            dsc = cls._build_argb8888_dsc(buf, target_width, target_height)

            return dsc, buf
        finally:
            renderer.delete()
