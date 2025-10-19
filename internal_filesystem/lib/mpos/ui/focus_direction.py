import math
import lvgl as lv
import mpos.util

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

def find_closest_obj_in_direction(direction_degrees, angle_tolerance=45):
    print(f"default focus group has {lv.group_get_default().get_obj_count()} items")
    focusgroup = lv.group_get_default()
    for objnr in range(focusgroup.get_obj_count()):
        obj = focusgroup.get_obj_by_index(objnr)
        print ("checking obj for equality...")
        mpos.util.print_lvgl_widget(obj)
    print(f"current focus object: {lv.group_get_default().get_focused()}")
    
    """Find the closest object in the specified direction from the current focused object."""
    # Get focus group and current focused object
    focus_group = lv.group_get_default()
    current_focused = focus_group.get_focused()
    
    if not current_focused:
        print("No current focused object.")
        return None
    
    print(f"Current focused object: {current_focused}")
    print(f"Default focus group has {focus_group.get_obj_count()} items")
    
    closest_obj = None
    min_distance = float('inf')
    
    # Iterate through objects in the focus group
    for objnr in range(focus_group.get_obj_count()):
        obj = focus_group.get_obj_by_index(objnr)
        if obj is current_focused:
            print(f"Skipping {obj} because it's the currently focused object.")
            continue
        
        # Compute angle to the object
        angle_deg = compute_angle_to_object(current_focused, obj)
        print(f"angle_deg is {angle_deg}")
        
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
