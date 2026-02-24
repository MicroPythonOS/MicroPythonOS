# AudioManager - Core Audio Management Service
# Registry-based audio routing with device descriptors and session control

import _thread

from ..task_manager import TaskManager


class StereoNotSupported(Exception):
    pass


class AudioManager:
    """
    Centralized audio management service with device registry and session control.

    Usage:
        from mpos import AudioManager

        AudioManager.add(AudioManager.Output(...))
        AudioManager.add(AudioManager.Input(...))

        player = AudioManager.player(file_path="music.wav")
        player.start()
    """

    STREAM_MUSIC = 0
    STREAM_NOTIFICATION = 1
    STREAM_ALARM = 2

    _instance = None

    class Output:
        def __init__(
            self,
            name,
            kind,
            channels=1,
            i2s_pins=None,
            buzzer_pin=None,
            preferred_sample_rate=None,
        ):
            if kind not in ("i2s", "buzzer"):
                raise ValueError("Output.kind must be 'i2s' or 'buzzer'")
            if channels not in (1, 2):
                raise ValueError("Output.channels must be 1 or 2")

            self.name = name
            self.kind = kind
            self.channels = channels
            self.preferred_sample_rate = preferred_sample_rate

            if kind == "i2s":
                if not i2s_pins:
                    raise ValueError("Output.i2s_pins required for i2s output")
                self._validate_i2s_pins(i2s_pins)
                self.i2s_pins = dict(i2s_pins)
                self.buzzer_pin = None
            else:
                if buzzer_pin is None:
                    raise ValueError("Output.buzzer_pin required for buzzer output")
                self.buzzer_pin = buzzer_pin
                self.i2s_pins = None

        @staticmethod
        def _validate_i2s_pins(i2s_pins):
            allowed = {"sck", "ws", "sd", "mck"}
            for key in i2s_pins:
                if key not in allowed:
                    raise ValueError("Invalid i2s_pins key for output: %s" % key)
            for key in ("ws", "sd"):
                if key not in i2s_pins:
                    raise ValueError("i2s_pins must include '%s'" % key)

        def __repr__(self):
            return "<AudioOutput %s kind=%s>" % (self.name, self.kind)

    class Input:
        def __init__(
            self,
            name,
            kind,
            channels=1,
            i2s_pins=None,
            adc_mic_pin=None,
            preferred_sample_rate=None,
        ):
            if kind not in ("i2s", "adc"):
                raise ValueError("Input.kind must be 'i2s' or 'adc'")
            if channels != 1:
                raise StereoNotSupported("Input channels=2 not supported yet")

            self.name = name
            self.kind = kind
            self.channels = channels
            self.preferred_sample_rate = preferred_sample_rate

            if kind == "i2s":
                if not i2s_pins:
                    raise ValueError("Input.i2s_pins required for i2s input")
                self._validate_i2s_pins(i2s_pins)
                self.i2s_pins = dict(i2s_pins)
                self.adc_mic_pin = None
            else:
                if adc_mic_pin is None:
                    raise ValueError("Input.adc_mic_pin required for adc input")
                self.adc_mic_pin = adc_mic_pin
                self.i2s_pins = None

        @staticmethod
        def _validate_i2s_pins(i2s_pins):
            allowed = {"sck_in", "sck", "ws", "sd_in"}
            for key in i2s_pins:
                if key not in allowed:
                    raise ValueError("Invalid i2s_pins key for input: %s" % key)
            for key in ("ws", "sd_in"):
                if key not in i2s_pins:
                    raise ValueError("i2s_pins must include '%s'" % key)

        def __repr__(self):
            return "<AudioInput %s kind=%s>" % (self.name, self.kind)

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        AudioManager._instance = self
        self._outputs = []
        self._inputs = []
        self._default_output = None
        self._default_input = None
        self._active_sessions = []
        self._volume = 50
        self._initialized = True

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def add(cls, device):
        return cls.get()._add_device(device)

    def _add_device(self, device):
        if isinstance(device, AudioManager.Output):
            self._outputs.append(device)
            if self._default_output is None:
                self._default_output = device
            return device
        if isinstance(device, AudioManager.Input):
            self._inputs.append(device)
            if self._default_input is None:
                self._default_input = device
            return device
        raise ValueError("Unsupported device type")

    @classmethod
    def get_outputs(cls):
        return list(cls.get()._outputs)

    @classmethod
    def get_inputs(cls):
        return list(cls.get()._inputs)

    @classmethod
    def get_default_output(cls):
        return cls.get()._default_output

    @classmethod
    def get_default_input(cls):
        return cls.get()._default_input

    @classmethod
    def set_default_output(cls, output):
        cls.get()._default_output = output

    @classmethod
    def set_default_input(cls, input_device):
        cls.get()._default_input = input_device

    @classmethod
    def set_volume(cls, volume):
        cls.get()._volume = max(0, min(100, volume))

    @classmethod
    def get_volume(cls):
        return cls.get()._volume

    @classmethod
    def player(
        cls,
        file_path=None,
        rtttl=None,
        stream_type=None,
        on_complete=None,
        output=None,
        sample_rate=None,
        volume=None,
    ):
        return Player(
            manager=cls.get(),
            file_path=file_path,
            rtttl=rtttl,
            stream_type=stream_type,
            on_complete=on_complete,
            output=output,
            sample_rate=sample_rate,
            volume=volume,
        )

    @classmethod
    def rtttl_player(cls, rtttl, **kwargs):
        return cls.player(rtttl=rtttl, **kwargs)

    @classmethod
    def recorder(
        cls,
        file_path,
        input=None,
        sample_rate=None,
        on_complete=None,
        duration_ms=None,
        **adc_config
    ):
        return Recorder(
            manager=cls.get(),
            file_path=file_path,
            input_device=input,
            sample_rate=sample_rate,
            on_complete=on_complete,
            duration_ms=duration_ms,
            adc_config=adc_config,
        )

    @classmethod
    def record_wav_adc(
        cls,
        file_path,
        duration_ms=None,
        sample_rate=None,
        adc_pin=None,
        on_complete=None,
        **adc_config
    ):
        manager = cls.get()
        from mpos.audio.stream_record_adc import ADCRecordStream

        stream = ADCRecordStream(
            file_path=file_path,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            adc_pin=adc_pin,
            on_complete=on_complete,
            **adc_config,
        )
        session = _ADCRecorderSession(manager, stream)
        manager._resolve_conflicts(session)
        manager._register_session(session)

        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(session._record_thread, ())
        return True

    @classmethod
    def stop(cls):
        return cls.get()._stop_all()

    def _stop_all(self):
        for session in list(self._active_sessions):
            session.stop()
        self._active_sessions = []

    def _register_session(self, session):
        self._active_sessions.append(session)

    def _session_finished(self, session):
        if session in self._active_sessions:
            self._active_sessions.remove(session)

    def _cleanup_inactive(self):
        active = []
        for session in self._active_sessions:
            if session.is_active():
                active.append(session)
        self._active_sessions = active

    def _resolve_conflicts(self, new_session):
        self._cleanup_inactive()
        to_stop = []
        for session in self._active_sessions:
            if self._sessions_conflict(session, new_session):
                to_stop.append(session)
        for session in to_stop:
            session.stop()
            if session in self._active_sessions:
                self._active_sessions.remove(session)

    @staticmethod
    def _pins_compatible(existing_signal, new_signal):
        if existing_signal == new_signal and existing_signal in ("ws", "sck"):
            return True
        return False

    def _sessions_conflict(self, existing, new_session):
        existing_pins = existing.pin_usage()
        new_pins = new_session.pin_usage()
        shared_clock = False

        for pin, new_signal in new_pins.items():
            if pin in existing_pins:
                existing_signal = existing_pins[pin]
                if self._pins_compatible(existing_signal, new_signal):
                    shared_clock = True
                    continue
                return True

        if shared_clock:
            if existing.sample_rate is None or new_session.sample_rate is None:
                return True
            if existing.sample_rate != new_session.sample_rate:
                return True

        return False

    def _start_player(self, player):
        if player.output is None:
            player.output = self._default_output
        if player.output is None:
            raise ValueError("No output device registered")

        if player.stream_type is None:
            player.stream_type = (
                self.STREAM_NOTIFICATION if player.rtttl else self.STREAM_MUSIC
            )

        if player.output.kind == "buzzer" and not player.rtttl:
            raise ValueError("RTTTL string required for buzzer output")
        if player.output.kind == "i2s" and not player.file_path:
            raise ValueError("file_path required for i2s output")

        player.sample_rate = self._determine_player_rate(player)

        self._resolve_conflicts(player)
        self._register_session(player)

        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(player._play_thread, ())

    def _start_recorder(self, recorder):
        if recorder.input_device is None:
            recorder.input_device = self._default_input
        if recorder.input_device is None:
            raise ValueError("No input device registered")

        recorder.sample_rate = self._determine_recorder_rate(recorder)

        self._resolve_conflicts(recorder)
        self._register_session(recorder)

        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(recorder._record_thread, ())

    def _determine_player_rate(self, player):
        if player.output.kind != "i2s":
            return None

        preferred = player.sample_rate or player.output.preferred_sample_rate

        from mpos.audio.stream_wav import WAVStream

        info = WAVStream.get_wav_info(player.file_path)
        original_rate = info["sample_rate"]
        playback_rate, _ = WAVStream.compute_playback_rate(original_rate, preferred)
        return playback_rate

    def _determine_recorder_rate(self, recorder):
        if recorder.sample_rate:
            return recorder.sample_rate
        if recorder.input_device and recorder.input_device.preferred_sample_rate:
            return recorder.input_device.preferred_sample_rate
        return 16000


