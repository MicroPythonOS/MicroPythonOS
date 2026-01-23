import lvgl as lv


class WidgetAnimator:
    """
    Utility for creating smooth, non-blocking animations on LVGL widgets.
    
    Provides fade, slide, and value interpolation animations with automatic
    cleanup and safe widget access handling.
    """

    @staticmethod
    def _safe_widget_access(callback):
        """
        Wrapper to safely access a widget, catching LvReferenceError.

        If the widget has been deleted, the callback is silently skipped.
        This prevents crashes when animations try to access deleted widgets.

        Args:
            callback: Function to call (should access a widget)

        Returns:
            None (always, even if callback returns a value)
        """
        try:
            callback()
        except Exception as e:
            # Check if it's an LvReferenceError (widget was deleted)
            if "LvReferenceError" in str(type(e).__name__) or "Referenced object was deleted" in str(e):
                # Widget was deleted - silently ignore
                pass
            else:
                # Some other error - re-raise it
                raise

    @staticmethod
    def show_widget(widget, anim_type="fade", duration=500, delay=0):
        """
        Show a widget with an animation.

        Args:
            widget (lv.obj): The widget to show
            anim_type (str): Animation type - "fade", "slide_down", or "slide_up" (default: "fade")
            duration (int): Animation duration in milliseconds (default: 500)
            delay (int): Animation delay in milliseconds (default: 0)

        Returns:
            The animation object
        """
        lv.anim_delete(widget, None)  # stop all ongoing animations to prevent visual glitches
        anim = lv.anim_t()
        anim.init()
        anim.set_var(widget)
        anim.set_delay(delay)
        anim.set_duration(duration)
        # Clear HIDDEN flag to make widget visible for animation:
        anim.set_start_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: widget.remove_flag(lv.obj.FLAG.HIDDEN)))

        if anim_type == "fade":
            # Create fade-in animation (opacity from 0 to 255)
            anim.set_values(0, 255)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_style_opa(value, 0)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Ensure opacity is reset after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: widget.set_style_opa(255, 0)))
        elif anim_type == "slide_down":
            # Create slide-down animation (y from -height to original y)
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y - height, original_y)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Reset y position after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: widget.set_y(original_y)))
        else:  # "slide_up"
            # Create slide-up animation (y from +height to original y)
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y + height, original_y)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Reset y position after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: widget.set_y(original_y)))

        anim.start()
        return anim

    @staticmethod
    def hide_widget(widget, anim_type="fade", duration=500, delay=0, hide=True):
        """
        Hide a widget with an animation.

        Args:
            widget (lv.obj): The widget to hide
            anim_type (str): Animation type - "fade", "slide_down", or "slide_up" (default: "fade")
            duration (int): Animation duration in milliseconds (default: 500)
            delay (int): Animation delay in milliseconds (default: 0)
            hide (bool): If True, adds HIDDEN flag after animation. If False, only animates opacity/position (default: True)

        Returns:
            The animation object
        """
        lv.anim_delete(widget, None)  # stop all ongoing animations to prevent visual glitches
        anim = lv.anim_t()
        anim.init()
        anim.set_var(widget)
        anim.set_duration(duration)
        anim.set_delay(delay)

        if anim_type == "fade":
            # Create fade-out animation (opacity from 255 to 0)
            anim.set_values(255, 0)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_style_opa(value, 0)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, hide=hide)))
        elif anim_type == "slide_down":
            # Create slide-down animation (y from original y to +height)
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y, original_y + height)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, original_y, hide)))
        else:  # "slide_up"
            # Create slide-up animation (y from original y to -height)
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y, original_y - height)
            anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            # Set HIDDEN flag after animation
            anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, original_y, hide)))

        anim.start()
        return anim

    @staticmethod
    def change_widget(widget, anim_type="interpolate", duration=5000, delay=0, begin_value=0, end_value=100, display_change=None):
        """
        Animate a widget's text by interpolating between begin_value and end_value.

        Args:
            widget: The widget to animate (should have set_text method)
            anim_type: Type of animation (currently "interpolate" is supported)
            duration: Animation duration in milliseconds
            delay: Animation delay in milliseconds
            begin_value: Starting value for interpolation
            end_value: Ending value for interpolation
            display_change: callback to display the change in the UI

        Returns:
            The animation object
        """
        lv.anim_delete(widget, None)  # stop all ongoing animations to prevent visual glitches
        anim = lv.anim_t()
        anim.init()
        anim.set_var(widget)
        anim.set_delay(delay)
        anim.set_duration(duration)

        if anim_type == "interpolate":
            anim.set_values(begin_value, end_value)
            if display_change is not None:
                anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: display_change(value)))
                # Ensure final value is set after animation
                anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: display_change(end_value)))
            else:
                anim.set_custom_exec_cb(lambda anim, value: WidgetAnimator._safe_widget_access(lambda: widget.set_text(str(value))))
                # Ensure final value is set after animation
                anim.set_completed_cb(lambda *args: WidgetAnimator._safe_widget_access(lambda: widget.set_text(str(end_value))))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
        else:
            return

        anim.start()
        return anim

    @staticmethod
    def smooth_show(widget, duration=500, delay=0):
        """
        Fade in a widget (shorthand for show_widget with fade animation).

        Args:
            widget: The widget to show
            duration: Animation duration in milliseconds (default: 500)
            delay: Animation delay in milliseconds (default: 0)

        Returns:
            The animation object
        """
        return WidgetAnimator.show_widget(widget, anim_type="fade", duration=duration, delay=delay)

    @staticmethod
    def smooth_hide(widget, hide=True, duration=500, delay=0):
        """
        Fade out a widget (shorthand for hide_widget with fade animation).

        Args:
            widget: The widget to hide
            hide: If True, adds HIDDEN flag after animation (default: True)
            duration: Animation duration in milliseconds (default: 500)
            delay: Animation delay in milliseconds (default: 0)

        Returns:
            The animation object
        """
        return WidgetAnimator.hide_widget(widget, anim_type="fade", duration=duration, delay=delay, hide=hide)

    @staticmethod
    def _hide_complete_cb(widget, original_y=None, hide=True):
        """
        Internal callback for hide animation completion.

        Args:
            widget: The widget being hidden
            original_y: Original Y position (for slide animations)
            hide: Whether to add HIDDEN flag
        """
        if hide:
            widget.add_flag(lv.obj.FLAG.HIDDEN)
        if original_y:
            widget.set_y(original_y)  # in case it shifted slightly due to rounding etc
