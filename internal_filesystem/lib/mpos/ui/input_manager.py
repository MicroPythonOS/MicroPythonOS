# lib/mpos/ui/input_manager.py
"""
InputManager - Framework for managing input device interactions.

Provides a clean API for accessing input device data like pointer/touch coordinates
and focus management.
All methods are class methods, so no instance creation is needed.
"""


class InputManager:
    """
    Input manager singleton for handling input device interactions.
    
    Provides static/class methods for accessing input device properties and data.
    """
    
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
        This function is needed because LVGL doesn't have a direct set_focus method.
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
