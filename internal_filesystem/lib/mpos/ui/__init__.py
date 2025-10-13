import lvgl as lv
import mpos.apps
import mpos.time
import mpos.wifi
from mpos.ui.anim import WidgetAnimator
import mpos.ui.topmenu

th = None

# These get set by init_rootscreen():
horizontal_resolution = None
vertical_resolution = None

down_start_x = 0
back_start_y = 0

# Widgets:
downbutton = None
backbutton = None

foreground_app_name=None

def get_pointer_xy():
    indev = lv.indev_active()
    if indev:
        point = lv.point_t()
        indev.get_point(point)
        return point.x, point.y
    else:
        return -1,-1 # make it visible that this occurred

# Shutdown function to run in main thread
def shutdown():
    print("Shutting down...")
    lv.deinit()  # Deinitialize LVGL (if supported)
    # Add driver cleanup here
    import sys
    sys.exit(0)

def set_foreground_app(appname):
    global foreground_app_name
    foreground_app_name = appname
    print(f"foreground app is: {foreground_app_name}")

def show_launcher():
    mpos.apps.restart_launcher()

def init_rootscreen():
    global horizontal_resolution, vertical_resolution
    rootscreen = lv.screen_active()
    horizontal_resolution = rootscreen.get_display().get_horizontal_resolution()
    vertical_resolution = rootscreen.get_display().get_vertical_resolution()
    # Create a style for the undecorated screen
    style = lv.style_t()
    style.init()
    # Remove background (make it transparent or set no color)
    style.set_bg_opa(lv.OPA.TRANSP)  # Transparent background
    style.set_border_width(0)        # No border
    style.set_outline_width(0)       # No outline
    style.set_shadow_width(0)        # No shadow
    style.set_pad_all(0)             # No padding
    style.set_radius(0)              # No corner radius (sharp edges)
    # Apply the style to the screen
    rootscreen.add_style(style, 0)
    rootscreen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    rootscreen.set_scroll_dir(lv.DIR.NONE)
    rootlabel = lv.label(rootscreen)
    rootlabel.set_text("Welcome to MicroPythonOS")
    rootlabel.center()


