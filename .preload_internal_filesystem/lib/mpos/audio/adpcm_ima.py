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


#@micropython.native
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


#@micropython.viper
def samples_per_block(block_align: int, channels: int) -> int:
    return 1 + (block_align - 4 * channels) * 2 // channels


#@micropython.native
def _read_s16_le(buf, off):
    raw = int.from_bytes(buf[off:off + 2], "little")
    if raw >= 0x8000:
        raw -= 0x10000
    return raw


#@micropython.native
def _write_s16_le(buf, off, val):
    buf[off] = val & 0xFF
    buf[off + 1] = (val >> 8) & 0xFF


#@micropython.native
def decode_block_into(data, channels, block_align, out, out_offset):
    """Decode one ADPCM-IMA block into the provided bytearray at out_offset."""
    ns_per_ch = samples_per_block(block_align, channels)

    preds = [0] * channels
    idxs = [0] * channels
    for ch in range(channels):
        off = ch * 4
        preds[ch] = max(-32768, min(32767, _read_s16_le(data, off)))
        idxs[ch] = max(0, min(88, data[off + 2]))

    for ch in range(channels):
        _write_s16_le(out, out_offset + ch * 2, preds[ch])

    dp = 4 * channels
    oi = [out_offset + ch * 2 + channels * 2 for ch in range(channels)]
    for _ in range((ns_per_ch - 1) // 8):
        for ch in range(channels):
            blk_start = dp
            dp += 4
            for bo in range(4):
                b = data[blk_start + bo]
                for nib in (b & 0x0F, b >> 4):
                    preds[ch], idxs[ch] = _expand(preds[ch], idxs[ch], nib)
                    _write_s16_le(out, oi[ch], preds[ch])
                    oi[ch] += channels * 2


#@micropython.native
def decode_block(data, channels, block_align):
    ns_per_ch = samples_per_block(block_align, channels)
    out = bytearray(ns_per_ch * channels * 2)
    decode_block_into(data, channels, block_align, out, 0)
    return out
