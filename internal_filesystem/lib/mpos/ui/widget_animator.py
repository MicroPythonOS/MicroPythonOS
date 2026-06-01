import lvgl as lv


def _safe_widget_access(callback):
    """
    Wrapper to safely access a widget, catching LvReferenceError.

    If the widget has been deleted, the callback is silently skipped.
    This prevents crashes when animations try to access deleted widgets.
    """
    try:
        callback()
    except Exception as e:
        if "LvReferenceError" in str(type(e).__name__) or "Referenced object was deleted" in str(e):
            pass
        else:
            raise


class SlidePanel:
    """
    Manages a widget that slides vertically between shown/hidden positions.

    Handles rapid open/close without animation glitches by:
    - Tracking logical state (is_open) separately from animation state
    - Always animating to fixed endpoint positions (not reading mid-flight Y)
    - Cancelling in-flight animations before starting new ones

    Usage:
        panel = SlidePanel(drawer, shown_y=24, hidden_y=-200, duration=300)
        panel.show()   # slides into view
        panel.hide()   # slides out of view
        panel.toggle() # toggles state
    """

    def __init__(self, widget, shown_y, hidden_y, duration=300, use_hidden_flag=True):
        """
        Args:
            widget: The LVGL widget to animate
            shown_y: Y position when fully visible
            hidden_y: Y position when fully hidden (off-screen)
            duration: Animation duration in milliseconds
            use_hidden_flag: If True, add/remove HIDDEN flag at animation endpoints
        """
        self.widget = widget
        self.shown_y = shown_y
        self.hidden_y = hidden_y
        self.duration = duration
        self.use_hidden_flag = use_hidden_flag
        self.is_open = False
        self.on_shown = None   # optional callback when show animation completes
        self.on_hidden = None  # optional callback when hide animation completes

    def show(self, animate=True):
        """Slide the widget to its shown position."""
        if self.is_open:
            return
        self.is_open = True
        lv.anim_delete(self.widget, None)
        if self.use_hidden_flag:
            self.widget.remove_flag(lv.obj.FLAG.HIDDEN)
        if animate:
            self._animate(self.hidden_y, self.shown_y, self._on_show_done)
        else:
            self.widget.set_y(self.shown_y)
            if self.on_shown:
                self.on_shown()

    def hide(self, animate=True):
        """Slide the widget to its hidden position."""
        if not self.is_open:
            return
        self.is_open = False
        lv.anim_delete(self.widget, None)
        if animate:
            self._animate(self.shown_y, self.hidden_y, self._on_hide_done)
        else:
            self.widget.set_y(self.hidden_y)
            if self.use_hidden_flag:
                self.widget.add_flag(lv.obj.FLAG.HIDDEN)
            if self.on_hidden:
                self.on_hidden()

    def toggle(self, animate=True):
        """Toggle between shown and hidden states."""
        if self.is_open:
            self.hide(animate)
        else:
            self.show(animate)

    def _animate(self, from_y, to_y, on_complete):
        anim = lv.anim_t()
        anim.init()
        anim.set_var(self.widget)
        anim.set_duration(self.duration)
        anim.set_values(from_y, to_y)
        anim.set_custom_exec_cb(lambda _a, v: _safe_widget_access(lambda: self.widget.set_y(v)))
        anim.set_path_cb(lv.anim_t.path_ease_in_out)
        anim.set_completed_cb(lambda *args: _safe_widget_access(on_complete))
        anim.start()

    def _on_show_done(self):
        self.widget.set_y(self.shown_y)
        if self.on_shown:
            self.on_shown()

    def _on_hide_done(self):
        self.widget.set_y(self.hidden_y)
        if self.use_hidden_flag:
            self.widget.add_flag(lv.obj.FLAG.HIDDEN)
        if self.on_hidden:
            self.on_hidden()


class WidgetAnimator:
    """
    Utility for creating smooth, non-blocking animations on LVGL widgets.
    
    Provides fade, slide, and value interpolation animations with automatic
    cleanup and safe widget access handling.
    """

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
        lv.anim_delete(widget, None)
        anim = lv.anim_t()
        anim.init()
        anim.set_var(widget)
        anim.set_delay(delay)
        anim.set_duration(duration)
        anim.set_start_cb(lambda *args: _safe_widget_access(lambda: widget.remove_flag(lv.obj.FLAG.HIDDEN)))

        if anim_type == "fade":
            anim.set_values(0, 255)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_style_opa(value, lv.PART.MAIN)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: widget.set_style_opa(255, lv.PART.MAIN)))
        elif anim_type == "slide_down":
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y - height, original_y)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: widget.set_y(original_y)))
        else:  # "slide_up"
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y + height, original_y)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: widget.set_y(original_y)))

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
        lv.anim_delete(widget, None)
        anim = lv.anim_t()
        anim.init()
        anim.set_var(widget)
        anim.set_duration(duration)
        anim.set_delay(delay)

        if anim_type == "fade":
            anim.set_values(255, 0)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_style_opa(value, lv.PART.MAIN)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, hide=hide)))
        elif anim_type == "slide_down":
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y, original_y + height)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, original_y, hide)))
        else:  # "slide_up"
            original_y = widget.get_y()
            height = widget.get_height()
            anim.set_values(original_y, original_y - height)
            anim.set_custom_exec_cb(lambda anim, value: _safe_widget_access(lambda: widget.set_y(value)))
            anim.set_path_cb(lv.anim_t.path_ease_in_out)
            anim.set_completed_cb(lambda *args: _safe_widget_access(lambda: WidgetAnimator._hide_complete_cb(widget, original_y, hide)))

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
