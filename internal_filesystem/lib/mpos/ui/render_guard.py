"""
Render guard: on ESP32, skip an LVGL pass when the C stack it would run on is
too full to hold it, instead of letting the pass overflow the stack.

This is a workaround. Measurements and method:
https://github.com/MicroPythonOS/MicroPythonOS/pull/324

The problem
-----------
lvgl_micropython's TaskHandler (task_handler.py) does not run LVGL from a loop
of its own. A machine.Timer fires every period_ms (2 ms by default, see
change_task_handler() in mpos/main.py) and queues a pass with
micropython.schedule(). A pass is one lv.task_handler() call: LVGL timers,
input, layout, drawing and the display flush. MicroPython runs a scheduled
callback the next time the VM checks for pending events, on top of whatever
Python code is running at that moment. That is usually the main thread, but
ESP32 builds have the GIL enabled, so it can also be another Python thread.
So a pass starts at whatever stack depth that code has reached, and adds its
own C frames on top.

On ESP32 the main thread is the mp_task FreeRTOS task, whose C stack has a
fixed size of 16 KB. MicroPython checks the stack depth only inside its own
runtime (for example on Python calls, raising RuntimeError "maximum recursion
depth exceeded"). Most of a pass is LVGL C code (layout, drawing, font
rendering), which does not check, so a pass that needs more stack than is
left runs past the end of the stack, and the board resets or hangs instead of
raising an exception.

TaskHandler already skips a pass while Python code runs inside an LVGL
callback (lv._nesting != 0), which is why starting an app from a launcher tap
is safe. Starting one anywhere else is not: AppManager.start_app() from the
REPL or mpremote, from an asyncio task, or as auto_start_app at boot. BlockTV's
onCreate/onResume then ran 10 to 12 KB deep, and a pass that starts there
needs another 4.9 to 7.3 KB, depending on what it draws.

Measured on a Waveshare ESP32-S3-Touch-LCD-3.5:
- Without the guard, 7 of 7 REPL launches of BlockTV reset the board
  (machine.reset_cause() == machine.HARD_RESET), each one during or right
  after a pass that started while BlockTV was creating a TTF font. A plain
  REPL launch peaked at 16,048 of 16,384 bytes of stack.
- One pass needs 4.9 to 7.3 KB of stack. The worst measured was a Lightning
  Piggy redraw: 7,344 bytes.
- With the guard, 3 of 3 REPL launches survived, peaking at 13,968 to 14,384
  bytes.

There is no single faulty line to fix: the app's frames and the pass's frames
are each normal, only their sum is too large for the stack.

What it does
------------
install() registers on_task_handler() as a TASK_HANDLER_STARTED callback.
When less than RENDER_RESERVE (9 KB) of stack is left, it returns False and
TaskHandler skips that pass, as it already does while lv._nesting != 0. The
next timer tick tries again. LVGL's clock is advanced by the timer callback,
not by the pass, so it keeps running while passes are skipped.

When it triggers
----------------
Only when sys.platform == "esp32". MicroPython's esp32 port reports that on
every chip it supports, so the guard is active in all MicroPythonOS ESP32
builds: ESP32, ESP32-S3 and ESP32-P4. All of them use MicroPython's default
16 KB mp_task stack (MICROPY_TASK_STACK_SIZE): build_mpos.sh does not change
it, and the code that would apply the builder's --task-stack-size option is
commented out in lvgl_micropython's builder/esp32.py.

Even on ESP32 it skips a pass only when micropython.stack_use() is above
16,384 - 9,216 = 7,168 bytes. The numbers in this docstring were measured on
the ESP32-S3 only.

stack_use() counts against the stack of the thread that runs the pass. The
guard assumes that stack is 16 KB, which holds for mp_task and for threads
started with TaskManager.good_stack_size() (16 KB on ESP32). A pass that runs
on a thread with a smaller stack (the _thread default on ESP32 is 5 KB) is not
protected.

On desktop and web builds STACK_SIZE is None and every pass runs.

What it costs
-------------
Two small Python calls per pass. While the running code is more than about
7 KB deep, the screen does not update and LVGL timers, input and animations
wait until that code returns or yields. In a minute of BlockTV running,
passes started 3 to 6 KB deep and only a handful were skipped (while it
parsed a download); they ran as soon as the coroutine yielded. Code that
busy-waits more than 7 KB deep for something only an LVGL pass does (for
example a flag set by an LVGL timer) could now wait forever; it should yield
to asyncio.

It only guards passes run by TaskHandler. Code that calls lv.task_handler(),
lv.timer_handler() or lv.refr_now() itself is not covered.

How to remove it
----------------
The root fix is to never start a pass deep in the stack: run passes from a
shallow point instead of from micropython.schedule(), for example from an
asyncio task, as the web build's TaskHandler already does
(scripts/web_port/staged_lib/task_handler.py). That changes when every app's
UI updates: no pass would run while code blocks without yielding to asyncio.
If that lands, delete this module, its install() call in
change_task_handler() (mpos/main.py) and tests/test_render_guard.py.

A larger mp_task stack is not a root fix on its own: it costs internal RAM
(FreeRTOS allocates task stacks there) and only moves the limit. If the stack
size changes, set STACK_SIZE to the new MICROPY_TASK_STACK_SIZE; the guard
then skips passes only in code deeper than that minus RENDER_RESERVE.
"""

import sys

import micropython

# Size of the mp_task C stack (MICROPY_TASK_STACK_SIZE in the firmware), which
# micropython.stack_use() counts against when the pass runs on the main
# thread (see "When it triggers" above). MicroPython has no function that
# returns it (micropython.mem_info() only prints the limit), so it is
# hard-coded. It must not be larger than the real stack; if it is smaller, the
# guard just skips some passes that would have fit.
# None means "unknown": never skip a pass.
STACK_SIZE = 16 * 1024 if sys.platform == "esp32" else None

# Stack a pass may need: the worst measured pass (7,344 bytes) plus margin for
# passes heavier than the ones measured.
RENDER_RESERVE = 9 * 1024


def has_render_headroom():
    """True if a pass can start at the current stack depth."""
    if STACK_SIZE is None:
        return True
    return STACK_SIZE - micropython.stack_use() >= RENDER_RESERVE


def on_task_handler(event, user_data):
    """TASK_HANDLER_STARTED callback: returning False makes TaskHandler skip
    this pass. The next timer tick tries again."""
    return has_render_headroom()


def install(task_handler, started_event):
    """Called by change_task_handler() in mpos/main.py for every new
    TaskHandler."""
    task_handler.add_event_cb(on_task_handler, started_event)
