import math
import hashlib

try:
    import micropython
except ImportError:
    micropython = None


_alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~"
_alphabet_values = {c: i for i, c in enumerate(_alphabet)}


def _base83_decode(s):
    value = 0
    for c in s:
        value = value * 83 + _alphabet_values[c]
    return value


def _srgb_to_linear(value):
    v = value / 255.0
    if v <= 0.04045:
        return v / 12.92
    return math.pow((v + 0.055) / 1.055, 2.4)


def _linear_to_srgb(value):
    v = max(0.0, min(1.0, value))
    if v <= 0.0031308:
        return int(v * 12.92 * 255 + 0.5)
    return int((1.055 * math.pow(v, 1.0 / 2.4) - 0.055) * 255 + 0.5)


def _sign_pow(value, exp):
    if value < 0:
        return -math.pow(-value, exp)
    return math.pow(value, exp)


# ---------------------------------------------------------------------------
# 1) pure Python decoder
# ---------------------------------------------------------------------------

def decode_blurhash(blurhash, width, height, punch=1.0):
    if len(blurhash) < 6:
        raise ValueError("BlurHash too short")

    size_info = _base83_decode(blurhash[0])
    size_y = size_info // 9 + 1
    size_x = (size_info % 9) + 1

    quant_max = _base83_decode(blurhash[1])
    real_max = (quant_max + 1) / 166.0 * punch

    expected_len = 4 + 2 * size_x * size_y
    if len(blurhash) != expected_len:
        raise ValueError("Invalid BlurHash length")

    dc_value = _base83_decode(blurhash[2:6])
    colours = [
        (
            _srgb_to_linear(dc_value >> 16),
            _srgb_to_linear((dc_value >> 8) & 255),
            _srgb_to_linear(dc_value & 255),
        )
    ]

    for idx in range(1, size_x * size_y):
        ac = _base83_decode(blurhash[4 + idx * 2 : 4 + (idx + 1) * 2])
        colours.append(
            (
                _sign_pow((ac // (19 * 19) - 9) / 9.0, 2.0) * real_max,
                _sign_pow(((ac // 19) % 19 - 9) / 9.0, 2.0) * real_max,
                _sign_pow((ac % 19 - 9) / 9.0, 2.0) * real_max,
            )
        )

    pixels = []
    wf = float(width)
    hf = float(height)
    for y in range(height):
        row = []
        for x in range(width):
            pixel = [0.0, 0.0, 0.0]
            for j in range(size_y):
                for i in range(size_x):
                    basis = math.cos(math.pi * x * i / wf) * math.cos(math.pi * y * j / hf)
                    c = colours[i + j * size_x]
                    pixel[0] += c[0] * basis
                    pixel[1] += c[1] * basis
                    pixel[2] += c[2] * basis
            row.append(
                (
                    _linear_to_srgb(pixel[0]),
                    _linear_to_srgb(pixel[1]),
                    _linear_to_srgb(pixel[2]),
                )
            )
        pixels.append(row)
    return pixels


# ---------------------------------------------------------------------------
# 2) @micropython.native decoder
# ---------------------------------------------------------------------------

def _make_cos_table(dim, components):
    table = []
    dimf = float(dim)
    for y in range(dim):
        for j in range(components):
            table.append(math.cos(math.pi * y * j / dimf))
    return table


def decode_blurhash_native(blurhash, width, height, punch=1.0):
    if len(blurhash) < 6:
        raise ValueError("BlurHash too short")

    size_info = _base83_decode(blurhash[0])
    size_y = size_info // 9 + 1
    size_x = (size_info % 9) + 1

    quant_max = _base83_decode(blurhash[1])
    real_max = (quant_max + 1) / 166.0 * punch

    expected_len = 4 + 2 * size_x * size_y
    if len(blurhash) != expected_len:
        raise ValueError("Invalid BlurHash length")

    dc_value = _base83_decode(blurhash[2:6])
    colours = [
        (
            _srgb_to_linear(dc_value >> 16),
            _srgb_to_linear((dc_value >> 8) & 255),
            _srgb_to_linear(dc_value & 255),
        )
    ]

    for idx in range(1, size_x * size_y):
        ac = _base83_decode(blurhash[4 + idx * 2 : 4 + (idx + 1) * 2])
        colours.append(
            (
                _sign_pow((ac // (19 * 19) - 9) / 9.0, 2.0) * real_max,
                _sign_pow(((ac // 19) % 19 - 9) / 9.0, 2.0) * real_max,
                _sign_pow((ac % 19 - 9) / 9.0, 2.0) * real_max,
            )
        )

    cos_x = _make_cos_table(width, size_x)
    cos_y = _make_cos_table(height, size_y)

    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            pixel = [0.0, 0.0, 0.0]
            for j in range(size_y):
                cy = cos_y[y * size_y + j]
                c_base = j * size_x
                for i in range(size_x):
                    basis = cos_x[x * size_x + i] * cy
                    c = colours[c_base + i]
                    pixel[0] += c[0] * basis
                    pixel[1] += c[1] * basis
                    pixel[2] += c[2] * basis
            row.append(
                (
                    _linear_to_srgb(pixel[0]),
                    _linear_to_srgb(pixel[1]),
                    _linear_to_srgb(pixel[2]),
                )
            )
        pixels.append(row)
    return pixels


if micropython and hasattr(micropython, "native"):
    decode_blurhash_native = micropython.native(decode_blurhash_native)


# ---------------------------------------------------------------------------
# 3) @micropython.viper decoder  (fixed-point integer math)
# ---------------------------------------------------------------------------

_VIPER_SCALE = 256

# pre-built sRGB LUT: maps linear[0.._VIPER_SCALE) → sRGB 0..255
_vsrgb_lut = None


def _ensure_srgb_lut():
    global _vsrgb_lut
    if _vsrgb_lut is not None:
        return
    _vsrgb_lut = bytearray(_VIPER_SCALE)
    for i in range(_VIPER_SCALE):
        v = i / float(_VIPER_SCALE)
        _vsrgb_lut[i] = _linear_to_srgb(v)


def decode_blurhash_viper(blurhash, width, height, punch=1.0):
    _ensure_srgb_lut()
    scale = _VIPER_SCALE

    size_info = _base83_decode(blurhash[0])
    size_y = size_info // 9 + 1
    size_x = (size_info % 9) + 1

    quant_max = _base83_decode(blurhash[1])
    real_max = (quant_max + 1) / 166.0 * punch

    expected_len = 4 + 2 * size_x * size_y
    if len(blurhash) != expected_len:
        raise ValueError("Invalid BlurHash length")

    dc_value = _base83_decode(blurhash[2:6])
    dc_r = int(_srgb_to_linear(dc_value >> 16) * scale)
    dc_g = int(_srgb_to_linear((dc_value >> 8) & 255) * scale)
    dc_b = int(_srgb_to_linear(dc_value & 255) * scale)

    comp_count = size_x * size_y
    comps = bytearray(comp_count * 6)
    for idx in range(comp_count):
        off = idx * 6
        if idx == 0:
            comps[off] = dc_r & 255
            comps[off + 1] = (dc_r >> 8) & 255
            comps[off + 2] = dc_g & 255
            comps[off + 3] = (dc_g >> 8) & 255
            comps[off + 4] = dc_b & 255
            comps[off + 5] = (dc_b >> 8) & 255
        else:
            ac = _base83_decode(blurhash[4 + idx * 2 : 4 + (idx + 1) * 2])
            cr = int(
                _sign_pow((ac // (19 * 19) - 9) / 9.0, 2.0) * real_max * scale
            )
            cg = int(
                _sign_pow(((ac // 19) % 19 - 9) / 9.0, 2.0) * real_max * scale
            )
            cb = int(
                _sign_pow((ac % 19 - 9) / 9.0, 2.0) * real_max * scale
            )
            comps[off] = cr & 255
            comps[off + 1] = (cr >> 8) & 255
            comps[off + 2] = cg & 255
            comps[off + 3] = (cg >> 8) & 255
            comps[off + 4] = cb & 255
            comps[off + 5] = (cb >> 8) & 255

    wf = float(width)
    hf = float(height)
    cos_x_tab = bytearray(width * size_x * 2)
    for x in range(width):
        for i in range(size_x):
            val = int(math.cos(math.pi * x * i / wf) * scale)
            off = (x * size_x + i) * 2
            cos_x_tab[off] = val & 255
            cos_x_tab[off + 1] = (val >> 8) & 255

    cos_y_tab = bytearray(height * size_y * 2)
    for y in range(height):
        for j in range(size_y):
            val = int(math.cos(math.pi * y * j / hf) * scale)
            off = (y * size_y + j) * 2
            cos_y_tab[off] = val & 255
            cos_y_tab[off + 1] = (val >> 8) & 255

    return _viper_decode_impl(
        width, height, size_x, size_y, scale,
        comps, cos_x_tab, cos_y_tab, _vsrgb_lut,
    )


@micropython.viper
def _viper_decode_impl(
    width: int, height: int, size_x: int, size_y: int, scale: int,
    comps, cos_x_tab, cos_y_tab, srgb_lut,
):
    scale_sq = scale * scale
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            pr = 0
            pg = 0
            pb = 0
            for j in range(size_y):
                cy_idx = (y * size_y + j) * 2
                cy = int(cos_y_tab[cy_idx]) | (int(cos_y_tab[cy_idx + 1]) << 8)
                if cy & 0x8000:
                    cy = cy - 65536
                for i in range(size_x):
                    cx_idx = (x * size_x + i) * 2
                    cx = int(cos_x_tab[cx_idx]) | (int(cos_x_tab[cx_idx + 1]) << 8)
                    if cx & 0x8000:
                        cx = cx - 65536
                    basis = cx * cy
                    comp_idx = (j * size_x + i) * 6
                    cr = int(comps[comp_idx]) | (int(comps[comp_idx + 1]) << 8)
                    if cr & 0x8000:
                        cr = cr - 65536
                    cg = int(comps[comp_idx + 2]) | (int(comps[comp_idx + 3]) << 8)
                    if cg & 0x8000:
                        cg = cg - 65536
                    cb = int(comps[comp_idx + 4]) | (int(comps[comp_idx + 5]) << 8)
                    if cb & 0x8000:
                        cb = cb - 65536
                    pr += cr * basis
                    pg += cg * basis
                    pb += cb * basis
            pr = pr // scale_sq
            pg = pg // scale_sq
            pb = pb // scale_sq
            if pr < 0:
                pr = 0
            elif pr >= scale:
                pr = scale - 1
            if pg < 0:
                pg = 0
            elif pg >= scale:
                pg = scale - 1
            if pb < 0:
                pb = 0
            elif pb >= scale:
                pb = scale - 1
            row.append((int(srgb_lut[pr]), int(srgb_lut[pg]), int(srgb_lut[pb])))
        pixels.append(row)
    return pixels


# ---------------------------------------------------------------------------
# RGB565 conversion helpers
# ---------------------------------------------------------------------------

def _rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def pixels_to_rgb565(pixels):
    h = len(pixels)
    w = len(pixels[0])
    buf = bytearray(w * h * 2)
    stride = w * 2
    for y in range(h):
        row = pixels[y]
        base = y * stride
        for x in range(w):
            r, g, b = row[x]
            c = _rgb565(r, g, b)
            i = base + x * 2
            buf[i] = c & 0xFF
            buf[i + 1] = c >> 8
    return buf


def blurhash_to_image_dsc(blurhash, width, height):
    import lvgl as lv

    if not blurhash:
        return None, None
    try:
        pixels = decode_blurhash_native(blurhash, width, height)
    except Exception:
        return None, None
    buf = pixels_to_rgb565(pixels)
    stride = width * 2
    try:
        dsc = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": width,
                "h": height,
                "stride": stride,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": len(buf),
            "data": buf,
        })
    except Exception:
        dsc = lv.image_dsc_t()
        dsc.data = buf
        dsc.header.magic = lv.IMAGE_HEADER_MAGIC
        dsc.header.w = width
        dsc.header.h = height
        dsc.header.stride = stride
        dsc.header.cf = lv.COLOR_FORMAT.RGB565
        dsc.data_size = len(buf)
    return dsc, buf


# ---------------------------------------------------------------------------
# Fallback: SHA1-hash-based icon generator (moved from appstore.py)
# ---------------------------------------------------------------------------

def generate_raw_app_icon(app_name, size=64):
    import lvgl as lv

    digest = hashlib.sha1(app_name.encode()).digest()
    bg = _rgb565_from_bytes(digest[0], digest[1], digest[2])
    fg = _rgb565_from_bytes(digest[3], digest[4], digest[5])
    buf = _fill_rgb565_icon_buffer(size, digest[6:14], bg, fg)
    stride = size * 2
    try:
        dsc = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": size,
                "h": size,
                "stride": stride,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": len(buf),
            "data": buf,
        })
    except Exception:
        dsc = lv.image_dsc_t()
        dsc.data = buf
        dsc.header.magic = lv.IMAGE_HEADER_MAGIC
        dsc.header.w = size
        dsc.header.h = size
        dsc.header.stride = stride
        dsc.header.cf = lv.COLOR_FORMAT.RGB565
        dsc.data_size = len(buf)
    return dsc, buf


@micropython.viper
def _fill_rgb565_icon_buffer(size: int, bits, bg: int, fg: int):
    buf = bytearray(size * size * 2)
    cell = size // 8
    for row in range(8):
        b = int(bits[row])
        for col in range(8):
            color = fg if (b & (1 << col)) else bg
            low = color & 0xFF
            high = color >> 8
            for y in range(row * cell, (row + 1) * cell):
                base = y * size * 2
                for x in range(col * cell, (col + 1) * cell):
                    i = base + x * 2
                    buf[i] = low
                    buf[i + 1] = high
    return buf


def _rgb565_from_bytes(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
