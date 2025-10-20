import math
import lvgl as lv
import mpos.util

import math
import mpos.util

def get_object_center(obj):
    """Calculate the center (x, y) of an object based on its absolute screen coordinates."""
    obj_area = lv.area_t()
    obj.get_coords(obj_area)
    width = obj_area.x2 - obj_area.x1
    height = obj_area.y2 - obj_area.y1
    x = obj_area.x1
    y = obj_area.y1
    center_x = x + width / 2
    center_y = y + height / 2
    return center_x, center_y

def compute_angle_to_object(from_obj, to_obj):
    """
    Compute the clockwise angle (degrees) from from_obj's center to to_obj's center.
    Convention: 0° = UP, 90° = RIGHT, 180° = DOWN, 270° = LEFT (clockwise).
    """
    # Get centers
    from_x, from_y = get_object_center(from_obj)
    to_x, to_y = get_object_center(to_obj)
    
    # Compute vector
    dx = to_x - from_x
    dy = to_y - from_y
    
    # Calculate angle (0° = UP, 90° = RIGHT, 180° = DOWN, 270° = LEFT)
    angle_rad = math.atan2(dx, -dy)
    angle_deg = math.degrees(angle_rad)
    return (angle_deg + 360) % 360  # Normalize to [0, 360)

def is_object_in_focus_group(focus_group, obj):
    """Check if an object is in the focus group and not hidden."""
    if obj is None or obj.has_flag(lv.obj.FLAG.HIDDEN):
        return False
    for objnr in range(focus_group.get_obj_count()):
        if focus_group.get_obj_by_index(objnr) is obj:
            return True
    return False

def get_closest_edge_point_and_distance(from_x, from_y, obj, direction_degrees, debug=False):
    """
    Calculate the distance to the closest edge point on obj, and check if its angle is within the direction cone.
    Returns (distance, closest_x, closest_y, angle_deg) or None if not in direction or inside.
    """
    obj_area = lv.area_t()
    obj.get_coords(obj_area)
    x = obj_area.x1
    y = obj_area.y1
    right = obj_area.x2
    bottom = obj_area.y2
    width = right - x
    height = bottom - y
    
    # Clamp to the rect bounds to find closest point
    closest_x = max(x, min(from_x, right))
    closest_y = max(y, min(from_y, bottom))
    
    # Compute vector to closest point
    dx = closest_x - from_x
    dy = closest_y - from_y
    
    # If closest point is the from point, the from is inside the obj, skip
    if dx == 0 and dy == 0:
        if debug:
            print(f"  Skipping {obj} because current center is inside the object.")
        return None
    
    # Compute distance
    distance = math.sqrt(dx**2 + dy**2)
    
    # Compute angle to the closest point (using same convention)
    angle_rad = math.atan2(dx, -dy)
    angle_deg = math.degrees(angle_rad)
    angle_deg = (angle_deg + 360) % 360
    
    # Check if in direction cone (±45°)
    angle_diff = min((angle_deg - direction_degrees) % 360, (direction_degrees - angle_deg) % 360)
    if angle_diff > 45:
        if debug:
            print(f"  {obj} at ({x}, {y}) size ({width}x{height}): closest point ({closest_x:.1f}, {closest_y:.1f}), angle {angle_deg:.1f}°, diff {angle_diff:.1f}° > 45°, skipped")
        return None
    
    if debug:
        print(f"  {obj} at ({x}, {y}) size ({width}x{height}): closest point ({closest_x:.1f}, {closest_y:.1f}), angle {angle_deg:.1f}°, distance {distance:.1f}, diff {angle_diff:.1f}°")
    
    return distance, closest_x, closest_y, angle_deg

def find_closest_obj_in_direction(focus_group, current_focused, direction_degrees, debug=False):
    """
    Find the closest object in the specified direction from the current focused object.
    Uses closest edge point for distance to handle object sizes intuitively.
    Only considers objects that are in the focus_group and not hidden (including children).
    Direction is in degrees: 0° = UP, 90° = RIGHT, 180° = DOWN, 270° = LEFT (clockwise).
    Returns the closest object or None.
    """
    if not current_focused:
        print("No current focused object.")
        return None
    
    if debug:
        print("Current focused object:")
        mpos.util.print_lvgl_widget(current_focused)
        print(f"Default focus group has {focus_group.get_obj_count()} items")
    
    closest_obj = None
    min_distance = float('inf')
    current_x, current_y = get_object_center(current_focused)
    
    def process_object(obj, depth=0):
        """Recursively process an object and its children to find the closest in direction."""
        nonlocal closest_obj, min_distance
        
        if obj is None or obj is current_focused:
            return
        
        # Check if the object is in the focus group and not hidden, then evaluate it
        if is_object_in_focus_group(focus_group, obj):
            result = get_closest_edge_point_and_distance(current_x, current_y, obj, direction_degrees, debug)
            if result:
                distance, closest_x, closest_y, angle_deg = result
                if distance < min_distance:
                    min_distance = distance
                    closest_obj = obj
                    if debug:
                        print(f"  Updated closest (distance {distance:.1f}, angle {angle_deg:.1f}°):")
                        mpos.util.print_lvgl_widget(obj, depth=depth)
        
        # Process children regardless of parent's focus group membership
        for childnr in range(obj.get_child_count()):
            child = obj.get_child(childnr)
            process_object(child, depth + 1)
    
    # Iterate through objects in the focus group
    for objnr in range(focus_group.get_obj_count()):
        obj = focus_group.get_obj_by_index(objnr)
        process_object(obj)
    
    # Result
    if closest_obj:
        print(f"Closest object in direction {direction_degrees}°:")
        mpos.util.print_lvgl_widget(closest_obj)
    else:
        print(f"No object found in direction {direction_degrees}°")
    
    return closest_obj













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
    o = find_closest_obj_in_direction(focus_group, current_focused, angle, True)
    if o:
        print("move_focus_direction: moving focus to:")
        mpos.util.print_lvgl_widget(o)
        emulate_focus_obj(focus_group, o)
