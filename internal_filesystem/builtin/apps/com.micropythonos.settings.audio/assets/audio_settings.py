from mpos import AudioManager, Intent, SettingsActivity, SharedPreferences


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
                },
                {
                    "title": "Output Device",
                    "key": "output_device",
                    "ui": "radiobuttons",
                    "ui_options": output_options,
                    "default_value": default_output.name if default_output else "",
                },
            ],
        )
        return intent
