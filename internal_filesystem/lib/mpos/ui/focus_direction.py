import math
import lvgl as lv
import mpos.util


# This function is missing so emulate it using focus_next():
def emulate_focus_obj(focusgroup, target):
    for objnr in range(focusgroup.get_obj_count()):
        currently_focused = focusgroup.get_focused()
        #print ("emulate_focus_obj: currently focused:") ; mpos.util.print_lvgl_widget(currently_focused)
        if currently_focused is target:
            print("emulate_focus_obj: found target, stopping")
            return
        else:
            focusgroup.focus_next()
    print("WARNING: emulate_focus_obj failed to find target")

def get_object_center(obj):
    """Calculate the center (x, y) of an object."""
    width = obj.get_width()
    height = obj.get_height()
    x = obj.get_x()
    y = obj.get_y()
    center_x = x + width / 2
    center_y = y + height / 2
    return center_x, center_y

def compute_angle_to_object(from_obj, to_obj):
    """Compute the clockwise angle (degrees) from from_obj's center to to_obj's center (0° = UP)."""
    # Get centers
    from_x, from_y = get_object_center(from_obj)
    to_x, to_y = get_object_center(to_obj)
    
    # Compute vector
    dx = to_x - from_x
    dy = to_y - from_y
    
    # Calculate angle (0° = UP, 90° = RIGHT, clockwise)
    angle_rad = math.atan2(-dx, dy)  # -dx, dy for 0° = UP
    angle_deg = math.degrees(angle_rad)
    return (angle_deg + 360) % 360  # Normalize to [0, 360)

def find_closest_obj_in_direction(focus_group, current_focused, direction_degrees, angle_tolerance=45):
    if not current_focused:
        print("No current focused object.")
        return None

    closest_obj = None
    min_distance = float('inf')
    
    # Iterate through objects in the focus group
    for objnr in range(focus_group.get_obj_count()):
        obj = focus_group.get_obj_by_index(objnr)
        if obj is current_focused:
            #print(f"Skipping {obj} because it's the currently focused object.")
            continue
        
        # Compute angle to the object
        angle_deg = compute_angle_to_object(current_focused, obj)
        #print(f"angle_deg is {angle_deg} for") ; mpos.util.print_lvgl_widget(obj)

        # Check if object is in the desired direction (within ±angle_tolerance)
        angle_diff = min((angle_deg - direction_degrees) % 360, (direction_degrees - angle_deg) % 360)
        if angle_diff <= angle_tolerance:
            # Calculate Euclidean distance
            current_x, current_y = get_object_center(current_focused)
            obj_x, obj_y = get_object_center(obj)
            distance = math.sqrt((obj_x - current_x)**2 + (obj_y - current_y)**2)
            
            # Update closest object if this one is closer
            if distance < min_distance:
                min_distance = distance
                closest_obj = obj

    # Result
    if closest_obj:
        print(f"Closest object in direction {direction_degrees}°: {closest_obj}")
    else:
        print(f"No object found in direction {direction_degrees}°")
    
    return closest_obj

def move_focus_direction(angle):
    focus_group = lv.group_get_default()
    if not focus_group:
        print("move_focus_direction: no default focus_group found, returning...")
        return
    current_focused = focus_group.get_focused()
    if not current_focused:
        print("move_focus_direction: nothing is focused, choosing the next thing")
        focus_group.focus_next()
        current_focused = focus_group.get_focused()
    if isinstance(current_focused, lv.keyboard):
        print("focus is on a keyboard, which has its own move_focus_direction: NOT moving")
        return
    o = find_closest_obj_in_direction(focus_group, current_focused, angle)
    if o:
        print("move_focus_direction: moving focus to:")
        mpos.util.print_lvgl_widget(o)
        emulate_focus_obj(focus_group, o)
