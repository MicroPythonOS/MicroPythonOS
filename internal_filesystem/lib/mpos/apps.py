import lvgl as lv

import _thread
import traceback

import mpos.info
import mpos.ui
from mpos.app.activity import Activity
from mpos.content.intent import Intent
from mpos.content.pm import PackageManager
# the code uses things like:
# mpos.ui.set_foreground_app(fullname)
# Activity.startActivity(None, Intent(activity_class=main_activity))

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
    for app in PackageManager.get_app_list():
        if app.is_valid_launcher():
            print(f"Found launcher, starting {app.fullname}")
            start_app(app.fullname)
            break

