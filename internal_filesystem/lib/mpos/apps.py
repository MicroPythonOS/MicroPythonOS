import lvgl as lv

import uio
import ujson
import uos
import utime # for timing calls

import _thread
import traceback

import mpos.info
import mpos.ui
from mpos.package_manager import PackageManager

def good_stack_size():
    stacksize = 24*1024
    import sys
    if sys.platform == "esp32":
        stacksize = 16*1024
    return stacksize

# Run the script in the current thread:
def execute_script(script_source, is_file, cwd=None, classname=None):
    import utime # for timing read and compile
    thread_id = _thread.get_ident()
    compile_name = 'script' if not is_file else script_source
    print(f"Thread {thread_id}: executing script with cwd: {cwd}")
    try:
        if is_file:
            print(f"Thread {thread_id}: reading script from file {script_source}")
            with open(script_source, 'r') as f: # No need to check if it exists as exceptions are caught
                start_time = utime.ticks_ms()
                script_source = f.read()
                read_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                print(f"execute_script: reading script_source took {read_time}ms")
        script_globals = {
            'lv': lv,
            '__name__': "__main__"
        }
        print(f"Thread {thread_id}: starting script")
        import sys
        path_before = sys.path
        if cwd:
            sys.path.append(cwd)
        try:
            start_time = utime.ticks_ms()
            compiled_script = compile(script_source, compile_name, 'exec')
            compile_time = utime.ticks_diff(utime.ticks_ms(), start_time)
            print(f"execute_script: compiling script_source took {compile_time}ms")
            start_time = utime.ticks_ms()
            exec(compiled_script, script_globals)
            end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
            print(f"apps.py execute_script: exec took {end_time}ms")
            # Introspect globals
            #classes = {k: v for k, v in script_globals.items() if isinstance(v, type)}
            #functions = {k: v for k, v in script_globals.items() if callable(v) and not isinstance(v, type)}
            #variables = {k: v for k, v in script_globals.items() if not callable(v)}
            #print("Classes:", classes.keys())
            #print("Functions:", functions.keys())
            #print("Variables:", variables.keys())
            if classname:
                main_activity = script_globals.get(classname)
                if main_activity:
                    start_time = utime.ticks_ms()
                    Activity.startActivity(None, Intent(activity_class=main_activity))
                    end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                    print(f"execute_script: Activity.startActivity took {end_time}ms")
                else:
                    print("Warning: could not find main_activity")
        except Exception as e:
            print(f"Thread {thread_id}: exception during execution:")
            # Print stack trace with exception type, value, and traceback
            tb = getattr(e, '__traceback__', None)
            traceback.print_exception(type(e), e, tb)
        print(f"Thread {thread_id}: script {compile_name} finished")
        sys.path = path_before
    except Exception as e:
        print(f"Thread {thread_id}: error:")
        tb = getattr(e, '__traceback__', None)
        traceback.print_exception(type(e), e, tb)

""" Unused:
# Run the script in a new thread:
# TODO: check if the script exists here instead of launching a new thread?
def execute_script_new_thread(scriptname, is_file):
    print(f"main.py: execute_script_new_thread({scriptname},{is_file})")
    try:
        # 168KB maximum at startup but 136KB after loading display, drivers, LVGL gui etc so let's go for 128KB for now, still a lot...
        # But then no additional threads can be created. A stacksize of 32KB allows for 4 threads, so 3 in the app itself, which might be tight.
        # 16KB allows for 10 threads in the apps, but seems too tight for urequests on unix (desktop) targets
        # 32KB seems better for the camera, but it forced me to lower other app threads from 16 to 12KB
        #_thread.stack_size(24576) # causes camera issue...
        # NOTE: This doesn't do anything if apps are started in the same thread!
        if "camtest" in scriptname:
            print("Starting camtest with extra stack size!")
            stack=32*1024
        elif "appstore" in scriptname:
            print("Starting appstore with extra stack size!")
            stack=24*1024 # this doesn't do anything because it's all started in the same thread
        else:
            stack=16*1024 # 16KB doesn't seem to be enough for the AppStore app on desktop
        stack = mpos.apps.good_stack_size()
        print(f"app.py: setting stack size for script to {stack}")
        _thread.stack_size(stack)
        _thread.start_new_thread(execute_script, (scriptname, is_file))
    except Exception as e:
        print("main.py: execute_script_new_thread(): error starting new thread thread: ", e)
"""

def start_app(fullname):
    mpos.ui.set_foreground_app(fullname)
    import utime
    start_time = utime.ticks_ms()
    app = PackageManager.get(fullname)
    if not app:
        print(f"Warning: start_app can't find app {fullname}")
        return
    if not app.installed_path:
        print(f"Warning: start_app can't start {fullname} because no it doesn't have an installed_path")
        return
    if not app.main_launcher_activity:
        print(f"WARNING: start_app can't start {fullname} because it doesn't have a main_launcher_activity")
        return
    start_script_fullpath = f"{app.installed_path}/{app.main_launcher_activity.get('entrypoint')}"
    execute_script(start_script_fullpath, True, app.installed_path + "/assets/", app.main_launcher_activity.get("classname"))
    # Launchers have the bar, other apps don't have it
    if app.is_valid_launcher():
        mpos.ui.topmenu.open_bar()
    else:
        mpos.ui.topmenu.close_bar()
    end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
    print(f"start_app() took {end_time}ms")

