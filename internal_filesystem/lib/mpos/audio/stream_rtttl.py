# RTTTLStream - RTTTL Ringtone Playback Stream for AudioManager
# Ring Tone Text Transfer Language parser and player
# Uses synchronous playback in a separate thread for non-blocking operation

import asyncio
import logging
import math
import os
import time

logger = logging.getLogger(__name__)


class RTTTLStream:
    """
    RTTTL (Ring Tone Text Transfer Language) parser and player.
    Format: "name:defaults:notes"
    Example: "Nokia:d=4,o=5,b=225:8e6,8d6,8f#,8g#,8c#6,8b,d"

    See: https://en.wikipedia.org/wiki/Ring_Tone_Text_Transfer_Language
    """

    # Note frequency table (A-G, with sharps)
    _NOTES = [
        440.0,  # A
        493.9,  # B or H
        261.6,  # C
        293.7,  # D
        329.6,  # E
        349.2,  # F
        392.0,  # G
        0.0,    # pad

        466.2,  # A#
        0.0,    # pad
        277.2,  # C#
        311.1,  # D#
        0.0,    # pad
        370.0,  # F#
        415.3,  # G#
        0.0,    # pad
    ]

    def __init__(self, rtttl_string, stream_type, volume, buzzer_instance, on_complete):
        """
        Initialize RTTTL stream.

        Args:
            rtttl_string: RTTTL format string (e.g., "Nokia:d=4,o=5,b=225:...")
            stream_type: Stream type (STREAM_MUSIC, STREAM_NOTIFICATION, STREAM_ALARM)
            volume: Volume level (0-100)
            buzzer_instance: PWM buzzer instance
            on_complete: Callback function(message) when playback finishes
        """
        self.stream_type = stream_type
        self.volume = volume
        self.buzzer = buzzer_instance
        self.on_complete = on_complete
        self._keep_running = True
        self._is_playing = False
        self._repeat_count = 1

        # Parse RTTTL format
        rtttl_string = rtttl_string.strip()
        tune_pieces = rtttl_string.split(':')
        if len(tune_pieces) != 3:
            raise ValueError('RTTTL should contain exactly 2 colons')

        self.name = tune_pieces[0]
        self.tune = tune_pieces[2]
        self.tune_idx = 0
        self._parse_defaults(tune_pieces[1])

    def is_playing(self):
        """Check if stream is currently playing."""
        return self._is_playing

    def stop(self):
        """Stop playback."""
        self._keep_running = False

    def _parse_defaults(self, defaults):
        """
        Parse default values from RTTTL format.
        Example: "d=4,o=5,b=140"
        """
        self.default_duration = 4
        self.default_octave = 5
        self.bpm = 120

        for item in defaults.split(','):
            setting = item.split('=')
            if len(setting) != 2:
                continue

            key = setting[0].strip()
            value = int(setting[1].strip())

            if key == 'o':
                self.default_octave = value
            elif key == 'd':
                self.default_duration = value
            elif key == 'b':
                self.bpm = value

        # Calculate milliseconds per whole note
        # 240000 = 60 sec/min * 4 beats/whole-note * 1000 msec/sec
        self.msec_per_whole_note = 240000.0 / self.bpm

    def _next_char(self):
        """Get next character from tune string."""
        if self.tune_idx < len(self.tune):
            char = self.tune[self.tune_idx]
            self.tune_idx += 1
            if char == ',':
                char = ' '
            return char
        return '|'  # End marker

    def _notes(self):
        """
        Generator that yields (frequency, duration_ms) tuples.

        Yields:
            tuple: (frequency_hz, duration_ms) for each note
        """
        while True:
            # Skip blank characters and commas
            char = self._next_char()
            while char == ' ':
                char = self._next_char()

            # Parse duration (if present)
            # Duration of 1 = whole note, 8 = 1/8 note
            duration = 0
            while char.isdigit():
                duration *= 10
                duration += ord(char) - ord('0')
                char = self._next_char()

            if duration == 0:
                duration = self.default_duration

            if char == '|':  # End of tune
                return

            # Parse note letter
            note = char.lower()
            if 'a' <= note <= 'g':
                note_idx = ord(note) - ord('a')
            elif note == 'h':
                note_idx = 1  # H is equivalent to B
            elif note == 'p':
                note_idx = 7  # Pause
            else:
                note_idx = 7  # Unknown = pause

            char = self._next_char()

            # Check for sharp
            if char == '#':
                note_idx += 8
                char = self._next_char()

            # Check for duration modifier (dot) before octave
            duration_multiplier = 1.0
            if char == '.':
                duration_multiplier = 1.5
                char = self._next_char()

            # Check for octave
            if '4' <= char <= '7':
                octave = ord(char) - ord('0')
                char = self._next_char()
            else:
                octave = self.default_octave

            # Check for duration modifier (dot) after octave
            if char == '.':
                duration_multiplier = 1.5
                char = self._next_char()

            # Calculate frequency and duration
            freq = self._NOTES[note_idx] * (1 << (octave - 4))
            msec = (self.msec_per_whole_note / duration) * duration_multiplier

            yield freq, msec

    def play(self):
        """Play RTTTL tune via buzzer (runs in separate thread)."""
        self._is_playing = True

        # Calculate exponential duty cycle for perceptually linear volume
        if self.volume <= 0:
            duty = 0
        else:
            volume = min(100, self.volume)

            # Exponential volume curve
            # Maximum volume is at 50% duty cycle (32768 when using duty_u16)
            # Minimum is 4 (absolute minimum for audible PWM)
            divider = 10
            duty = int(
                ((math.exp(volume / divider) - math.exp(0.1)) /
                 (math.exp(10) - math.exp(0.1)) * (32768 - 4)) + 4
            )

        if __debug__: logger.debug("Playing '%s' (volume %s%%)", self.name, self.volume)

        try:
            iteration = 0
            while self._keep_running and iteration < self._repeat_count:
                iteration += 1
                self.tune_idx = 0
                for freq, msec in self._notes():
                    if not self._keep_running:
                        if __debug__: logger.debug("Playback stopped by user")
                        break

                    # Play tone
                    if freq > 0:
                        try:
                            self.buzzer.freq(int(freq))
                            self.buzzer.duty_u16(duty)
                        except RuntimeError:
                            # PWM was deinitialized by another thread/session
                            self._keep_running = False
                            break

                    # Play for 90% of duration, silent for 10% (note separation)
                    # Blocking sleep is OK - we're in a separate thread
                    time.sleep_ms(int(msec * 0.9))
                    try:
                        self.buzzer.duty_u16(0)
                    except RuntimeError:
                        # PWM was deinitialized by another thread/session
                        self._keep_running = False
                        break
                    time.sleep_ms(int(msec * 0.1))

            if __debug__: logger.debug("Finished playing '%s'", self.name)
            if self.on_complete:
                self.on_complete(f"Finished: {self.name}")

        except Exception as e:
            logger.error("Error: %s", e)
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            # Ensure buzzer is off
            try:
                self.buzzer.duty_u16(0)
            except RuntimeError:
                # PWM was already deinitialized by another thread/session
                pass
            self._is_playing = False

    def set_volume(self, vol):
        self.volume = vol

    def set_repeat(self, count):
        try:
            count = int(count)
        except (TypeError, ValueError):
            return
        if count < 0:
            count = 0
        self._repeat_count = count


