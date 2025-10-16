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
        if isinstance(obj,lv.label):
            label = f"has label {obj.get_text()}"
        padding = "  " * depth
        print(f"{padding}{obj} with size {obj.get_width()}x{obj.get_height()} {label}")
        for childnr in range(obj.get_child_count()):
            print_lvgl_widget(obj.get_child(childnr), depth+1)