class _ADCRecorderSession:
    def __init__(self, manager, stream):
        self._manager = manager
        self._stream = stream
        self.sample_rate = stream.sample_rate

    def start(self):
        self._manager._resolve_conflicts(self)
        self._manager._register_session(self)

        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(self._record_thread, ())

    def stop(self):
        if self._stream:
            self._stream.stop()
        self._manager._session_finished(self)

    def is_active(self):
        return self.is_recording()

    def is_recording(self):
        return self._stream is not None and self._stream.is_recording()

    def pin_usage(self):
        adc_pin = getattr(self._stream, "adc_pin", None)
        if adc_pin is None:
            return {}
        return {adc_pin: "adc"}

    def _record_thread(self):
        try:
            self._stream.record()
        finally:
            self._manager._session_finished(self)


class Player:
    def __init__(
        self,
        manager,
        file_path=None,
        rtttl=None,
        stream_type=None,
        on_complete=None,
        output=None,
        sample_rate=None,
        volume=None,
    ):
        self._manager = manager
        self.file_path = file_path
        self.rtttl = rtttl
        self.stream_type = stream_type
        self.on_complete = on_complete
        self.output = output
        self.sample_rate = sample_rate
        self.volume = volume
        self._stream = None
        self._buzzer = None

    def start(self):
        self._manager._start_player(self)

    def stop(self):
        if self._stream:
            self._stream.stop()
        if self._buzzer:
            try:
                self._buzzer.deinit()
            except Exception:
                pass
        self._manager._session_finished(self)

    def pause(self):
        if self._stream and hasattr(self._stream, "pause"):
            self._stream.pause()

    def resume(self):
        if self._stream and hasattr(self._stream, "resume"):
            self._stream.resume()

    def is_active(self):
        return self.is_playing()

    def is_playing(self):
        return self._stream is not None and self._stream.is_playing()

    def get_progress_percent(self):
        if self._stream and hasattr(self._stream, "get_progress_percent"):
            return self._stream.get_progress_percent()
        return None

    def get_progress_ms(self):
        if self._stream and hasattr(self._stream, "get_progress_ms"):
            return self._stream.get_progress_ms()
        return None

    def get_duration_ms(self):
        if self._stream and hasattr(self._stream, "get_duration_ms"):
            return self._stream.get_duration_ms()
        return None

    def pin_usage(self):
        if not self.output:
            return {}
        if self.output.kind == "buzzer":
            return {self.output.buzzer_pin: "buzzer"}
        if self.output.kind == "i2s":
            return _pin_map_i2s_output(self.output.i2s_pins)
        return {}

    def _play_thread(self):
        try:
            if self.output.kind == "buzzer":
                self._play_rtttl()
            else:
                self._play_wav()
        finally:
            if self._buzzer:
                try:
                    self._buzzer.deinit()
                except Exception:
                    pass
            self._manager._session_finished(self)

    def _play_rtttl(self):
        from mpos.audio.stream_rtttl import RTTTLStream
        from machine import Pin, PWM

        self._buzzer = PWM(Pin(self.output.buzzer_pin, Pin.OUT))
        self._buzzer.duty_u16(0)

        self._stream = RTTTLStream(
            rtttl_string=self.rtttl,
            stream_type=self.stream_type,
            volume=self.volume if self.volume is not None else self._manager._volume,
            buzzer_instance=self._buzzer,
            on_complete=self.on_complete,
        )
        self._stream.play()

    def _play_wav(self):
        from mpos.audio.stream_wav import WAVStream

        self._stream = WAVStream(
            file_path=self.file_path,
            stream_type=self.stream_type,
            volume=self.volume if self.volume is not None else self._manager._volume,
            i2s_pins=self.output.i2s_pins,
            on_complete=self.on_complete,
            requested_sample_rate=self.sample_rate,
        )
        self._stream.play()


