# lib/mpos/ui/widget.py
import lvgl as lv
from .anim import smooth_show, smooth_hide
from .view import back_screen
from .topmenu import open_drawer, drawer_open
from .display import get_display_width, get_display_height

downbutton = None
backbutton = None
down_start_x = 0
back_start_y = 0

def _back_swipe_cb(event):
    if drawer_open:
        return
    global back_start_y, backbutton
    code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x, y = point.x, point.y

    if code == lv.EVENT.PRESSED:
        smooth_show(backbutton)
        back_start_y = y
    elif code == lv.EVENT.PRESSING:
        magnetic_x = round(x / 10)
        backbutton.set_pos(magnetic_x, back_start_y)
    elif code == lv.EVENT.RELEASED:
        smooth_hide(backbutton)
        if x > min(100, get_display_width() / 3):
            back_screen()

def _top_swipe_cb(event):
    if drawer_open:
        return
    global down_start_x, downbutton
    code = event.get_code()
    indev = lv.indev_active()
    if not indev:
        return
    point = lv.point_t()
    indev.get_point(point)
    x, y = point.x, point.y

    if code == lv.EVENT.PRESSED:
        smooth_show(downbutton)
        down_start_x = x
    elif code == lv.EVENT.PRESSING:
        magnetic_y = round(y / 10)
        downbutton.set_pos(down_start_x, magnetic_y)
    elif code == lv.EVENT.RELEASED:
        smooth_hide(downbutton)
        if y > min(80, get_display_height() / 3):
            open_drawer()

def handle_back_swipe():
    global backbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(round(60), lv.layer_top().get_height() - 80)
    rect.set_pos(0, 80)
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    style.set_border_width(0)
    rect.add_style(style, 0)

    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(_back_swipe_cb, lv.EVENT.RELEASED, None)

    backbutton = lv.button(lv.layer_top())
    backbutton.set_pos(0, 200)
    backbutton.add_flag(lv.obj.FLAG.HIDDEN)
    backbutton.add_state(lv.STATE.DISABLED)
    lbl = lv.label(backbutton)
    lbl.set_text(lv.SYMBOL.LEFT)
    lbl.set_style_text_font(lv.font_montserrat_18, 0)
    lbl.center()

def handle_top_swipe():
    global downbutton
    rect = lv.obj(lv.layer_top())
    rect.set_size(lv.pct(100), 60)
    rect.set_pos(0, 0)
    rect.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

    style = lv.style_t()
    style.init()
    style.set_bg_opa(lv.OPA.TRANSP)
    rect.add_style(style, 0)

    rect.add_event_cb(_top_swipe_cb, lv.EVENT.PRESSED, None)
    rect.add_event_cb(_top_swipe_cb, lv.EVENT.PRESSING, None)
    rect.add_event_cb(_top_swipe_cb, lv.EVENT.RELEASED, None)

    downbutton = lv.button(lv.layer_top())
    downbutton.set_pos(100, 0)
    downbutton.add_flag(lv.obj.FLAG.HIDDEN)
    downbutton.add_state(lv.STATE.DISABLED)
    lbl = lv.label(downbutton)
    lbl.set_text(lv.SYMBOL.DOWN)
    lbl.set_style_text_font(lv.font_montserrat_18, 0)
    lbl.center()
