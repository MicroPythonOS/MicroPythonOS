# lib/mpos/ui/input_manager.py
"""
InputManager - Framework for managing input device interactions.

Provides a clean API for accessing input device data like pointer/touch coordinates,
focus management, and input device registration.
All methods are class methods, so no instance creation is needed.
"""


class InputManager:
    """
    Input manager singleton for handling input device interactions.
    
    Provides static/class methods for accessing input device properties and data.
    """
    
    _registered_indevs = []  # List of registered input devices
    
    @classmethod
    def register_indev(cls, indev):
        """
        Register an input device for later querying.
        Called by board initialization code.
        
        Parameters:
        - indev: LVGL input device object
        """
        if indev and indev not in cls._registered_indevs:
            cls._registered_indevs.append(indev)
    
    @classmethod
    def unregister_indev(cls, indev):
        """
        Unregister an input device.
        
        Parameters:
        - indev: LVGL input device object to remove
        """
        if indev in cls._registered_indevs:
            indev.enable(False)
            cls._registered_indevs.remove(indev)
    
    @classmethod
    def list_indevs(cls):
        """
        Get list of all registered input devices.
        
        Returns: list of LVGL input device objects
        """
        return cls._registered_indevs
    
    @classmethod
    def has_indev_type(cls, indev_type):
        """
        Check if any registered input device has the specified type.
        
        Parameters:
        - indev_type: LVGL input device type (e.g., lv.INDEV_TYPE.KEYPAD)
        
        Returns: bool - True if device type is available
        """
        for indev in cls._registered_indevs:
            if indev.get_type() == indev_type:
                return True
        return False
    
    @classmethod
    def pointer_xy(cls):
        """Get current pointer/touch coordinates."""
        import lvgl as lv
        indev = lv.indev_active()
        if indev:
            p = lv.point_t()
            indev.get_point(p)
            return p.x, p.y
        return -1, -1
    
    @classmethod
    def emulate_focus_obj(cls, focusgroup, target):
        """
        Emulate setting focus to a specific object in the focus group.
        This function is needed because the current version of LVGL doesn't have a direct set_focus method.
        It should exist, according to the API, so maybe it will be available in the next release and this function might no longer be needed someday.
        """
        if not focusgroup:
            print("emulate_focus_obj needs a focusgroup, returning...")
            return
        if not target:
            print("emulate_focus_obj needs a target, returning...")
            return
        for objnr in range(focusgroup.get_obj_count()):
            currently_focused = focusgroup.get_focused()
            if currently_focused is target:
                return
            else:
                focusgroup.focus_next()
        print("WARNING: emulate_focus_obj failed to find target")
