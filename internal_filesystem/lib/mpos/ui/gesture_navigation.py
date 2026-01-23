import lvgl as lv
from lvgl import LvReferenceError
from .anim import smooth_show, smooth_hide
from .view import back_screen
from mpos.ui import topmenu as topmenu
from .display import DisplayMetrics

downbutton = None
backbutton = None
down_start_x = 0
down_start_y = 0
back_start_y = 0
back_start_x = 0
short_movement_threshold = 10
backbutton_visible = False
downbutton_visible = False

def is_short_movement(dx, dy):
    return dx < short_movement_threshold and dy < short_movement_threshold

def _passthrough_click(x, y, indev):
    obj = lv.indev_search_obj(lv.screen_active(), lv.point_t({'x': x, 'y': y}))
    # print(f"Found object: {obj}")
    if obj:
        try:
            # print(f"Simulating press/click/release on {obj}")
            obj.send_event(lv.EVENT.PRESSED, indev)
            obj.send_event(lv.EVENT.CLICKED, indev)
            obj.send_event(lv.EVENT.RELEASED, indev) # gets lost
        except LvReferenceError as e:
            print(f"Object to click is gone: {e}")

def _back_swipe_cb(event):
    global backbutton, back_start_y, back_start_x, backbutton_visible
    event_code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x = point.x
    y = point.y
    dx = abs(x - back_start_x)
    dy = abs(y - back_start_y)
    #print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
    if event_code == lv.EVENT.PRESSED:
        back_start_y = y
        back_start_x = x
    elif event_code == lv.EVENT.PRESSING:
        should_show = not is_short_movement(dx, dy)
        if should_show != backbutton_visible:
            backbutton_visible = should_show
            smooth_show(backbutton) if should_show else smooth_hide(backbutton)
        backbutton.set_pos(round(x / 10), back_start_y)
    elif event_code == lv.EVENT.RELEASED:
        if backbutton_visible:
            backbutton_visible = False
            smooth_hide(backbutton)
        if x > DisplayMetrics.width() / 5:
            if topmenu.drawer_open :
                topmenu.close_drawer()
            else : 
                back_screen()
        elif is_short_movement(dx, dy):
            # print("Short movement - treating as tap")
            _passthrough_click(x, y, indev)

def _top_swipe_cb(event):
    if topmenu.drawer_open:
        print("ignoring top swipe gesture because drawer is open")
        return

    global downbutton, down_start_x, down_start_y, downbutton_visible
    event_code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x = point.x
    y = point.y
    dx = abs(x - down_start_x)
    dy = abs(y - down_start_y)
    # print(f"visual_back_swipe_cb event_code={event_code} and event_name={name} and pos: {x}, {y}")
    if event_code == lv.EVENT.PRESSED:
        down_start_x = x
        down_start_y = y
    elif event_code == lv.EVENT.PRESSING:
        should_show = not is_short_movement(dx, dy)
        if should_show != downbutton_visible:
            downbutton_visible = should_show
            smooth_show(downbutton) if should_show else smooth_hide(downbutton)
        downbutton.set_pos(down_start_x, round(y / 10))
    elif event_code == lv.EVENT.RELEASED:
        if downbutton_visible:
            downbutton_visible = False
            smooth_hide(downbutton)
        dx = abs(x - down_start_x)
        dy = abs(y - down_start_y)
        if y > DisplayMetrics.height() / 5:
            topmenu.open_drawer()
        elif is_short_movement(dx, dy):
            # print("Short movement - treating as tap")
            _passthrough_click(x, y, indev)

def handle_back_swipe():
    global backbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(topmenu.NOTIFICATION_BAR_HEIGHT, lv.layer_top().get_height()-topmenu.NOTIFICATION_BAR_HEIGHT) # narrow because it overlaps buttons
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    rect.set_scroll_dir(lv.DIR.NONE)
    rect.set_pos(0, topmenu.NOTIFICATION_BAR_HEIGHT)
    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    style.set_border_width(0)
    style.set_radius(0)
    if False: # debug the swipe zone with a red border
        style.set_bg_opa(15)
        style.set_border_width(4)
        style.set_border_color(lv.color_hex(0xFF0000))  # Red border for visibility
        style.set_border_opa(lv.OPA._50)  # 50% opacity for the border
    rect.add_style(style, 0)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.RELEASED, None)
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
    rect.set_size(lv.pct(100), topmenu.NOTIFICATION_BAR_HEIGHT)
    rect.set_pos(0, 0)
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    style.set_border_width(0)
    style.set_radius(0)
    if False: # debug the swipe zone with a red border
        style.set_bg_opa(15)
        style.set_border_width(4)
        style.set_border_color(lv.color_hex(0xFF0000))  # Red border for visibility
        style.set_border_opa(lv.OPA._50)  # 50% opacity for the border
    rect.add_style(style, 0)
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
