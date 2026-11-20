from mpos import AudioManager, Intent, SettingsActivity, SharedPreferences

# The piezo disc only reproduces a narrow band around its resonance (~3-4 kHz),
# so harmonic-poor material is inaudible at unity gain. Overdriving the samples
# hard-clips them into square waves whose harmonics the disc can reproduce:
# 100 leaves the samples untouched, 3200 is the maximum boost.
BUZZER_GAIN_OPTIONS = [
    ("Off (clean)", "100"),
    ("Low", "200"),
    ("Medium", "400"),
    ("Strong", "800"),
    ("Max", "1600"),
    ("Extreme", "3200"),
]

# A multiple of the sample rate. Only a whole multiple keeps the duty updates
# in step with the carrier: a carrier that is not one (78 kHz for a 22.05 kHz
# file is 3.54x) makes the sample's duty land on a different number of carrier
# periods each time, and the disc turns speech into a constant squeal. Higher
# multiples move the switching noise further up at the cost of duty resolution.
BUZZER_CARRIER_OPTIONS = [
    ("Auto (sample rate)", "0"),
    ("2x sample rate", "2"),
    ("3x sample rate", "3"),
    ("4x sample rate", "4"),
    ("6x sample rate", "6"),
    ("8x sample rate", "8"),
]

# First-order high-pass before the overdrive, which pushes the 1-3 kHz part of
# speech up towards the disc's resonance.
BUZZER_EMPHASIS_OPTIONS = [
    ("Off", "0"),
    ("Low", "30"),
    ("Medium", "55"),
    ("High", "75"),
    ("Max", "90"),
]

# Ring modulation with a square carrier: moves the baseband into the disc's
# 2-5 kHz window. Sounds buzzy ("Donald Duck"), but puts far more energy where
# the disc can reproduce it.
BUZZER_MOD_OPTIONS = [
    ("Off", "0"),
    ("2 kHz", "2000"),
    ("2.5 kHz", "2500"),
    ("3 kHz", "3000"),
    ("3.5 kHz", "3500"),
    ("4 kHz", "4000"),
]


def _apply_buzzer_gain(value):
    if not value:
        return
    AudioManager.set_buzzer_tuning("buzzer_gain", value)


def _apply_buzzer_carrier(value):
    if not value:
        return
    AudioManager.set_buzzer_tuning("buzzer_carrier", value)


def _apply_buzzer_emphasis(value):
    if not value:
        return
    AudioManager.set_buzzer_tuning("buzzer_emphasis", value)


def _apply_buzzer_mod(value):
    if not value:
        return
    AudioManager.set_buzzer_tuning("buzzer_mod", value)


def _apply_input_device(name):
    if not name:
        return
    for device in AudioManager.get_inputs():
        if device.name == name:
            AudioManager.set_default_input(device)
            return


def _has_buzzer_output(setting=None):
    return AudioManager.find_output_by_kind("buzzer") is not None


def _apply_output_device(name):
    if not name:
        return
    for device in AudioManager.get_outputs():
        if device.name == name:
            AudioManager.set_default_output(device)
            return


class AudioSettings(SettingsActivity):
    PREFS_NAMESPACE = "com.micropythonos.settings.audio"

    def getIntent(self):
        intent = Intent()
        prefs = SharedPreferences(self.PREFS_NAMESPACE)

        inputs = AudioManager.get_inputs()
        outputs = AudioManager.get_outputs()

        input_options = [(device.name, device.name) for device in inputs]
        if not input_options:
            input_options = [("No input devices", "")]

        output_options = [(device.name, device.name) for device in outputs]
        if not output_options:
            output_options = [("No output devices", "")]

        default_input = AudioManager.get_default_input()
        default_output = AudioManager.get_default_output()

        intent.putExtra("prefs", prefs)
        intent.putExtra(
            "settings",
            [
                {
                    "title": "Input Device",
                    "key": "input_device",
                    "ui": "radiobuttons",
                    "ui_options": input_options,
                    "default_value": default_input.name if default_input else "",
                    "changed_callback": _apply_input_device,
                },
                {
                    "title": "Output Device",
                    "key": "output_device",
                    "ui": "radiobuttons",
                    "ui_options": output_options,
                    "default_value": default_output.name if default_output else "",
                    "changed_callback": _apply_output_device,
                },
                {
                    "title": "Buzzer Gain",
                    "key": "buzzer_gain",
                    "ui": "radiobuttons",
                    "ui_options": BUZZER_GAIN_OPTIONS,
                    "default_value": "800",
                    "changed_callback": _apply_buzzer_gain,
                    "should_show": _has_buzzer_output,
                },
                {
                    "title": "Buzzer Carrier",
                    "key": "buzzer_carrier",
                    "ui": "radiobuttons",
                    "ui_options": BUZZER_CARRIER_OPTIONS,
                    "default_value": "0",
                    "changed_callback": _apply_buzzer_carrier,
                    "should_show": _has_buzzer_output,
                },
                {
                    "title": "Buzzer Emphasis",
                    "key": "buzzer_emphasis",
                    "ui": "radiobuttons",
                    "ui_options": BUZZER_EMPHASIS_OPTIONS,
                    "default_value": "0",
                    "changed_callback": _apply_buzzer_emphasis,
                    "should_show": _has_buzzer_output,
                },
                {
                    "title": "Buzzer Ring Mod",
                    "key": "buzzer_mod",
                    "ui": "radiobuttons",
                    "ui_options": BUZZER_MOD_OPTIONS,
                    "default_value": "0",
                    "changed_callback": _apply_buzzer_mod,
                    "should_show": _has_buzzer_output,
                },
            ],
        )
        return intent
