import lvgl as lv
from .anim import smooth_show, smooth_hide
from .view import back_screen
from .topmenu import open_drawer, drawer_open, NOTIFICATION_BAR_HEIGHT
from .display import get_display_width, get_display_height

downbutton = None
backbutton = None
down_start_x = 0
back_start_y = 0


# Would be better to somehow save other events, like clicks, and pass them down to the layers below if released with x < 60
def _back_swipe_cb(event):
    if drawer_open:
        print("ignoring back gesture because drawer is open")
        return

    global backbutton, back_start_y
    event_code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x = point.x
    y = point.y
    #print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
    if event_code == lv.EVENT.PRESSED:
        smooth_show(backbutton)
        back_start_y = y
    elif event_code == lv.EVENT.PRESSING:
        magnetic_x = round(x / 10)
        backbutton.set_pos(magnetic_x,back_start_y)
    elif event_code == lv.EVENT.RELEASED:
        smooth_hide(backbutton)
        if x > min(100, get_display_width() / 4):
            back_screen()


# Would be better to somehow save other events, like clicks, and pass them down to the layers below if released with x < 60
def _top_swipe_cb(event):
    if drawer_open:
        print("ignoring top swipe gesture because drawer is open")
        return

    global downbutton, down_start_x
    event_code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x = point.x
    y = point.y
    #print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
    if event_code == lv.EVENT.PRESSED:
        smooth_show(downbutton)
        down_start_x = x
    elif event_code == lv.EVENT.PRESSING:
        magnetic_y = round(y/ 10)
        downbutton.set_pos(down_start_x,magnetic_y)
    elif event_code == lv.EVENT.RELEASED:
        smooth_hide(downbutton)
        if y > min(80, get_display_height() / 4):
            open_drawer()


def handle_back_swipe():
    global backbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(round(NOTIFICATION_BAR_HEIGHT/2), lv.layer_top().get_height()-NOTIFICATION_BAR_HEIGHT) # narrow because it overlaps buttons
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    rect.set_scroll_dir(lv.DIR.NONE)
    rect.set_pos(0, NOTIFICATION_BAR_HEIGHT)
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
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.RELEASED, None)
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

def handle_top_swipe():
    global downbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(lv.pct(100), round(NOTIFICATION_BAR_HEIGHT*2/3))
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
    rect.add_event_cb(_top_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(_top_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(_top_swipe_cb, lv.EVENT.RELEASED, None)
    # button with label that shows up during the dragging:
    downbutton = lv.button(lv.layer_top())
    downbutton.set_pos(0, round(lv.layer_top().get_height() / 2))
    downbutton.add_flag(lv.obj.FLAG.HIDDEN)
    downbutton.add_state(lv.STATE.DISABLED)
    downlabel = lv.label(downbutton)
    downlabel.set_text(lv.SYMBOL.DOWN)
    downlabel.set_style_text_font(lv.font_montserrat_18, 0)
    downlabel.center()