EVENT_MAP = {
    lv.EVENT.ALL: "ALL",
    lv.EVENT.CANCEL: "CANCEL",
    lv.EVENT.CHILD_CHANGED: "CHILD_CHANGED",
    lv.EVENT.CHILD_CREATED: "CHILD_CREATED",
    lv.EVENT.CHILD_DELETED: "CHILD_DELETED",
    lv.EVENT.CLICKED: "CLICKED",
    lv.EVENT.COLOR_FORMAT_CHANGED: "COLOR_FORMAT_CHANGED",
    lv.EVENT.COVER_CHECK: "COVER_CHECK",
    lv.EVENT.CREATE: "CREATE",
    lv.EVENT.DEFOCUSED: "DEFOCUSED",
    lv.EVENT.DELETE: "DELETE",
    lv.EVENT.DRAW_MAIN: "DRAW_MAIN",
    lv.EVENT.DRAW_MAIN_BEGIN: "DRAW_MAIN_BEGIN",
    lv.EVENT.DRAW_MAIN_END: "DRAW_MAIN_END",
    lv.EVENT.DRAW_POST: "DRAW_POST",
    lv.EVENT.DRAW_POST_BEGIN: "DRAW_POST_BEGIN",
    lv.EVENT.DRAW_POST_END: "DRAW_POST_END",
    lv.EVENT.DRAW_TASK_ADDED: "DRAW_TASK_ADDED",
    lv.EVENT.FLUSH_FINISH: "FLUSH_FINISH",
    lv.EVENT.FLUSH_START: "FLUSH_START",
    lv.EVENT.FLUSH_WAIT_FINISH: "FLUSH_WAIT_FINISH",
    lv.EVENT.FLUSH_WAIT_START: "FLUSH_WAIT_START",
    lv.EVENT.FOCUSED: "FOCUSED",
    lv.EVENT.GESTURE: "GESTURE",
    lv.EVENT.GET_SELF_SIZE: "GET_SELF_SIZE",
    lv.EVENT.HIT_TEST: "HIT_TEST",
    lv.EVENT.HOVER_LEAVE: "HOVER_LEAVE",
    lv.EVENT.HOVER_OVER: "HOVER_OVER",
    lv.EVENT.INDEV_RESET: "INDEV_RESET",
    lv.EVENT.INSERT: "INSERT",
    lv.EVENT.INVALIDATE_AREA: "INVALIDATE_AREA",
    lv.EVENT.KEY: "KEY",
    lv.EVENT.LAST: "LAST",
    lv.EVENT.LAYOUT_CHANGED: "LAYOUT_CHANGED",
    lv.EVENT.LEAVE: "LEAVE",
    lv.EVENT.LONG_PRESSED: "LONG_PRESSED",
    lv.EVENT.LONG_PRESSED_REPEAT: "LONG_PRESSED_REPEAT",
    lv.EVENT.PREPROCESS: "PREPROCESS",
    lv.EVENT.PRESSED: "PRESSED",
    lv.EVENT.PRESSING: "PRESSING",
    lv.EVENT.PRESS_LOST: "PRESS_LOST",
    lv.EVENT.READY: "READY",
    lv.EVENT.REFRESH: "REFRESH",
    lv.EVENT.REFR_EXT_DRAW_SIZE: "REFR_EXT_DRAW_SIZE",
    lv.EVENT.REFR_READY: "REFR_READY",
    lv.EVENT.REFR_REQUEST: "REFR_REQUEST",
    lv.EVENT.REFR_START: "REFR_START",
    lv.EVENT.RELEASED: "RELEASED",
    lv.EVENT.RENDER_READY: "RENDER_READY",
    lv.EVENT.RENDER_START: "RENDER_START",
    lv.EVENT.RESOLUTION_CHANGED: "RESOLUTION_CHANGED",
    lv.EVENT.ROTARY: "ROTARY",
    lv.EVENT.SCREEN_LOADED: "SCREEN_LOADED",
    lv.EVENT.SCREEN_LOAD_START: "SCREEN_LOAD_START",
    lv.EVENT.SCREEN_UNLOADED: "SCREEN_UNLOADED",
    lv.EVENT.SCREEN_UNLOAD_START: "SCREEN_UNLOAD_START",
    lv.EVENT.SCROLL: "SCROLL",
    lv.EVENT.SCROLL_BEGIN: "SCROLL_BEGIN",
    lv.EVENT.SCROLL_END: "SCROLL_END",
    lv.EVENT.SCROLL_THROW_BEGIN: "SCROLL_THROW_BEGIN",
    lv.EVENT.SHORT_CLICKED: "SHORT_CLICKED",
    lv.EVENT.SIZE_CHANGED: "SIZE_CHANGED",
    lv.EVENT.STYLE_CHANGED: "STYLE_CHANGED",
    lv.EVENT.VALUE_CHANGED: "VALUE_CHANGED",
    lv.EVENT.VSYNC: "VSYNC"
}

# Function to translate event code to name
def get_event_name(event_code):
    return EVENT_MAP.get(event_code, f"Unknown event {event_code}")


def close_top_layer_msgboxes():
    """
    Iterate through all widgets in lv.layer_top() and close any lv.msgbox instances.
    """
    top_layer = lv.layer_top()
    if not top_layer:
        print("No top layer found")
        return

    # Get number of children
    child_count = top_layer.get_child_count_by_type(lv.msgbox_backdrop_class)
    print(f"Top layer has {child_count} msgbox_backdrops")

    # Iterate through children (use index to avoid modifying list during deletion)
    i = 0
    while i < top_layer.get_child_count_by_type(lv.msgbox_backdrop_class):
        child = top_layer.get_child_by_type(i,lv.msgbox_backdrop_class)
        print("Found msgbox, closing it")
        msgbox = child.get_child_by_type(0,lv.msgbox_class)
        msgbox.close()  # Close the message box
        # Note: lv.msgbox_close() may delete the object, so child count may change

    # Optional: Verify no msgboxes remain
    child_count = top_layer.get_child_count_by_type(lv.msgbox_backdrop_class)
    if child_count == 0:
        print("All msgboxes closed, top layer empty")
    else:
        print(f"Top layer still has {child_count} children")


