# MP3 helpers: stream info parsing and decoding through the native mp3dec module.
#
# The header parser is plain Python so metadata can be read without decoding
# (AudioManager needs the sample rate before it opens I2S, and the music player
# shows the duration).

_MPEG1_BITRATES = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_MPEG2_BITRATES = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_MPEG1_RATES = (44100, 48000, 32000)
_MPEG2_RATES = (22050, 24000, 16000)
_MPEG25_RATES = (11025, 12000, 8000)

_HEAD_READ = 32 * 1024


def _id3v2_size(header):
    if len(header) < 10 or header[0:3] != b"ID3":
        return 0
    size = (
        ((header[6] & 0x7F) << 21)
        | ((header[7] & 0x7F) << 14)
        | ((header[8] & 0x7F) << 7)
        | (header[9] & 0x7F)
    )
    total = 10 + size
    if header[5] & 0x10:  # footer present
        total += 10
    return total


def _parse_header(buf, offset):
    if offset < 0 or offset + 4 > len(buf):
        return None
    b0 = buf[offset]
    b1 = buf[offset + 1]
    b2 = buf[offset + 2]
    b3 = buf[offset + 3]
    if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
        return None
    version_bits = (b1 >> 3) & 0x3
    layer_bits = (b1 >> 1) & 0x3
    if version_bits == 1 or layer_bits != 1:  # reserved version, or not Layer III
        return None
    bitrate_index = (b2 >> 4) & 0xF
    rate_index = (b2 >> 2) & 0x3
    if bitrate_index in (0, 15) or rate_index == 3:
        return None
    if version_bits == 3:
        bitrate_kbps = _MPEG1_BITRATES[bitrate_index]
        sample_rate = _MPEG1_RATES[rate_index]
        samples_per_frame = 1152
    elif version_bits == 2:
        bitrate_kbps = _MPEG2_BITRATES[bitrate_index]
        sample_rate = _MPEG2_RATES[rate_index]
        samples_per_frame = 576
    else:
        bitrate_kbps = _MPEG2_BITRATES[bitrate_index]
        sample_rate = _MPEG25_RATES[rate_index]
        samples_per_frame = 576
    padding = (b2 >> 1) & 0x1
    frame_bytes = (samples_per_frame // 8) * bitrate_kbps * 1000 // sample_rate + padding
    return {
        "version_bits": version_bits,
        "layer": 3,
        "bitrate_kbps": bitrate_kbps,
        "sample_rate": sample_rate,
        "samples_per_frame": samples_per_frame,
        "frame_bytes": frame_bytes,
        "channels": 1 if (b3 >> 6) == 3 else 2,
    }


def _same_stream(first, second):
    return (
        second is not None
        and first["version_bits"] == second["version_bits"]
        and first["sample_rate"] == second["sample_rate"]
        and first["channels"] == second["channels"]
    )


def _find_frame(buf, start=0):
    limit = len(buf) - 4
    offset = start
    while offset <= limit:
        if buf[offset] == 0xFF and (buf[offset + 1] & 0xE0) == 0xE0:
            info = _parse_header(buf, offset)
            if info is not None:
                following = offset + info["frame_bytes"]
                if following + 4 > len(buf):
                    return offset, info
                if _same_stream(info, _parse_header(buf, following)):
                    return offset, info
        offset += 1
    return None, None


def _xing_frames(buf, frame_start, info):
    """Return (frame_count, byte_count, vbr) for a Xing/Info or VBRI header."""
    mono = info["channels"] == 1
    if info["version_bits"] == 3:
        side_info = 17 if mono else 32
    else:
        side_info = 9 if mono else 17
    offset = frame_start + 4 + side_info
    if offset + 8 <= len(buf):
        tag = buf[offset:offset + 4]
        if tag == b"Xing" or tag == b"Info":
            flags = int.from_bytes(buf[offset + 4:offset + 8], "big")
            frames = None
            byte_count = None
            if flags & 0x1 and offset + 12 <= len(buf):
                frames = int.from_bytes(buf[offset + 8:offset + 12], "big")
            if flags & 0x2 and offset + 16 <= len(buf):
                byte_count = int.from_bytes(buf[offset + 12:offset + 16], "big")
            return frames, byte_count, tag == b"Xing"

    offset = frame_start + 36
    if offset + 18 <= len(buf) and buf[offset:offset + 4] == b"VBRI":
        return (
            int.from_bytes(buf[offset + 14:offset + 18], "big"),
            int.from_bytes(buf[offset + 10:offset + 14], "big"),
            True,
        )
    return None, None, False


def get_info(file_path):
    """Read sample rate, channels and duration from an MP3 file.

    Raises ValueError when no Layer III frame can be found.
    """
    file_size = 0
    try:
        import os

        file_size = os.stat(file_path)[6]
    except OSError:
        pass

    with open(file_path, "rb") as f:
        head = f.read(10)
        id3_size = _id3v2_size(head)
        if id3_size:
            f.seek(id3_size)
        else:
            f.seek(0)
        buf = f.read(_HEAD_READ)

        frame_start, info = _find_frame(buf)
        if info is None:
            raise ValueError("No MP3 frame found")

        frames, stream_bytes, vbr = _xing_frames(buf, frame_start, info)

        has_id3v1 = False
        if file_size > 128:
            try:
                f.seek(-128, 2)
                has_id3v1 = f.read(3) == b"TAG"
            except OSError:
                pass

    sample_rate = info["sample_rate"]
    samples_per_frame = info["samples_per_frame"]
    if frames:
        duration_ms = frames * samples_per_frame * 1000 // sample_rate
    else:
        audio_bytes = file_size - id3_size - frame_start
        if has_id3v1:
            audio_bytes -= 128
        if audio_bytes < 0:
            audio_bytes = 0
        duration_ms = audio_bytes * 8 // info["bitrate_kbps"] if info["bitrate_kbps"] else 0

    if stream_bytes and frames:
        frame_bytes = stream_bytes // (frames + 1)
        if frame_bytes:
            info["bitrate_kbps"] = (
                frame_bytes * 8 * sample_rate // samples_per_frame // 1000
            )

    result = dict(info)
    result["duration_ms"] = duration_ms
    result["total_samples"] = duration_ms * sample_rate // 1000
    result["audio_offset"] = id3_size + frame_start
    result["id3_size"] = id3_size
    result["vbr"] = bool(vbr)
    result["xing_frames"] = frames
    result["file_size"] = file_size
    return result


# ── Decoding helpers (native module) ─────────────────────────────────


def _volume_shift(volume):
    if volume is None:
        return 0
    from mpos.audio.stream_wav import WAVStream

    return WAVStream._volume_percent_to_shift(volume)


def _wav_header(sample_rate, channels, data_size):
    byte_rate = sample_rate * channels * 2
    return (
        b"RIFF"
        + (data_size + 36).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + channels.to_bytes(2, "little")
        + sample_rate.to_bytes(4, "little")
        + byte_rate.to_bytes(4, "little")
        + (channels * 2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + data_size.to_bytes(4, "little")
    )


def decode_file(file_path, volume=100, chunk_size=8192):
    """Decode a whole file to interleaved 16-bit PCM (little endian)."""
    import mp3dec

    decoder = mp3dec.Decoder()
    out = bytearray(16384)
    shift = _volume_shift(volume)
    result = bytearray()
    try:
        with open(file_path, "rb") as f:
            eof = False
            while not eof:
                data = f.read(chunk_size)
                if not data:
                    eof = True
                    decoder.finish()
                while True:
                    written = decoder.decode_into(data, out, shift)
                    data = b""
                    if not written:
                        break
                    result.extend(memoryview(out)[:written])
    finally:
        decoder.close()
    return bytes(result)


def decode_to_wav(src_path, dst_path, volume=100, chunk_size=8192):
    """Decode *src_path* to a 16-bit PCM WAV at *dst_path*."""
    import mp3dec

    info = get_info(src_path)
    sample_rate = info["sample_rate"]
    channels = info["channels"]
    decoder = mp3dec.Decoder()
    out = bytearray(16384)
    shift = _volume_shift(volume)
    data_size = 0
    try:
        with open(src_path, "rb") as f, open(dst_path, "wb") as wav:
            wav.write(_wav_header(sample_rate, channels, 0))
            eof = False
            while not eof:
                data = f.read(chunk_size)
                if not data:
                    eof = True
                    decoder.finish()
                while True:
                    written = decoder.decode_into(data, out, shift)
                    data = b""
                    if not written:
                        break
                    wav.write(memoryview(out)[:written])
                    data_size += written
            wav.seek(0)
            wav.write(_wav_header(sample_rate, channels, data_size))
    finally:
        decoder.close()
    return info
