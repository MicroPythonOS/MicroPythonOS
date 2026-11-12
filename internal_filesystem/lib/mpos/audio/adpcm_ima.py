# IMA ADPCM decoder for MicroPython

import micropython

_STEP_TABLE = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13900,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
)

_INDEX_TABLE = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)

# Byte copies of the tables for the viper loop: indexing a tuple there boxes
# every lookup, and decoding 4KB of audio does 8000 of them. This is the same
# table, just readable from a pointer.
_STEP_LE = bytes([byte for value in _STEP_TABLE for byte in (value & 0xFF, value >> 8)])
_INDEX_BIAS = bytes([value + 1 for value in _INDEX_TABLE])


@micropython.native
def _expand(predictor, step_index, nibble):
    step = _STEP_TABLE[step_index]
    diff = ((nibble & 7) * 2 + 1) * step >> 3
    if nibble & 8:
        predictor -= diff
    else:
        predictor += diff
    predictor = max(-32768, min(32767, predictor))
    step_index += _INDEX_TABLE[nibble]
    step_index = max(0, min(88, step_index))
    return predictor, step_index


@micropython.viper
def samples_per_block(block_align: int, channels: int) -> int:
    return 1 + (block_align - 4 * channels) * 2 // channels


@micropython.native
def _read_s16_le(buf, off):
    raw = int.from_bytes(buf[off:off + 2], "little")
    if raw >= 0x8000:
        raw -= 0x10000
    return raw


@micropython.native
def _write_s16_le(buf, off, val):
    buf[off] = val & 0xFF
    buf[off + 1] = (val >> 8) & 0xFF


@micropython.viper
def _decode_mono_into(src, block_align: int, dst, out_offset: int) -> int:
    """Decode a mono block; returns how many frames were written."""
    steps = ptr8(_STEP_LE)
    indexes = ptr8(_INDEX_BIAS)
    s = ptr8(src)
    d = ptr8(dst)
    frames = 1 + (block_align - 4) * 2
    predictor = s[0] | (s[1] << 8)
    if predictor > 32767:
        predictor -= 65536
    step_index = s[2]
    if step_index > 88:
        step_index = 88
    o = out_offset
    d[o] = predictor & 0xFF
    d[o + 1] = (predictor >> 8) & 0xFF
    o += 2
    p = 4
    written = 1
    while written < frames:
        value = s[p]
        p += 1
        shift = 0
        while shift < 8:
            nibble = (value >> shift) & 15
            step = steps[step_index * 2] | (steps[step_index * 2 + 1] << 8)
            diff = (((nibble & 7) * 2 + 1) * step) >> 3
            if nibble & 8:
                predictor -= diff
            else:
                predictor += diff
            if predictor > 32767:
                predictor = 32767
            elif predictor < -32768:
                predictor = -32768
            step_index += indexes[nibble] - 1
            if step_index < 0:
                step_index = 0
            elif step_index > 88:
                step_index = 88
            d[o] = predictor & 0xFF
            d[o + 1] = (predictor >> 8) & 0xFF
            o += 2
            shift += 4
        written += 2
    return frames