# Starts the first launcher that's found
def restart_launcher():
    print("restart_launcher")
    mpos.ui.empty_screen_stack()
    # No need to stop the other launcher first, because it exits after building the screen
    for app in mpos.package_manager.PackageManager.get_app_list():
        if app.is_valid_launcher():
            print(f"Found launcher, starting {app.fullname}")
            start_app(app.fullname)
            break

class App:
    # ------------------------------------------------------------------ #
    #  Regular constructor – use when you already have the data
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        name="Unknown",
        publisher="Unknown",
        short_description="",
        long_description="",
        icon_url="",
        download_url="",
        fullname="Unknown",
        version="0.0.0",
        category="",
        activities=None,
        installed_path=None,
    ):
        self.name = name
        self.publisher = publisher
        self.short_description = short_description
        self.long_description = long_description
        self.icon_url = icon_url
        self.download_url = download_url
        self.fullname = fullname
        self.version = version
        self.category = category
        self.activities = activities if activities is not None else []
        self.installed_path = installed_path

        # Cached image fields (kept for compatibility)
        self.image = None
        self.image_dsc = None

        # Find the main launcher activity once, at construction time
        self.main_launcher_activity = self._find_main_launcher_activity()

    # ------------------------------------------------------------------ #
    #  Human-readable representation
    # ------------------------------------------------------------------ #
    def __str__(self):
        return (
            f"App(name='{self.name}', "
            f"publisher='{self.publisher}', "
            f"short_description='{self.short_description}', "
            f"version='{self.version}', "
            f"category='{self.category}', "
            f"activities={len(self.activities)} items, "
            f"installed_path={self.installed_path})"
        )

    # ------------------------------------------------------------------ #
    #  Private helper – locate the MAIN/LAUNCHER activity
    # ------------------------------------------------------------------ #
    def _find_main_launcher_activity(self):
        for activity in self.activities:
            if not activity.get("entrypoint") or not activity.get("classname"):
                print("Warning: activity missing entrypoint or classname – skipping")
                continue

            for intent_filter in activity.get("intent_filters", []):
                if (
                    intent_filter.get("action") == "main"
                    and intent_filter.get("category") == "launcher"
                ):
                    print("Found main launcher activity!")
                    return activity
        return None

    # ------------------------------------------------------------------ #
    #  Convenience check for launcher-type apps
    # ------------------------------------------------------------------ #
    def is_valid_launcher(self):
        return self.category == "launcher" and self.main_launcher_activity is not None

    # ------------------------------------------------------------------ #
    #  Class-method constructor that builds an App from a manifest file
    # ------------------------------------------------------------------ #
    @classmethod
    def from_manifest(cls, appdir):
        """
        Parse <appdir>/META-INF/MANIFEST.JSON and return a fully-populated
        App instance.  If the file cannot be read, a default App with
        placeholder values is returned.
        """
        print(f"parse_manifest({appdir})")
        manifest_path = f"{appdir}/META-INF/MANIFEST.JSON"

        # Minimal default instance – guarantees every field has a fallback
        default = cls(installed_path=appdir)

        try:
            with open(manifest_path, "r") as f:
                data = ujson.load(f)
        except OSError as exc:
            print(f"parse_manifest: error loading {manifest_path} – {exc}")
            return default

        # Merge manifest data with defaults
        return cls(
            name=data.get("name", default.name),
            publisher=data.get("publisher", default.publisher),
            short_description=data.get("short_description", default.short_description),
            long_description=data.get("long_description", default.long_description),
            icon_url=data.get("icon_url", default.icon_url),
            download_url=data.get("download_url", default.download_url),
            fullname=data.get("fullname", default.fullname),
            version=data.get("version", default.version),
            category=data.get("category", default.category),
            activities=data.get("activities", default.activities),
            installed_path=appdir,
        )


class Activity:

    def __init__(self):
        self.intent = None  # Store the intent that launched this activity
        self.result = None
        self._result_callback = None

    def onCreate(self):
        pass
    def onStart(self, screen):
        pass
    def onResume(self, screen):
        pass
    def onPause(self, screen):
        pass
    def onStop(self, screen):
        pass
    def onDestroy(self, screen):
        pass

    def setContentView(self, screen):
        mpos.ui.setContentView(self, screen)

    def startActivity(self, intent):
        ActivityNavigator.startActivity(intent)

    def startActivityForResult(self, intent, result_callback):
        ActivityNavigator.startActivityForResult(intent, result_callback)

    def initError(self, e):
        print(f"WARNING: You might have inherited from Activity with a custom __init__() without calling super().__init__(). Got AttributeError: {e}")

    def getIntent(self):
        try:
            return self.intent
        except AttributeError as e:
            self.initError(e)

    def setResult(self, result_code, data=None):
        """Set the result to be returned when the activity finishes."""
        try:
            self.result = {"result_code": result_code, "data": data or {}}
        except AttributeError as e:
            self.initError(e)

    def finish(self):
        mpos.ui.back_screen()
        try:
            if self._result_callback and self.result:
                self._result_callback(self.result)
                self._result_callback = None  # Clean up
        except AttributeError as e:
            self.initError(e)

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


