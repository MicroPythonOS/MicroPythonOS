import lvgl as lv

class WidgetAnimator:

#    def __init__(self):
#        self.animations = {}  # Store animations for each widget

#    def stop_animation(self, widget):
#        """Stop any running animation for the widget."""
#        if widget in self.animations:
#            self.animations[widget].delete()
#            del self.animations[widget]


    # show_widget and hide_widget could have a (lambda) callback that sets the final state (eg: drawer_open) at the end
    @staticmethod
    def show_widget(widget, anim_type="fade", duration=500, delay=0):
        """Show a widget with an animation (fade or slide)."""
        # Clear HIDDEN flag to make widget visible for animation
        widget.remove_flag(lv.obj.FLAG.HIDDEN)

        if anim_type == "fade":
            # Create fade-in animation (opacity from 0 to 255)
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(0, 255)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_style_opa(value, 0))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Ensure opacity is reset after animation
            anim.set_completed_cb(lambda *args: widget.set_style_opa(255, 0))
        elif anim_type == "slide_down":
            print("doing slide_down")
            # Create slide-down animation (y from -height to original y)
            original_y = widget.get_y()
            height = widget.get_height()
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(original_y - height, original_y)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_y(value))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Reset y position after animation
            anim.set_completed_cb(lambda *args: widget.set_y(original_y))
        elif anim_type == "slide_up":
            # Create slide-up animation (y from +height to original y)
            # Seems to cause scroll bars to be added somehow if done to a keyboard at the bottom of the screen...
            original_y = widget.get_y()
            height = widget.get_height()
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(original_y + height, original_y)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_y(value))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Reset y position after animation
            anim.set_completed_cb(lambda *args: widget.set_y(original_y))

        # Store and start animation
        #self.animations[widget] = anim
        anim.start()

    @staticmethod
    def hide_widget(widget, anim_type="fade", duration=500, delay=0, hide=True):
        """Hide a widget with an animation (fade or slide)."""
        if anim_type == "fade":
            # Create fade-out animation (opacity from 255 to 0)
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(255, 0)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_style_opa(value, 0))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator.hide_complete_cb(widget, hide=hide))
        elif anim_type == "slide_down":
            # Create slide-down animation (y from original y to +height)
            # Seems to cause scroll bars to be added somehow if done to a keyboard at the bottom of the screen...
            original_y = widget.get_y()
            height = widget.get_height()
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(original_y, original_y + height)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_y(value))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator.hide_complete_cb(widget, original_y, hide))
        elif anim_type == "slide_up":
            print("hide with slide_up")
            # Create slide-up animation (y from original y to -height)
            original_y = widget.get_y()
            height = widget.get_height()
            anim = lv.anim_t()
            anim.init()
            anim.set_var(widget)
            anim.set_values(original_y, original_y - height)
            anim.set_duration(duration)
            anim.set_delay(delay)
            anim.set_custom_exec_cb(lambda anim, value: widget.set_y(value))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator.hide_complete_cb(widget, original_y, hide))

        # Store and start animation
        #self.animations[widget] = anim
        anim.start()

    @staticmethod
    def hide_complete_cb(widget, original_y=None, hide=True):
        #print("hide_complete_cb")
        if hide:
            widget.add_flag(lv.obj.FLAG.HIDDEN)
        if original_y:
            widget.set_y(original_y) # in case it shifted slightly due to rounding etc


def smooth_show(widget):
    WidgetAnimator.show_widget(widget, anim_type="fade", duration=500, delay=0)

def smooth_hide(widget, hide=True):
    WidgetAnimator.hide_widget(widget, anim_type="fade", duration=500, delay=0, hide=hide)