@micropython.viper
def _decode_stereo_into(src, block_align: int, dst, out_offset: int) -> int:
    """Decode a stereo block; returns how many frames were written."""
    steps = ptr8(_STEP_LE)
    indexes = ptr8(_INDEX_BIAS)
    s = ptr8(src)
    d = ptr8(dst)
    frames = 1 + (block_align - 8)
    predictor0 = s[0] | (s[1] << 8)
    if predictor0 > 32767:
        predictor0 -= 65536
    index0 = s[2]
    if index0 > 88:
        index0 = 88
    predictor1 = s[4] | (s[5] << 8)
    if predictor1 > 32767:
        predictor1 -= 65536
    index1 = s[6]
    if index1 > 88:
        index1 = 88
    o0 = out_offset
    o1 = out_offset + 2
    d[o0] = predictor0 & 0xFF
    d[o0 + 1] = (predictor0 >> 8) & 0xFF
    d[o1] = predictor1 & 0xFF
    d[o1 + 1] = (predictor1 >> 8) & 0xFF
    o0 += 4
    o1 += 4
    # Each eight-frame group is four bytes for the left channel followed by
    # four for the right, not alternating bytes.
    p = 8
    written = 1
    while written < frames:
        nibbles = 0
        while nibbles < 4:
            value = s[p]
            p += 1
            shift = 0
            while shift < 8:
                nibble = (value >> shift) & 15
                step = steps[index0 * 2] | (steps[index0 * 2 + 1] << 8)
                diff = (((nibble & 7) * 2 + 1) * step) >> 3
                if nibble & 8:
                    predictor0 -= diff
                else:
                    predictor0 += diff
                if predictor0 > 32767:
                    predictor0 = 32767
                elif predictor0 < -32768:
                    predictor0 = -32768
                index0 += indexes[nibble] - 1
                if index0 < 0:
                    index0 = 0
                elif index0 > 88:
                    index0 = 88
                d[o0] = predictor0 & 0xFF
                d[o0 + 1] = (predictor0 >> 8) & 0xFF
                o0 += 4
                shift += 4
            nibbles += 1
        nibbles = 0
        while nibbles < 4:
            value = s[p]
            p += 1
            shift = 0
            while shift < 8:
                nibble = (value >> shift) & 15
                step = steps[index1 * 2] | (steps[index1 * 2 + 1] << 8)
                diff = (((nibble & 7) * 2 + 1) * step) >> 3
                if nibble & 8:
                    predictor1 -= diff
                else:
                    predictor1 += diff
                if predictor1 > 32767:
                    predictor1 = 32767
                elif predictor1 < -32768:
                    predictor1 = -32768
                index1 += indexes[nibble] - 1
                if index1 < 0:
                    index1 = 0
                elif index1 > 88:
                    index1 = 88
                d[o1] = predictor1 & 0xFF
                d[o1 + 1] = (predictor1 >> 8) & 0xFF
                o1 += 4
                shift += 4
            nibbles += 1
        written += 8
    return frames


@micropython.native
def _decode_block_py(data, channels, block_align, out, out_offset):
    """Reference decoder: plain Python, used when viper is not in effect.

    CI comments out the `@micropython.viper` decorators so the test runner can
    execute every module as ordinary Python; the pointer builtins the fast path
    relies on do not exist then, so this implementation is what runs there.
    """
    ns_per_ch = samples_per_block(block_align, channels)
    preds = [0] * channels
    idxs = [0] * channels
    for ch in range(channels):
        off = ch * 4
        preds[ch] = _read_s16_le(data, off)
        idxs[ch] = max(0, min(88, data[off + 2]))
    for ch in range(channels):
        _write_s16_le(out, out_offset + ch * 2, preds[ch])
    dp = 4 * channels
    oi = [out_offset + ch * 2 + channels * 2 for ch in range(channels)]
    for _ in range((ns_per_ch - 1) // 8):
        for ch in range(channels):
            start = dp
            dp += 4
            for byte_offset in range(4):
                value = data[start + byte_offset]
                for nibble in (value & 0x0F, value >> 4):
                    preds[ch], idxs[ch] = _expand(preds[ch], idxs[ch], nibble)
                    _write_s16_le(out, oi[ch], preds[ch])
                    oi[ch] += channels * 2


@micropython.viper
def _viper_probe(buf) -> int:
    return ptr8(buf)[0]


def _viper_available():
    try:
        return _viper_probe(bytearray(1)) == 0
    except Exception:
        return False


_VIPER = _viper_available()


@micropython.native
def decode_block_into(data, channels, block_align, out, out_offset):
    """Decode one ADPCM-IMA block into the provided bytearray at out_offset."""
    frames = 1 + (block_align - 4 * channels) * 2 // channels
    if len(data) < block_align or out_offset + frames * channels * 2 > len(out):
        raise IndexError("truncated IMA block")
    if not _VIPER:
        _decode_block_py(data, channels, block_align, out, out_offset)
    elif channels == 1:
        _decode_mono_into(data, block_align, out, out_offset)
    else:
        _decode_stereo_into(data, block_align, out, out_offset)


@micropython.native
def decode_block(data, channels, block_align):
    ns_per_ch = samples_per_block(block_align, channels)
    out = bytearray(ns_per_ch * channels * 2)
    decode_block_into(data, channels, block_align, out, 0)
    return out
