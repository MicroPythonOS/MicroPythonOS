"""Calibrate IMU Activity.

Guides user through IMU calibration process:
1. Show calibration instructions
2. Check stationarity when user clicks "Calibrate Now"
3. Perform calibration
4. Show results
"""

import lvgl as lv
import time
import sys
from mpos.app.activity import Activity
import mpos.ui
import mpos.sensor_manager as SensorManager
from mpos.ui.testing import wait_for_render


class CalibrationState:
    """Enum for calibration states."""
    READY = 0
    CALIBRATING = 1
    COMPLETE = 2
    ERROR = 3


class CalibrateIMUActivity(Activity):
    """Guide user through IMU calibration process."""

    # State
    current_state = CalibrationState.READY
    calibration_thread = None

    # Widgets
    title_label = None
    status_label = None
    progress_bar = None
    detail_label = None
    action_button = None
    action_button_label = None
    cancel_button = None

    def __init__(self):
        super().__init__()
        self.is_desktop = sys.platform != "esp32"

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(mpos.ui.pct_of_display_width(3), 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER)
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        # Title
        self.title_label = lv.label(screen)
        self.title_label.set_text("IMU Calibration")
        self.title_label.set_style_text_font(lv.font_montserrat_16, 0)

        # Status label
        self.status_label = lv.label(screen)
        self.status_label.set_text("Initializing...")
        self.status_label.set_style_text_font(lv.font_montserrat_12, 0)
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(90))

        # Progress bar (hidden initially)
        self.progress_bar = lv.bar(screen)
        self.progress_bar.set_size(lv.pct(90), 20)
        self.progress_bar.set_value(0, False)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)

        # Detail label (for additional info)
        self.detail_label = lv.label(screen)
        self.detail_label.set_text("")
        self.detail_label.set_style_text_font(lv.font_montserrat_10, 0)
        self.detail_label.set_style_text_color(lv.color_hex(0x888888), 0)
        self.detail_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.detail_label.set_width(lv.pct(90))

        # Button container
        btn_cont = lv.obj(screen)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_style_border_width(0, 0)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_style_pad_all(1,0)
        btn_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, 0)

        # Action button
        self.action_button = lv.button(btn_cont)
        self.action_button.set_size(lv.pct(45), lv.SIZE_CONTENT)
        self.action_button_label = lv.label(self.action_button)
        self.action_button_label.set_text("Start")
        self.action_button_label.center()
        self.action_button.add_event_cb(self.action_button_clicked, lv.EVENT.CLICKED, None)

        # Cancel button
        self.cancel_button = lv.button(btn_cont)
        self.cancel_button.set_size(lv.pct(45), lv.SIZE_CONTENT)
        cancel_label = lv.label(self.cancel_button)
        cancel_label.set_text("Cancel")
        cancel_label.center()
        self.cancel_button.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)

        # Check if IMU is available
        if not self.is_desktop and not SensorManager.is_available():
            self.set_state(CalibrationState.ERROR)
            self.status_label.set_text("IMU not available on this device")
            self.action_button.add_state(lv.STATE.DISABLED)
            return

        # Show calibration instructions
        self.set_state(CalibrationState.READY)

    def onPause(self, screen):
        # Stop any running calibration
        if self.current_state == CalibrationState.CALIBRATING:
            # Calibration will detect activity is no longer in foreground
            pass
        super().onPause(screen)

    def set_state(self, new_state):
        """Update state and UI accordingly."""
        self.current_state = new_state
        self.update_ui_for_state()

    def update_ui_for_state(self):
        """Update UI based on current state."""
        if self.current_state == CalibrationState.READY:
            self.status_label.set_text("Place device on flat, stable surface\n\nKeep device completely still during calibration")
            self.detail_label.set_text("Calibration will take ~2 seconds\nUI will freeze during calibration")
            self.action_button_label.set_text("Calibrate Now")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
            self.cancel_button.remove_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.CALIBRATING:
            self.status_label.set_text("Calibrating IMU...")
            self.detail_label.set_text("Do not move device!")
            self.action_button.add_state(lv.STATE.DISABLED)
            self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
            self.progress_bar.set_value(50, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.COMPLETE:
            # Status text will be set by calibration results
            self.action_button_label.set_text("Done")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(100, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.ERROR:
            # Status text will be set by error handler
            self.action_button_label.set_text("Retry")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

    def action_button_clicked(self, event):
        """Handle action button clicks based on current state."""
        if self.current_state == CalibrationState.READY:
            self.start_calibration_process()
        elif self.current_state == CalibrationState.COMPLETE:
            self.finish()
        elif self.current_state == CalibrationState.ERROR:
            self.set_state(CalibrationState.READY)


    def start_calibration_process(self):
        """Start the calibration process.

        Note: Runs in main thread - UI will freeze during calibration (~2 seconds).
        This avoids threading issues with I2C/sensor access.
        """
        try:
            # Step 1: Check stationarity
            self.set_state(CalibrationState.CALIBRATING)
            wait_for_render()  # Let UI update

            if self.is_desktop:
                stationarity = {'is_stationary': True, 'message': 'Mock: Stationary'}
            else:
                stationarity = SensorManager.check_stationarity(samples=30)

            if stationarity is None or not stationarity['is_stationary']:
                msg = stationarity['message'] if stationarity else "Stationarity check failed"
                self.handle_calibration_error(
                    f"Device not stationary!\n\n{msg}\n\nPlace on flat surface and try again.")
                return

            # Step 2: Perform calibration
            if self.is_desktop:
                time.sleep(2)
                accel_offsets = (0.1, -0.05, 0.15)
                gyro_offsets = (0.2, -0.1, 0.05)
            else:
                # Real calibration - UI will freeze here
                accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
                gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)

                if accel:
                    accel_offsets = SensorManager.calibrate_sensor(accel, samples=100)
                else:
                    accel_offsets = None

                if gyro:
                    gyro_offsets = SensorManager.calibrate_sensor(gyro, samples=100)
                else:
                    gyro_offsets = None

            # Step 3: Show results
            result_msg = "Calibration successful!"
            if accel_offsets:
                result_msg += f"\n\nAccel offsets:\nX:{accel_offsets[0]:.3f} Y:{accel_offsets[1]:.3f} Z:{accel_offsets[2]:.3f}"
            if gyro_offsets:
                result_msg += f"\n\nGyro offsets:\nX:{gyro_offsets[0]:.3f} Y:{gyro_offsets[1]:.3f} Z:{gyro_offsets[2]:.3f}"

            self.show_calibration_complete(result_msg)

        except Exception as e:
            import sys
            sys.print_exception(e)
            self.handle_calibration_error(str(e))

    def show_calibration_complete(self, result_msg):
        """Show calibration completion message."""
        self.status_label.set_text(result_msg)
        self.detail_label.set_text("Calibration saved to storage.")
        self.set_state(CalibrationState.COMPLETE)

    def handle_calibration_error(self, error_msg):
        """Handle error during calibration."""
        self.set_state(CalibrationState.ERROR)
        self.status_label.set_text(f"Calibration failed:\n\n{error_msg}")
        self.detail_label.set_text("")

