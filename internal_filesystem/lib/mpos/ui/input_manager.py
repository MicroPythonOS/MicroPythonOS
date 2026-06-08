# lib/mpos/ui/input_manager.py
"""
InputManager - Framework for managing input device interactions.

Provides a clean API for accessing input device data like pointer/touch coordinates,
focus management, and input device registration.
All methods are class methods, so no instance creation is needed.
"""

import lvgl as lv


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
    def has_pointer(cls):
        """Check if any registered input device is a pointer/touch device."""
        return cls.has_indev_type(lv.INDEV_TYPE.POINTER)

    @classmethod
    def set_touch_feedback_cb(cls, cb):
        """Attach cb(event) to every registered pointer indev on LV_EVENT_CLICKED.

        LVGL sends CLICKED on touch release only when the press did not scroll a
        scrollable parent, so cb fires on taps but not on swipes that scroll.
        Whether to act is the callback's own decision. It can read a preference
        on each call. Call once at boot. A second call registers cb again.
        """
        for indev in cls._registered_indevs:
            try:
                if indev.get_type() == lv.INDEV_TYPE.POINTER and hasattr(indev, "add_event_cb"):
                    indev.add_event_cb(cb, lv.EVENT.CLICKED, None)
            except Exception as e:
                print("InputManager.set_touch_feedback_cb:", e)

    @classmethod
    def pointer_xy(cls):
        """Get current pointer/touch coordinates."""
        indev = lv.indev_active()
        if indev:
            p = lv.point_t()
            indev.get_point(p)
            return p.x, p.y
        return -1, -1
    
    @classmethod
    def emulate_focus_obj(cls, focusgroup, target):
        """
        Deprecated compatibility shim.

        Use lv.group_focus_obj(target) directly.
        """
        if not target:
            print("emulate_focus_obj needs a target, returning...")
            return

        print(
            "WARNING: InputManager.emulate_focus_obj() is deprecated and unnecessary. "
            "Use lv.group_focus_obj(target) directly."
        )

        lv.group_focus_obj(target)