screen_stack = [] # Stack of (activity, screen) tuples

def empty_screen_stack():
    global screen_stack
    screen_stack.clear()

# new_activity might be None for compatibility, can be removed if compatibility is no longer needed
def setContentView(new_activity, new_screen):
    global screen_stack

    # Get current activity and screen
    current_activity, current_screen = None, None
    if len(screen_stack) > 0:
        current_activity, current_screen = screen_stack[-1]

    if current_activity and current_screen:
        # Notify current activity that it's being backgrounded:
        current_activity.onPause(current_screen)
        current_activity.onStop(current_screen)
        # don't destroy because the user might go back to it

    # Start the new one:
    print("Appending screen to screen_stack")
    screen_stack.append((new_activity, new_screen))
    close_top_layer_msgboxes() # otherwise they remain
    if new_activity:
        #start_time = utime.ticks_ms()
        new_activity.onStart(new_screen)  # Initialize UI elements
        #end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        #print(f"ui.py setContentView: new_activity.onStart took {end_time}ms")

    #start_time = utime.ticks_ms()
    lv.screen_load_anim(new_screen, lv.SCR_LOAD_ANIM.OVER_LEFT, 500, 0, False)
    #end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
    #print(f"ui.py setContentView: screen_load took {end_time}ms")

    if new_activity:
        #start_time = utime.ticks_ms()
        new_activity.onResume(new_screen)  # Screen is now active
        #end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        #print(f"ui.py setContentView: new_activity.onResume took {end_time}ms")

def remove_and_stop_current_activity():
    current_activity, current_screen = screen_stack.pop()  # Get current activity and its screen
    if current_activity:
        current_activity.onPause(current_screen)
        current_activity.onStop(current_screen)
        current_activity.onDestroy(current_screen)

def back_screen():
    print("back_screen() running")
    global screen_stack
    if len(screen_stack) <= 1:
        print("Warning: can't go back because screen_stack is empty.")
        return False  # No previous screen
    #close_top_layer_msgboxes() # would be nicer to "cancel" all input events
    remove_and_stop_current_activity()
    prev_activity, prev_screen = screen_stack[-1] # load previous screen
    print("loading prev_screen with animation")
    lv.screen_load_anim(prev_screen, lv.SCR_LOAD_ANIM.OVER_RIGHT, 500, 0, True) #  True means delete the old screen, which is fine as we're going back and current_activity.onDestroy() was called
    if prev_activity:
        prev_activity.onResume(prev_screen)
    if len(screen_stack) == 1:
        mpos.ui.topmenu.open_bar()


# Would be better to somehow save other events, like clicks, and pass them down to the layers below if released with x < 60
def back_swipe_cb(event):
    if mpos.ui.topmenu.drawer_open:
        print("ignoring back gesture because drawer is open")
        return

    global backbutton, back_start_y
    event_code = event.get_code()
    #name = mpos.ui.get_event_name(event_code)
    indev = lv.indev_active()
    if indev:
        point = lv.point_t()
        indev.get_point(point)
        x = point.x
        y = point.y
        #print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
        if event_code == lv.EVENT.PRESSED:
            mpos.ui.anim.smooth_show(backbutton)
            back_start_y = y
        elif event_code == lv.EVENT.PRESSING:
            magnetic_x = round(x / 10)
            backbutton.set_pos(magnetic_x,back_start_y)
        elif event_code == lv.EVENT.RELEASED:
            mpos.ui.anim.smooth_hide(backbutton)
            if x > min(100,horizontal_resolution / 3):
                mpos.ui.back_screen()

