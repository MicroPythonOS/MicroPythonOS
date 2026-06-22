# WAVStream - WAV File Playback Stream for AudioManager
# Supports 8/16/24/32-bit PCM, mono+stereo, auto-upsampling.
# Uses synchronous playback in a separate thread for non-blocking operation.

import logging
import machine
import micropython
import os
import time
from mpos.audio import adpcm_ima

logger = logging.getLogger(__name__)


class WAVStream:
    """
    WAV file playback stream with I2S output.
    Supports 8/16/24/32-bit PCM, mono and stereo, auto-upsampling to >=8000 Hz.
    """

    WAVE_FORMAT_PCM = 0x1
    WAVE_FORMAT_ADPCM = 0x0011
    WAVE_FORMAT_EXTENSIBLE = 0xFFFE # often used for 24 and 32 bits per sample
    _VOLUME_TO_SHIFT = (
        16, 7, 6, 6, 5, 5, 5, 4, 4, 4,
        4, 4, 4, 3, 3, 3, 3, 3, 3, 3,
        3, 3, 3, 3, 3, 2, 2, 2, 2, 2,
        2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
        2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
        1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
        0,
    )

    def __init__(
        self,
        file_path,
        stream_type,
        volume,
        i2s_pins,
        on_complete,
        requested_sample_rate=None,
        on_open=None,
        on_close=None,
    ):
        """
        Initialize WAV stream.

        Args:
            file_path: Path to WAV file
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)
            volume: Volume level (0-100)
            i2s_pins: Dict with 'sck', 'ws', 'sd' pin numbers
            on_complete: Callback function(message) when playback finishes
            requested_sample_rate: Optional negotiated sample rate for shared clocks
            on_open: Optional callable invoked after MCLK starts, before I2S init
            on_close: Optional callable invoked before I2S deinit (after audio drains)
        """
        self.file_path = file_path
        self.stream_type = stream_type
        self.volume = volume
        self.i2s_pins = i2s_pins
        self.on_complete = on_complete
        self.requested_sample_rate = requested_sample_rate
        self.on_open = on_open
        self.on_close = on_close
        self._keep_running = True
        self._is_playing = False
        self._i2s = None
        self._mck_pwm = None
        self._progress_samples = 0
        self._total_samples = 0
        self._duration_ms = None
        self._playback_rate = None
        self._original_rate = None
        self._channels = None
        self._bits_per_sample = None
        self._data_size = None

    def is_playing(self):
        """Check if stream is currently playing."""
        return self._is_playing

    def stop(self):
        """Stop playback."""
        self._keep_running = False

    def get_progress_percent(self):
        if self._total_samples <= 0:
            return None
        return int((self._progress_samples / self._total_samples) * 100)

    def get_progress_ms(self):
        if self._playback_rate:
            return int((self._progress_samples / self._playback_rate) * 1000)
        return None

    def get_duration_ms(self):
        return self._duration_ms


    # ----------------------------------------------------------------------
    #  WAV header parser - returns bit-depth and format info
    # ----------------------------------------------------------------------
    @staticmethod
    def _find_data_chunk(f):
        """
        Parse WAV header and find data chunk.

        Returns:
            tuple: (data_start, data_size, sample_rate, channels,
                    bits_per_sample, format_tag, block_align, total_samples_frames)
        """
        f.seek(0)
        if f.read(4) != b'RIFF':
            raise ValueError("Not a RIFF (standard .wav) file")

        file_size = int.from_bytes(f.read(4), 'little') + 8

        if f.read(4) != b'WAVE':
            raise ValueError("Not a WAVE (standard .wav) file")

        pos = 12
        sample_rate = None
        channels = None
        bits_per_sample = None
        format_tag = None
        block_align = None
        total_samples_frames = None
        data_start = None
        data_size = None

        while pos < file_size:
            f.seek(pos)
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break

            chunk_size = int.from_bytes(f.read(4), 'little')

            if chunk_id == b'fmt ':
                fmt = f.read(chunk_size)
                if len(fmt) < 16:
                    raise ValueError("Invalid fmt chunk")

                format_tag = int.from_bytes(fmt[0:2], 'little')
                if format_tag not in (WAVStream.WAVE_FORMAT_PCM, WAVStream.WAVE_FORMAT_EXTENSIBLE, WAVStream.WAVE_FORMAT_ADPCM):
                    raise ValueError("Unsupported WAV format tag: 0x%04x" % format_tag)

                channels = int.from_bytes(fmt[2:4], 'little')
                if channels not in (1, 2):
                    raise ValueError("Only mono or stereo supported")

                sample_rate = int.from_bytes(fmt[4:8], 'little')
                block_align = int.from_bytes(fmt[12:14], 'little')
                bits_per_sample = int.from_bytes(fmt[14:16], 'little')

                if format_tag == WAVStream.WAVE_FORMAT_ADPCM:
                    if bits_per_sample not in (4, 16):
                        raise ValueError("ADPCM WAV must have 4 or 16 bits per sample")
                else:
                    if bits_per_sample not in (8, 16, 24, 32):
                        raise ValueError("Only 8/16/24/32-bit PCM supported")

            elif chunk_id == b'fact':
                if chunk_size >= 4:
                    total_samples_frames = int.from_bytes(f.read(4), 'little')

            elif chunk_id == b'data':
                data_start = f.tell()
                data_size = chunk_size

            pos += 8 + chunk_size
            if chunk_size % 2:
                pos += 1

        if data_start is None:
            raise ValueError("No 'data' chunk found")

        if format_tag == WAVStream.WAVE_FORMAT_PCM or format_tag == WAVStream.WAVE_FORMAT_EXTENSIBLE:
            total_samples_frames = data_size // (channels * (bits_per_sample // 8))
        elif total_samples_frames is None:
            spb = 1 + (block_align - 4 * channels) * 2 // channels
            total_samples_frames = (data_size // block_align) * spb

        return (data_start, data_size, sample_rate, channels,
                bits_per_sample, format_tag, block_align, total_samples_frames)

    # ----------------------------------------------------------------------
    #  WAV info helpers
    # ----------------------------------------------------------------------
    @staticmethod
    def get_wav_info(file_path):
        with open(file_path, 'rb') as f:
            data_start, data_size, sample_rate, channels, bits_per_sample, format_tag, block_align, total_samples_frames = (
                WAVStream._find_data_chunk(f)
            )
        return {
            "data_start": data_start,
            "data_size": data_size,
            "sample_rate": sample_rate,
            "channels": channels,
            "bits_per_sample": bits_per_sample,
            "format_tag": format_tag,
            "block_align": block_align,
            "total_samples_frames": total_samples_frames,
        }

    @staticmethod
    def compute_playback_rate(original_rate, requested_rate=None):
        if requested_rate:
            if requested_rate <= original_rate:
                return original_rate, 1
            upsample_factor = (requested_rate + original_rate - 1) // original_rate
            return original_rate * upsample_factor, upsample_factor

        minimal_rate = 8000
        if original_rate >= minimal_rate:
            return original_rate, 1
        upsample_factor = (minimal_rate + original_rate - 1) // original_rate
        return original_rate * upsample_factor, upsample_factor

    # ----------------------------------------------------------------------
    #  Bit depth conversion functions
    # ----------------------------------------------------------------------
    @staticmethod
    @micropython.native
    def _convert_8_to_16(buf):
        """Convert 8-bit unsigned PCM to 16-bit signed PCM."""
        out = bytearray(len(buf) * 2)
        j = 0
        for i in range(len(buf)):
            u8 = buf[i]
            s16 = (u8 - 128) << 8
            out[j] = s16 & 0xFF
            out[j + 1] = (s16 >> 8) & 0xFF
            j += 2
        return out

    @staticmethod
    @micropython.native
    def _convert_24_to_16(buf):
        """Convert 24-bit PCM to 16-bit PCM."""
        samples = len(buf) // 3
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            b0 = buf[j]
            b1 = buf[j + 1]
            b2 = buf[j + 2]
            s24 = (b2 << 16) | (b1 << 8) | b0
            if b2 & 0x80:
                s24 -= 0x1000000
            s16 = s24 >> 8
            out[i * 2] = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 3
        return out

    @staticmethod
    @micropython.native
    def _convert_32_to_16(buf):
        """Convert 32-bit PCM to 16-bit PCM."""
        samples = len(buf) // 4
        out = bytearray(samples * 2)
        j = 0
        for i in range(samples):
            b0 = buf[j]
            b1 = buf[j + 1]
            b2 = buf[j + 2]
            b3 = buf[j + 3]
            s32 = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
            if b3 & 0x80:
                s32 -= 0x100000000
            s16 = s32 >> 16
            out[i * 2] = s16 & 0xFF
            out[i * 2 + 1] = (s16 >> 8) & 0xFF
            j += 4
        return out

    @staticmethod
    def _get_freq_duty(sample_rate):
        return (sample_rate * 256, 32768) # sensible defaults
        '''
        # These frequencies and duty cycles don't wake up the Fri3d Communicator when playing to headset, but that will be fixed so no need:
        if sample_rate == 8000:
            return (640000,1365)
        elif sample_rate == 11025:
            return (1060800,1024)
        elif sample_rate == 16000:
            return (512000,512)
        elif sample_rate == 22050:
            return (705600,1024)
        elif sample_rate == 32000:
            return (1024000,1024)
        elif sample_rate == 44100:
            return (1411200,2048)
        else:
            if __debug__: logger.debug("Uncommon sample rate %s, using default", sample_rate)
            return (sample_rate * 256, 32768)
        '''

    # ----------------------------------------------------------------------
    #  Upsampling (zero-order-hold)
    # ----------------------------------------------------------------------
    @staticmethod
    @micropython.native
    def _upsample_buffer(raw, factor):
        """Upsample 16-bit buffer by repeating samples."""
        if factor == 1:
            return raw

        upsampled = bytearray(len(raw) * factor)
        out_idx = 0
        for i in range(0, len(raw), 2):
            lo = raw[i]
            hi = raw[i + 1]
            for _ in range(factor):
                upsampled[out_idx] = lo
                upsampled[out_idx + 1] = hi
                out_idx += 2
        return upsampled

    @staticmethod
    @micropython.native
    def _volume_percent_to_shift(volume):
        """Convert 0-100 volume percent to a 0-16 right-shift amount."""
        if volume <= 0:
            return 16
        if volume >= 100:
            return 0
        return WAVStream._VOLUME_TO_SHIFT[volume]

    # ----------------------------------------------------------------------
    #  Main playback routine
    # ----------------------------------------------------------------------
    def play(self):
        """Main synchronous playback routine (runs in separate thread)."""
        self._is_playing = True

        try:
            with open(self.file_path, 'rb') as f:
                st = os.stat(self.file_path)
                file_size = st[6]
                if __debug__: logger.debug("Playing %s (%s bytes)", self.file_path, file_size)

                # Parse WAV header
                data_start, data_size, original_rate, channels, bits_per_sample, format_tag, block_align, total_samples_frames = \
                    self._find_data_chunk(f)

                self._original_rate = original_rate
                self._channels = channels
                self._bits_per_sample = bits_per_sample
                self._data_size = data_size

                playback_rate, upsample_factor = self.compute_playback_rate(
                    original_rate,
                    self.requested_sample_rate,
                )

                self._playback_rate = playback_rate

                # This influences how long it takes for the audio to start; low values: more responsive, high values: slow start but smoother
                # ibuf = playback_rate # doesnt account for stereo vs mono...
                #ibuf = 8192 * 1 # more jitters when playing audio and doing other things like updating the UI
                ibuf =  8192 * 4 # good balance between smooth audio and still responsive to volume changes
                #ibuf = 8192 * 8 # 64KiB seems to help for reducing stutter while playing music + QuasiBird

                if __debug__: logger.debug("%s Hz, %s-bit, %s-ch", original_rate, bits_per_sample, channels)
                if __debug__: logger.debug("Playback at %s Hz (upsample factor %s)", playback_rate, upsample_factor)

                if data_size > file_size - data_start:
                    data_size = file_size - data_start

                bytes_per_sample = (bits_per_sample // 8) * channels
                if format_tag == WAVStream.WAVE_FORMAT_ADPCM or bytes_per_sample > 0:
                    self._total_samples = total_samples_frames
                    self._duration_ms = int((self._total_samples / original_rate) * 1000)

                if __debug__: logger.debug("I2S init params: requested_rate=%s, playback_rate=%s, original_rate=%s, channels=%s, bits=16, i2s_pins=%s", self.requested_sample_rate, playback_rate, original_rate, channels, self.i2s_pins)

                # Initialize I2S (always 16-bit output)
                try:
                    i2s_format = machine.I2S.MONO if channels == 1 else machine.I2S.STEREO
                    if __debug__: logger.debug("I2S config: format=%s, ibuf=%s, has_sck=%s, mck_pin=%s", 'MONO' if channels == 1 else 'STEREO', ibuf, bool(self.i2s_pins.get('sck')), self.i2s_pins.get('mck'))

                    # Configure MCLK pin if provided (must be done before I2S init)
                    # On some MicroPython versions, machine.I2S() supports a mck argument
                    # but not on ESP32S3 1.27.0 version, apparently.
                    if 'mck' in self.i2s_pins:
                        mck_pin = machine.Pin(self.i2s_pins['mck'], machine.Pin.OUT)
                        from machine import PWM
                        try:
                            self._mck_pwm = PWM(mck_pin)
                            freq, duty = WAVStream._get_freq_duty(playback_rate)
                            self._mck_pwm.freq(freq)
                            self._mck_pwm.duty_u16(duty)
                            if __debug__: logger.debug("MCLK PWM started at %s Hz with duty cycle %s/65535", freq, duty)
                        except Exception as e:
                            logger.error("MCLK PWM init failed: %s", e)
                            # fallback or error handling

                    # Notify codec/amp to prepare for playback (enable amp, unmute DAC, etc.)
                    if self.on_open:
                        try:
                            self.on_open()
                        except Exception as e:
                            logger.error("on_open failed: %s", e)

                    if self.i2s_pins.get("sck"):
                        self._i2s = machine.I2S(
                            0,
                            sck=machine.Pin(self.i2s_pins['sck'], machine.Pin.OUT),
                            ws=machine.Pin(self.i2s_pins['ws'], machine.Pin.OUT),
                            sd=machine.Pin(self.i2s_pins['sd'], machine.Pin.OUT),
                            mode=machine.I2S.TX,
                            bits=16,
                            format=i2s_format,
                            rate=playback_rate,
                            ibuf=ibuf
                        )
                    else:
                        self._i2s = machine.I2S(
                            0,
                            ws=machine.Pin(self.i2s_pins['ws'], machine.Pin.OUT),
                            sd=machine.Pin(self.i2s_pins['sd'], machine.Pin.OUT),
                            mode=machine.I2S.TX,
                            bits=16,
                            format=i2s_format,
                            rate=playback_rate,
                            ibuf=ibuf
                        )
                except Exception as e:
                    logger.error("I2S init failed: %s", e)
                    return

                if __debug__: logger.debug("Playing %s bytes (volume %s%%)", data_size, self.volume)
                f.seek(data_start)

                bytes_per_second_out = playback_rate * 2 * channels

                if format_tag == WAVStream.WAVE_FORMAT_ADPCM:
                    spb = adpcm_ima.samples_per_block(block_align, channels)

                    # Decode enough blocks per chunk for ~100 ms of output audio
                    target_decoded_bytes = max(
                        playback_rate * 2 * channels // 10,
                        spb * 2 * channels,
                    )
                    blocks_per_chunk = max(1, target_decoded_bytes // (spb * 2 * channels))

                    frames_so_far = 0
                    while frames_so_far < total_samples_frames:
                        if not self._keep_running:
                            if __debug__: logger.debug("Playback stopped by user")
                            break

                        remaining_compressed = data_size - (f.tell() - data_start)
                        remaining_compressed -= remaining_compressed % block_align
                        if remaining_compressed <= 0:
                            break

                        max_blocks = min(blocks_per_chunk, remaining_compressed // block_align)
                        to_read = max_blocks * block_align
                        if to_read <= 0:
                            break

                        raw_compressed = bytearray(f.read(to_read))
                        if not raw_compressed:
                            break

                        raw = bytearray()
                        for off in range(0, len(raw_compressed), block_align):
                            raw.extend(adpcm_ima.decode_block(raw_compressed[off:off + block_align], channels, block_align))

                        frames = len(raw) // (2 * channels)

                        # Upsample if needed
                        if upsample_factor > 1:
                            raw = self._upsample_buffer(raw, upsample_factor)

                        # Volume scaling via I2S native right-shift
                        if self.volume < 100:
                            volume_shift = self._volume_percent_to_shift(self.volume)
                            if self._i2s and volume_shift > 0:
                                self._i2s.shift(buf=raw, bits=16, shift=-volume_shift)

                        # Output to I2S
                        if self._i2s:
                            remaining = memoryview(raw)
                            while remaining:
                                written = self._i2s.write(remaining)
                                if written is None:
                                    written = len(remaining)
                                if written <= 0:
                                    time.sleep_ms(1)
                                    continue
                                remaining = remaining[written:]
                        else:
                            time.sleep(frames / playback_rate)

                        frames_so_far += frames
                        self._progress_samples = frames_so_far

                        # Yield so the UI thread gets a chance to run
                        if self._keep_running:
                            time.sleep_ms(1)

                else:
                    # Chunk size tuning notes:
                    # - Smaller chunks = more responsive to stop()
                    # - Larger chunks = less overhead, smoother audio
                    # - The 0.5-second (stereo) or 1 second (mono) I2S buffer handles timing smoothness
                    bytes_per_second = original_rate * bytes_per_sample
                    chunk_size = int(bytes_per_second / 10.7) # chunk_size of 8192 worked great with 22050hz stereo 16 bit so 88200 bytes per sample so fator 10.7
                    #chunk_size = bytes_per_second >> 3 # 12-14 fps
                    #chunk_size = bytes_per_second >> 4 # 16-18 fps but stutters
                    #chunk_size = int(bytes_per_second / 12) # 18 fps for 8khz mono, 16 fps for 22khz mono, higher stutters
                    #chunk_size = int(bytes_per_second / 11) # still jitters at 22050hz stereo in quasibird

                    total_original = 0
                    while total_original < data_size:
                        if not self._keep_running:
                            if __debug__: logger.debug("Playback stopped by user")
                            break

                        # Read chunk of original data
                        to_read = min(chunk_size, data_size - total_original)
                        to_read -= (to_read % bytes_per_sample)
                        if to_read <= 0:
                            break

                        raw = bytearray(f.read(to_read))
                        if not raw:
                            break

                        # 1. Convert bit-depth to 16-bit
                        if bits_per_sample == 8:
                            raw = self._convert_8_to_16(raw)
                        elif bits_per_sample == 24:
                            raw = self._convert_24_to_16(raw)
                        elif bits_per_sample == 32:
                            raw = self._convert_32_to_16(raw)

                        # 2. Upsample if needed
                        if upsample_factor > 1:
                            raw = self._upsample_buffer(raw, upsample_factor)

                        # 3. Volume scaling via I2S native right-shift
                        if self.volume < 100:
                            volume_shift = self._volume_percent_to_shift(self.volume)
                            if self._i2s and volume_shift > 0:
                                self._i2s.shift(buf=raw, bits=16, shift=-volume_shift)

                        # 4. Output to I2S (blocking write is OK - we're in a separate thread)
                        if self._i2s:
                            remaining = memoryview(raw)
                            while remaining:
                                written = self._i2s.write(remaining)
                                if written is None:
                                    written = len(remaining)
                                if written <= 0:
                                    time.sleep_ms(1)
                                    continue
                                remaining = remaining[written:]
                        else:
                            # Simulate playback timing if no I2S
                            num_samples = len(raw) // (2 * channels)
                            time.sleep(num_samples / playback_rate)

                        total_original += to_read
                        self._progress_samples = total_original // bytes_per_sample

                        # Yield so the UI thread gets a chance to run
                        if self._keep_running:
                            time.sleep_ms(1)

                if self._i2s and self._keep_running:
                    try:
                        drain_ms = int((ibuf / bytes_per_second_out) * 1000)
                        if drain_ms > 0:
                            time.sleep_ms(drain_ms)
                    except Exception as e:
                        logger.error("Drain wait failed: %s", e)

                if __debug__: logger.debug("Finished playing %s", self.file_path)
                if self.on_complete:
                    self.on_complete(f"Finished: {self.file_path}")

        except Exception as e:
            logger.error("Error: %s", e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            self._is_playing = False
            if self.on_close:
                try:
                    self.on_close()
                except Exception as e:
                    logger.error("on_close failed: %s", e)
            if self._i2s:
                if __debug__: logger.debug("Done playing, doing i2s deinit")
                self._i2s.deinit() # disabling this does not fix the "play just once" issue
                self._i2s = None
            if self._mck_pwm:
                try:
                    if __debug__: logger.debug("Done playing, stopping MCLK PWM")
                    self._mck_pwm.deinit()
                finally:
                    self._mck_pwm = None

    def set_volume(self, vol):
        self.volume = vol