class Recorder:
    def __init__(
        self,
        manager,
        file_path,
        input_device=None,
        sample_rate=None,
        on_complete=None,
        duration_ms=None,
        adc_config=None,
    ):
        self._manager = manager
        self.file_path = file_path
        self.input_device = input_device
        self.sample_rate = sample_rate
        self.on_complete = on_complete
        self.duration_ms = duration_ms
        self.adc_config = adc_config or {}
        self._stream = None

    def start(self):
        self._manager._start_recorder(self)

    def stop(self):
        if self._stream:
            self._stream.stop()
        self._manager._session_finished(self)

    def pause(self):
        if self._stream and hasattr(self._stream, "pause"):
            self._stream.pause()

    def resume(self):
        if self._stream and hasattr(self._stream, "resume"):
            self._stream.resume()

    def is_active(self):
        return self.is_recording()

    def is_recording(self):
        return self._stream is not None and self._stream.is_recording()

    def get_duration_ms(self):
        if self._stream and hasattr(self._stream, "get_duration_ms"):
            return self._stream.get_duration_ms()
        if self._stream and hasattr(self._stream, "get_elapsed_ms"):
            return self._stream.get_elapsed_ms()
        return None

    def pin_usage(self):
        if not self.input_device:
            return {}
        if self.input_device.kind == "adc":
            return {self.input_device.adc_mic_pin: "adc"}
        if self.input_device.kind == "i2s":
            return _pin_map_i2s_input(self.input_device.i2s_pins)
        return {}

    def _record_thread(self):
        try:
            if self.input_device.kind == "adc":
                self._record_adc()
            else:
                self._record_i2s()
        finally:
            self._manager._session_finished(self)

    def _record_i2s(self):
        from mpos.audio.stream_record import RecordStream

        self._stream = RecordStream(
            file_path=self.file_path,
            duration_ms=self.duration_ms,
            sample_rate=self.sample_rate,
            i2s_pins=self.input_device.i2s_pins,
            on_complete=self.on_complete,
        )
        self._stream.record()

    def _record_adc(self):
        from mpos.audio.stream_record_adc import ADCRecordStream

        self._stream = ADCRecordStream(
            file_path=self.file_path,
            duration_ms=self.duration_ms,
            sample_rate=self.sample_rate,
            adc_pin=self.input_device.adc_mic_pin,
            on_complete=self.on_complete,
            **self.adc_config,
        )
        self._stream.record()


def _pin_map_i2s_output(i2s_pins):
    pins = {}
    if i2s_pins.get("sck") is not None:
        pins[i2s_pins["sck"]] = "sck"
    pins[i2s_pins["ws"]] = "ws"
    pins[i2s_pins["sd"]] = "sd"
    if i2s_pins.get("mck") is not None:
        pins[i2s_pins["mck"]] = "mck"
    return pins


def _pin_map_i2s_input(i2s_pins):
    pins = {}
    sck_pin = i2s_pins.get("sck_in", i2s_pins.get("sck"))
    if sck_pin is not None:
        pins[sck_pin] = "sck"
    pins[i2s_pins["ws"]] = "ws"
    pins[i2s_pins["sd_in"]] = "sd_in"
    return pins