class WebRTTTLStream(RTTTLStream):
    runs_async = True

    @staticmethod
    def _duty_for_volume(volume):
        if volume <= 0:
            return 0
        volume = min(100, volume)
        divider = 10
        return int(
            ((math.exp(volume / divider) - math.exp(0.1)) /
             (math.exp(10) - math.exp(0.1)) * (32768 - 4)) + 4
        )

    async def _play_async(self):
        try:
            iteration = 0
            while self._keep_running and iteration < self._repeat_count:
                iteration += 1
                self.tune_idx = 0
                for frequency, duration_ms in self._notes():
                    if not self._keep_running:
                        break
                    duty = self._duty_for_volume(self.volume)
                    if frequency > 0:
                        self.buzzer.freq(int(frequency))
                        self.buzzer.duty_u16(duty)
                    await asyncio.sleep_ms(int(duration_ms * 0.9))
                    self.buzzer.duty_u16(0)
                    await asyncio.sleep_ms(int(duration_ms * 0.1))
            if self.on_complete:
                self.on_complete("Finished: %s" % self.name)
        except Exception as e:
            logger.error("Error: %s", e)
            if self.on_complete:
                self.on_complete("Error: %s" % e)
        finally:
            try:
                self.buzzer.duty_u16(0)
            except RuntimeError:
                pass
            self._is_playing = False

    def play(self):
        self._is_playing = True
        asyncio.get_event_loop().create_task(self._play_async())


