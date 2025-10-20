import lvgl as lv

def urldecode(s):
    result = ""
    i = 0
    while i < len(s):
        if s[i] == '%':
            result += chr(int(s[i+1:i+3], 16))
            i += 3
        else:
            result += s[i]
            i += 1
    return result

def print_lvgl_widget(obj, depth=0):
    if obj:
        label = ""
        hidden = ""
        editable = "editable"
        obj_area = lv.area_t()
        obj.get_coords(obj_area)
        if obj.has_flag(lv.obj.FLAG.HIDDEN):
            hidden = "hidden "
        if not obj.is_editable():
            editable = "not editable "
        if isinstance(obj,lv.label):
            label = f" with label '{obj.get_text()}'"
        padding = "  " * depth
        print(f"{padding}{obj} pos:{obj_area.x1}x{obj_area.y1} size:{obj_area.get_width()}x{obj_area.get_height()} {hidden}{editable} {label}")
        for childnr in range(obj.get_child_count()):
            print_lvgl_widget(obj.get_child(childnr), depth+1)
    else:
        print("print_lvgl_widget called on 'None'")