def handle_back_swipe():
    global backbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(round(mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT/2), lv.layer_top().get_height()-mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT) # narrow because it overlaps buttons
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    rect.set_scroll_dir(lv.DIR.NONE)
    rect.set_pos(0, mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT)
    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    style.set_border_width(0)
    style.set_radius(0)
    if False: # debug the back swipe zone with a red border
        style.set_bg_opa(15)
        style.set_border_width(4)
        style.set_border_color(lv.color_hex(0xFF0000))  # Red border for visibility
        style.set_border_opa(lv.OPA._50)  # 50% opacity for the border
    rect.add_style(style, 0)
    #rect.add_flag(lv.obj.FLAG.CLICKABLE)  # Make the object clickable
    #rect.add_flag(lv.obj.FLAG.GESTURE_BUBBLE)  # Allow dragging
    rect.add_event_cb(back_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(back_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(back_swipe_cb, lv.EVENT.RELEASED, None)
    #rect.add_event_cb(back_swipe_cb, lv.EVENT.ALL, None)
    # button with label that shows up during the dragging:
    backbutton = lv.button(lv.layer_top())
    backbutton.set_pos(0, round(lv.layer_top().get_height() / 2))
    backbutton.add_flag(lv.obj.FLAG.HIDDEN)
    backbutton.add_state(lv.STATE.DISABLED)
    backlabel = lv.label(backbutton)
    backlabel.set_text(lv.SYMBOL.LEFT)
    backlabel.set_style_text_font(lv.font_montserrat_18, 0)
    backlabel.center()

# Would be better to somehow save other events, like clicks, and pass them down to the layers below if released with x < 60
def top_swipe_cb(event):
    if mpos.ui.topmenu.drawer_open:
        print("ignoring top swipe gesture because drawer is open")
        return

    global downbutton, down_start_x
    event_code = event.get_code()
    name = mpos.ui.get_event_name(event_code)
    indev = lv.indev_active()
    if indev:
        point = lv.point_t()
        indev.get_point(point)
        x = point.x
        y = point.y
        #print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
        if event_code == lv.EVENT.PRESSED:
            mpos.ui.anim.smooth_show(downbutton)
            down_start_x = x
        elif event_code == lv.EVENT.PRESSING:
            magnetic_y = round(y/ 10)
            downbutton.set_pos(down_start_x,magnetic_y)
        elif event_code == lv.EVENT.RELEASED:
            mpos.ui.anim.smooth_hide(downbutton)
            if y > min(80,vertical_resolution / 3):
                mpos.ui.topmenu.open_drawer()


def handle_top_swipe():
    global downbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(lv.pct(100), round(mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT*2/3))
    rect.set_pos(0, 0)
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    #style.set_bg_opa(15)
    style.set_border_width(0)
    style.set_radius(0)
    #style.set_border_color(lv.color_hex(0xFF0000))  # White border for visibility
    #style.set_border_opa(lv.OPA._50)  # 50% opacity for the border
    rect.add_style(style, 0)
    #rect.add_flag(lv.obj.FLAG.CLICKABLE)  # Make the object clickable
    #rect.add_flag(lv.obj.FLAG.GESTURE_BUBBLE)  # Allow dragging
    rect.add_event_cb(top_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(top_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(top_swipe_cb, lv.EVENT.RELEASED, None)
    # button with label that shows up during the dragging:
    downbutton = lv.button(lv.layer_top())
    downbutton.set_pos(0, round(lv.layer_top().get_height() / 2))
    downbutton.add_flag(lv.obj.FLAG.HIDDEN)
    downbutton.add_state(lv.STATE.DISABLED)
    downlabel = lv.label(downbutton)
    downlabel.set_text(lv.SYMBOL.DOWN)
    downlabel.set_style_text_font(lv.font_montserrat_18, 0)
    downlabel.center()


def pct_of_display_width(percent):
    return round(horizontal_resolution * percent / 100)

def pct_of_display_height(percent):
    return round(vertical_resolution * percent / 100)

def min_resolution():
    return min(mpos.ui.horizontal_resolution,mpos.ui.vertical_resolution)

def max_resolution():
    return max(mpos.ui.horizontal_resolution,mpos.ui.vertical_resolution)