class DesktopRTTTLStream(RTTTLStream):
    def __init__(self, rtttl_string, stream_type, volume, on_complete):
        super().__init__(rtttl_string, stream_type, volume, None, on_complete)
        self._wav_stream = None
        self._temp_path = "/tmp/mpos_rtttl_%d.wav" % id(self)

    @staticmethod
    def _write_samples(file, frequency, sample_count, sample_rate):
        chunk_samples = 1024
        phase = 0.0
        remaining = sample_count
        while remaining > 0:
            count = min(chunk_samples, remaining)
            data = bytearray(count * 2)
            for index in range(count):
                value = 12000 if phase < sample_rate / 2 else -12000
                value &= 0xFFFF
                data[index * 2] = value & 0xFF
                data[index * 2 + 1] = value >> 8
                phase += frequency
                if phase >= sample_rate:
                    phase -= sample_rate
            file.write(data)
            remaining -= count

    @staticmethod
    def _write_silence(file, sample_count):
        chunk = bytes(2048)
        remaining = sample_count * 2
        while remaining > 0:
            count = min(len(chunk), remaining)
            file.write(chunk[:count])
            remaining -= count

    def _render(self):
        sample_rate = 22050
        data_size = 0
        with open(self._temp_path, "wb") as file:
            file.write(b"RIFF\x00\x00\x00\x00WAVEfmt ")
            file.write((16).to_bytes(4, "little"))
            file.write((1).to_bytes(2, "little"))
            file.write((1).to_bytes(2, "little"))
            file.write(sample_rate.to_bytes(4, "little"))
            file.write((sample_rate * 2).to_bytes(4, "little"))
            file.write((2).to_bytes(2, "little"))
            file.write((16).to_bytes(2, "little"))
            file.write(b"data\x00\x00\x00\x00")

            iteration = 0
            while self._keep_running and iteration < self._repeat_count:
                iteration += 1
                self.tune_idx = 0
                for frequency, duration_ms in self._notes():
                    if not self._keep_running:
                        break
                    tone_samples = int(sample_rate * duration_ms * 0.9 / 1000)
                    silence_samples = int(sample_rate * duration_ms * 0.1 / 1000)
                    if frequency > 0:
                        self._write_samples(file, frequency, tone_samples, sample_rate)
                    else:
                        self._write_silence(file, tone_samples)
                    self._write_silence(file, silence_samples)
                    data_size += (tone_samples + silence_samples) * 2

            file.seek(4)
            file.write((data_size + 36).to_bytes(4, "little"))
            file.seek(40)
            file.write(data_size.to_bytes(4, "little"))

    def play(self):
        from mpos.audio.stream_wav import WAVStream

        self._is_playing = True
        try:
            self._render()
            if not self._keep_running:
                if self.on_complete:
                    self.on_complete("Finished: %s" % self.name)
                return
            self._wav_stream = WAVStream(
                file_path=self._temp_path,
                stream_type=self.stream_type,
                volume=self.volume,
                i2s_pins={"ws": 0, "sd": 0},
                on_complete=None,
            )
            self._wav_stream.play()
            if self.on_complete:
                self.on_complete("Finished: %s" % self.name)
        except Exception as e:
            logger.error("Error: %s", e)
            if self.on_complete:
                self.on_complete("Error: %s" % e)
        finally:
            self._is_playing = False
            try:
                os.remove(self._temp_path)
            except OSError:
                pass

    def stop(self):
        self._keep_running = False
        if self._wav_stream:
            self._wav_stream.stop()

    def set_volume(self, vol):
        self.volume = vol
        if self._wav_stream:
            self._wav_stream.set_volume(vol)
