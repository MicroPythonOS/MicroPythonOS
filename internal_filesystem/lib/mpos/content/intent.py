
class Intent:
    def __init__(self, activity_class=None, action=None, data=None, extras=None):
        self.activity_class = activity_class  # Explicit target (e.g., SettingsActivity)
        self.action = action  # Action string (e.g., "view", "share")
        self.data = data  # Single data item (e.g., URL)
        self.extras = extras or {}  # Dictionary for additional data
        self.flags = {}  # Simplified flags: {"clear_top": bool, "no_history": bool, "no_animation": bool}

    def addFlag(self, flag, value=True):
        self.flags[flag] = value
        return self

    def putExtra(self, key, value):
            self.extras[key] = value
            return self