class ActivityNavigator:
    @staticmethod
    def startActivity(intent):
        if not isinstance(intent, Intent):
            raise ValueError("Must provide an Intent")
        if intent.action:  # Implicit intent: resolve handlers
            handlers = APP_REGISTRY.get(intent.action, [])
            if len(handlers) == 1:
                intent.activity_class = handlers[0]
                ActivityNavigator._launch_activity(intent)
            elif handlers:
                ActivityNavigator._show_chooser(intent, handlers)
            else:
                raise ValueError(f"No handlers for action: {intent.action}")
        else:
            ActivityNavigator._launch_activity(intent)

    @staticmethod
    def startActivityForResult(intent, result_callback):
        """Launch an activity and pass a callback for the result."""
        if not isinstance(intent, Intent):
            raise ValueError("Must provide an Intent")
        if intent.action:  # Implicit intent: resolve handlers
            handlers = APP_REGISTRY.get(intent.action, [])
            if len(handlers) == 1:
                intent.activity_class = handlers[0]
                return ActivityNavigator._launch_activity(intent, result_callback)
            elif handlers:
                ActivityNavigator._show_chooser(intent, handlers)
                return None  # Chooser handles result forwarding
            else:
                raise ValueError(f"No handlers for action: {intent.action}")
        else:
            return ActivityNavigator._launch_activity(intent, result_callback)

    @staticmethod
    def _launch_activity(intent, result_callback=None):
        """Launch an activity and set up result callback."""
        activity = intent.activity_class()
        activity.intent = intent
        activity._result_callback = result_callback  # Pass callback to activity
        start_time = utime.ticks_ms()
        mpos.ui.save_and_clear_current_focusgroup()
        activity.onCreate()
        end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        print(f"apps.py _launch_activity: activity.onCreate took {end_time}ms")
        return activity

    @staticmethod
    def _show_chooser(intent, handlers):
        chooser_intent = Intent(ChooserActivity, extras={"original_intent": intent, "handlers": [h.__name__ for h in handlers]})
        ActivityNavigator._launch_activity(chooser_intent)


class ChooserActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get handlers from intent extras
        original_intent = self.getIntent().extras.get("original_intent")
        handlers = self.getIntent().extras.get("handlers", [])
        label = lv.label(screen)
        label.set_text("Choose an app")
        label.set_pos(10, 10)

        for i, handler_name in enumerate(handlers):
            btn = lv.btn(screen)
            btn.set_user_data(f"handler_{i}")
            btn_label = lv.label(btn)
            btn_label.set_text(handler_name)
            btn.set_pos(10, 50 * (i + 1) + 10)
            btn.add_event_cb(lambda e, h=handler_name, oi=original_intent: self._select_handler(h, oi), lv.EVENT.CLICKED)
        self.setContentView(screen)

    def _select_handler(self, handler_name, original_intent):
        for handler in APP_REGISTRY.get(original_intent.action, []):
            if handler.__name__ == handler_name:
                original_intent.activity_class = handler
                navigator.startActivity(original_intent)
                break
        navigator.finish()  # Close chooser

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ChooserActivity":
            print("Stopped for Chooser")
        else:
            print("Stopped for other screen")


class ViewActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get content from intent (prefer extras.url, fallback to data)
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        label = lv.label(screen)
        label.set_user_data("content_label")
        label.set_text(f"Viewing: {content}")
        label.center()
        self.setContentView(screen)

    def onStart(self, screen):
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        for i in range(screen.get_child_cnt()):
            if screen.get_child(i).get_user_data() == "content_label":
                screen.get_child(i).set_text(f"Viewing: {content}")

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ViewActivity":
            print("Stopped for View")
        else:
            print("Stopped for other screen")

class ShareActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get text from intent (prefer extras.text, fallback to data)
        text = self.getIntent().extras.get("text", self.getIntent().data or "No text")
        label = lv.label(screen)
        label.set_user_data("share_label")
        label.set_text(f"Share: {text}")
        label.set_pos(10, 10)

        btn = lv.btn(screen)
        btn.set_user_data("share_btn")
        btn_label = lv.label(btn)
        btn_label.set_text("Share")
        btn.set_pos(10, 50)
        btn.add_event_cb(lambda e: self._share_content(text), lv.EVENT.CLICKED)
        self.setContentView(screen)

    def _share_content(self, text):
        # Dispatch to another app (e.g., MessagingActivity) or simulate sharing
        print(f"Sharing: {text}")  # Placeholder for actual sharing
        # Example: Launch another share handler
        navigator.startActivity(Intent(action="share", data=text))
        navigator.finish()  # Close ShareActivity

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ShareActivity":
            print("Stopped for Share")
        else:
            print("Stopped for other screen")

APP_REGISTRY = { # This should be handled by a new class PackageManager:
    "view": [ViewActivity],  # Hypothetical activities
    "share": [ShareActivity]
}
