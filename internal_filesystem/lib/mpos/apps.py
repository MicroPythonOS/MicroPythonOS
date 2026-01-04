import lvgl as lv

import _thread
import traceback

import mpos.info
import mpos.ui
from mpos.app.activity import Activity
from mpos.content.intent import Intent
from mpos.content.package_manager import PackageManager

def good_stack_size():
    stacksize = 24*1024 # less than 20KB crashes on desktop when doing heavy apps, like LightningPiggy's Wallet connections
    import sys
    if sys.platform == "esp32":
        stacksize = 16*1024
    return stacksize

# Run the script in the current thread:
# Returns True if successful
def execute_script(script_source, is_file, classname, cwd=None):
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
        path_before = sys.path[:]  # Make a copy, not a reference
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
            classes = {k: v for k, v in script_globals.items() if isinstance(v, type)}
            functions = {k: v for k, v in script_globals.items() if callable(v) and not isinstance(v, type)}
            variables = {k: v for k, v in script_globals.items() if not callable(v)}
            print("Classes:", classes.keys()) # This lists a whole bunch of classes, including lib/mpos/ stuff
            print("Functions:", functions.keys())
            print("Variables:", variables.keys())
            main_activity = script_globals.get(classname)
            if main_activity:
                start_time = utime.ticks_ms()
                Activity.startActivity(None, Intent(activity_class=main_activity))
                end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                print(f"execute_script: Activity.startActivity took {end_time}ms")
            else:
                print(f"Warning: could not find app's main_activity {classname}")
                return False
        except Exception as e:
            print(f"Thread {thread_id}: exception during execution:")
            # Print stack trace with exception type, value, and traceback
            tb = getattr(e, '__traceback__', None)
            traceback.print_exception(type(e), e, tb)
            return False
        finally:
            # Always restore sys.path, even if we return early or raise an exception
            print(f"Thread {thread_id}: script {compile_name} finished, restoring sys.path from {sys.path} to {path_before}")
            sys.path = path_before
        return True
    except Exception as e:
        print(f"Thread {thread_id}: error:")
        tb = getattr(e, '__traceback__', None)
        traceback.print_exception(type(e), e, tb)
        return False

""" Unused:
# Run the script in a new thread:
# NOTE: check if the script exists here instead of launching a new thread?
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

# Returns True if successful
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
    entrypoint = "assets/main.py"
    classname = "Main"
    if not app.main_launcher_activity:
        print(f"WARNING: app {fullname} doesn't have a main_launcher_activity, defaulting to class {classname} in {entrypoint}")
    else:
        entrypoint = app.main_launcher_activity.get('entrypoint')
        classname = app.main_launcher_activity.get("classname")
    result = execute_script(app.installed_path + "/" + entrypoint, True, classname, app.installed_path + "/assets/")
    # Launchers have the bar, other apps don't have it
    if app.is_valid_launcher():
        mpos.ui.topmenu.open_bar()
    else:
        mpos.ui.topmenu.close_bar()
    end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
    print(f"start_app() took {end_time}ms")
    return result


# Starts the first launcher that's found
def restart_launcher():
    print("restart_launcher")
    # Stop all apps
    mpos.ui.remove_and_stop_all_activities()
    # No need to stop the other launcher first, because it exits after building the screen
    return start_app(PackageManager.get_launcher().fullname)

