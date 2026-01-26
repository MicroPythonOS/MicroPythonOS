# RTTTLStream - RTTTL Ringtone Playback Stream for AudioManager
# Ring Tone Text Transfer Language parser and player
# Uses synchronous playback in a separate thread for non-blocking operation

import math
import time


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

        # Parse RTTTL format
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

        print(f"RTTTLStream: Playing '{self.name}' (volume {self.volume}%)")

        try:
            for freq, msec in self._notes():
                if not self._keep_running:
                    print("RTTTLStream: Playback stopped by user")
                    break

                # Play tone
                if freq > 0:
                    self.buzzer.freq(int(freq))
                    self.buzzer.duty_u16(duty)

                # Play for 90% of duration, silent for 10% (note separation)
                # Blocking sleep is OK - we're in a separate thread
                time.sleep_ms(int(msec * 0.9))
                self.buzzer.duty_u16(0)
                time.sleep_ms(int(msec * 0.1))

            print(f"RTTTLStream: Finished playing '{self.name}'")
            if self.on_complete:
                self.on_complete(f"Finished: {self.name}")

        except Exception as e:
            print(f"RTTTLStream: Error: {e}")
            if self.on_complete:
                self.on_complete(f"Error: {e}")

        finally:
            # Ensure buzzer is off
            self.buzzer.duty_u16(0)
            self._is_playing = False

    def set_volume(self, vol):
        self.volume = vol
