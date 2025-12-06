"""Calibrate IMU Activity.

Guides user through IMU calibration process:
1. Check current calibration quality
2. Ask if user wants to recalibrate
3. Check stationarity
4. Perform calibration
5. Verify results
6. Save to new location
"""

import lvgl as lv
import time
import _thread
import sys
from mpos.app.activity import Activity
import mpos.ui
import mpos.sensor_manager as SensorManager
import mpos.apps
from mpos.ui.testing import wait_for_render


class CalibrationState:
    """Enum for calibration states."""
    IDLE = 0
    CHECKING_QUALITY = 1
    AWAITING_CONFIRMATION = 2
    CHECKING_STATIONARITY = 3
    CALIBRATING = 4
    VERIFYING = 5
    COMPLETE = 6
    ERROR = 7


class CalibrateIMUActivity(Activity):
    """Guide user through IMU calibration process."""

    # State
    current_state = CalibrationState.IDLE
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

        # Title
        self.title_label = lv.label(screen)
        self.title_label.set_text("IMU Calibration")
        self.title_label.set_style_text_font(lv.font_montserrat_20, 0)

        # Status label
        self.status_label = lv.label(screen)
        self.status_label.set_text("Initializing...")
        self.status_label.set_style_text_font(lv.font_montserrat_16, 0)
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
        self.detail_label.set_style_text_font(lv.font_montserrat_12, 0)
        self.detail_label.set_style_text_color(lv.color_hex(0x888888), 0)
        self.detail_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.detail_label.set_width(lv.pct(90))

        # Button container
        btn_cont = lv.obj(screen)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_style_border_width(0, 0)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
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

        # Start by checking current quality
        self.set_state(CalibrationState.IDLE)
        self.action_button_label.set_text("Check Quality")

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
        if self.current_state == CalibrationState.IDLE:
            self.status_label.set_text("Ready to check calibration quality")
            self.action_button_label.set_text("Check Quality")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
            self.cancel_button.remove_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.CHECKING_QUALITY:
            self.status_label.set_text("Checking current calibration...")
            self.action_button.add_state(lv.STATE.DISABLED)
            self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
            self.progress_bar.set_value(20, True)
            self.cancel_button.remove_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.AWAITING_CONFIRMATION:
            # Status will be set by quality check result
            self.action_button_label.set_text("Calibrate Now")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(30, True)
            self.cancel_button.remove_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.CHECKING_STATIONARITY:
            self.status_label.set_text("Checking if device is stationary...")
            self.detail_label.set_text("Keep device still on flat surface")
            self.action_button.add_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(40, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.CALIBRATING:
            self.status_label.set_text("Calibrating IMU...")
            self.detail_label.set_text("Do not move device!\nCollecting samples...")
            self.action_button.add_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(60, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.VERIFYING:
            self.status_label.set_text("Verifying calibration...")
            self.action_button.add_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(90, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.COMPLETE:
            self.status_label.set_text("Calibration complete!")
            self.action_button_label.set_text("Done")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.set_value(100, True)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

        elif self.current_state == CalibrationState.ERROR:
            self.action_button_label.set_text("Retry")
            self.action_button.remove_state(lv.STATE.DISABLED)
            self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
            self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)

    def action_button_clicked(self, event):
        """Handle action button clicks based on current state."""
        if self.current_state == CalibrationState.IDLE:
            self.start_quality_check()
        elif self.current_state == CalibrationState.AWAITING_CONFIRMATION:
            self.start_calibration_process()
        elif self.current_state == CalibrationState.COMPLETE:
            self.finish()
        elif self.current_state == CalibrationState.ERROR:
            self.set_state(CalibrationState.IDLE)

    def start_quality_check(self):
        """Check current calibration quality."""
        self.set_state(CalibrationState.CHECKING_QUALITY)

        # Run in background thread
        _thread.stack_size(mpos.apps.good_stack_size())
        _thread.start_new_thread(self.quality_check_thread, ())

    def quality_check_thread(self):
        """Background thread for quality check."""
        try:
            if self.is_desktop:
                quality = self.get_mock_quality()
            else:
                quality = SensorManager.check_calibration_quality(samples=50)

            if quality is None:
                self.update_ui_threadsafe_if_foreground(self.handle_quality_error, "Failed to read IMU")
                return

            # Update UI with results
            self.update_ui_threadsafe_if_foreground(self.show_quality_results, quality)

        except Exception as e:
            print(f"[CalibrateIMU] Quality check error: {e}")
            self.update_ui_threadsafe_if_foreground(self.handle_quality_error, str(e))

    def show_quality_results(self, quality):
        """Show quality check results and ask for confirmation."""
        rating = quality['quality_rating']
        score = quality['quality_score']
        issues = quality['issues']

        # Build status message
        if rating == "Good":
            msg = f"Current calibration: {rating} ({score*100:.0f}%)\n\nCalibration looks good!"
        else:
            msg = f"Current calibration: {rating} ({score*100:.0f}%)\n\nRecommend recalibrating."

        if issues:
            msg += "\n\nIssues found:\n" + "\n".join(f"- {issue}" for issue in issues[:3])  # Show first 3

        self.status_label.set_text(msg)
        self.set_state(CalibrationState.AWAITING_CONFIRMATION)

    def handle_quality_error(self, error_msg):
        """Handle error during quality check."""
        self.set_state(CalibrationState.ERROR)
        self.status_label.set_text(f"Error: {error_msg}")
        self.detail_label.set_text("Check IMU connection and try again")

    def start_calibration_process(self):
        """Start the calibration process.

        Note: Runs in main thread - UI will freeze during calibration (~1 second).
        This avoids threading issues with I2C/sensor access.
        """
        try:
            print("[CalibrateIMU] === Calibration started ===")

            # Step 1: Check stationarity
            print("[CalibrateIMU] Step 1: Checking stationarity...")
            self.set_state(CalibrationState.CHECKING_STATIONARITY)
            wait_for_render()  # Let UI update

            if self.is_desktop:
                stationarity = {'is_stationary': True, 'message': 'Mock: Stationary'}
            else:
                print("[CalibrateIMU] Calling SensorManager.check_stationarity(samples=30)...")
                stationarity = SensorManager.check_stationarity(samples=30)
                print(f"[CalibrateIMU] Stationarity result: {stationarity}")

            if stationarity is None or not stationarity['is_stationary']:
                msg = stationarity['message'] if stationarity else "Stationarity check failed"
                print(f"[CalibrateIMU] Device not stationary: {msg}")
                self.handle_calibration_error(
                    f"Device not stationary!\n\n{msg}\n\nPlace on flat surface and try again.")
                return

            print("[CalibrateIMU] Device is stationary, proceeding to calibration")

            # Step 2: Perform calibration
            print("[CalibrateIMU] Step 2: Performing calibration...")
            self.set_state(CalibrationState.CALIBRATING)
            self.status_label.set_text("Calibrating IMU...\n\nUI will freeze for ~2 seconds\nPlease wait...")
            wait_for_render()  # Let UI update before blocking

            if self.is_desktop:
                print("[CalibrateIMU] Mock calibration (desktop)")
                time.sleep(2)
                accel_offsets = (0.1, -0.05, 0.15)
                gyro_offsets = (0.2, -0.1, 0.05)
            else:
                # Real calibration - UI will freeze here
                print("[CalibrateIMU] Real calibration (hardware)")
                accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
                gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)
                print(f"[CalibrateIMU] Accel sensor: {accel}, Gyro sensor: {gyro}")

                if accel:
                    print("[CalibrateIMU] Calibrating accelerometer (100 samples)...")
                    accel_offsets = SensorManager.calibrate_sensor(accel, samples=100)
                    print(f"[CalibrateIMU] Accel offsets: {accel_offsets}")
                else:
                    accel_offsets = None

                if gyro:
                    print("[CalibrateIMU] Calibrating gyroscope (100 samples)...")
                    gyro_offsets = SensorManager.calibrate_sensor(gyro, samples=100)
                    print(f"[CalibrateIMU] Gyro offsets: {gyro_offsets}")
                else:
                    gyro_offsets = None

            # Step 3: Verify results
            print("[CalibrateIMU] Step 3: Verifying calibration...")
            self.set_state(CalibrationState.VERIFYING)
            wait_for_render()

            if self.is_desktop:
                verify_quality = self.get_mock_quality(good=True)
            else:
                print("[CalibrateIMU] Checking calibration quality (50 samples)...")
                verify_quality = SensorManager.check_calibration_quality(samples=50)
                print(f"[CalibrateIMU] Verification quality: {verify_quality}")

            if verify_quality is None:
                print("[CalibrateIMU] Verification failed")
                self.handle_calibration_error("Calibration completed but verification failed")
                return

            # Step 4: Show results
            print("[CalibrateIMU] Step 4: Showing results...")
            rating = verify_quality['quality_rating']
            score = verify_quality['quality_score']

            result_msg = f"Calibration successful!\n\nNew quality: {rating} ({score*100:.0f}%)"
            if accel_offsets:
                result_msg += f"\n\nAccel offsets:\nX:{accel_offsets[0]:.3f} Y:{accel_offsets[1]:.3f} Z:{accel_offsets[2]:.3f}"
            if gyro_offsets:
                result_msg += f"\n\nGyro offsets:\nX:{gyro_offsets[0]:.3f} Y:{gyro_offsets[1]:.3f} Z:{gyro_offsets[2]:.3f}"

            print(f"[CalibrateIMU] Calibration complete! Result: {result_msg[:80]}")
            self.show_calibration_complete(result_msg)
            print("[CalibrateIMU] === Calibration finished ===")

        except Exception as e:
            print(f"[CalibrateIMU] Calibration error: {e}")
            import sys
            sys.print_exception(e)
            self.handle_calibration_error(str(e))

    def old_calibration_thread_func_UNUSED(self):
        """Background thread for calibration process."""
        try:
            print("[CalibrateIMU] === Calibration thread started ===")

            # Step 1: Check stationarity
            print("[CalibrateIMU] Step 1: Checking stationarity...")
            if self.is_desktop:
                stationarity = {'is_stationary': True, 'message': 'Mock: Stationary'}
            else:
                print("[CalibrateIMU] Calling SensorManager.check_stationarity(samples=30)...")
                stationarity = SensorManager.check_stationarity(samples=30)
                print(f"[CalibrateIMU] Stationarity result: {stationarity}")

            if stationarity is None or not stationarity['is_stationary']:
                msg = stationarity['message'] if stationarity else "Stationarity check failed"
                print(f"[CalibrateIMU] Device not stationary: {msg}")
                self.update_ui_threadsafe_if_foreground(self.handle_calibration_error,
                    f"Device not stationary!\n\n{msg}\n\nPlace on flat surface and try again.")
                return

            print("[CalibrateIMU] Device is stationary, proceeding to calibration")

            # Step 2: Perform calibration
            print("[CalibrateIMU] Step 2: Performing calibration...")
            self.update_ui_threadsafe_if_foreground(lambda: self.set_state(CalibrationState.CALIBRATING))
            time.sleep(0.5)  # Brief pause for user to see status change

            if self.is_desktop:
                # Mock calibration
                print("[CalibrateIMU] Mock calibration (desktop)")
                time.sleep(2)
                accel_offsets = (0.1, -0.05, 0.15)
                gyro_offsets = (0.2, -0.1, 0.05)
            else:
                # Real calibration
                print("[CalibrateIMU] Real calibration (hardware)")
                accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
                gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)
                print(f"[CalibrateIMU] Accel sensor: {accel}, Gyro sensor: {gyro}")

                if accel:
                    print("[CalibrateIMU] Calibrating accelerometer (30 samples)...")
                    accel_offsets = SensorManager.calibrate_sensor(accel, samples=30)
                    print(f"[CalibrateIMU] Accel offsets: {accel_offsets}")
                else:
                    accel_offsets = None

                if gyro:
                    print("[CalibrateIMU] Calibrating gyroscope (30 samples)...")
                    gyro_offsets = SensorManager.calibrate_sensor(gyro, samples=30)
                    print(f"[CalibrateIMU] Gyro offsets: {gyro_offsets}")
                else:
                    gyro_offsets = None

            # Step 3: Verify results
            print("[CalibrateIMU] Step 3: Verifying calibration...")
            self.update_ui_threadsafe_if_foreground(lambda: self.set_state(CalibrationState.VERIFYING))
            time.sleep(0.5)

            if self.is_desktop:
                verify_quality = self.get_mock_quality(good=True)
            else:
                print("[CalibrateIMU] Checking calibration quality (50 samples)...")
                verify_quality = SensorManager.check_calibration_quality(samples=50)
                print(f"[CalibrateIMU] Verification quality: {verify_quality}")

            if verify_quality is None:
                print("[CalibrateIMU] Verification failed")
                self.update_ui_threadsafe_if_foreground(self.handle_calibration_error,
                    "Calibration completed but verification failed")
                return

            # Step 4: Show results
            print("[CalibrateIMU] Step 4: Showing results...")
            rating = verify_quality['quality_rating']
            score = verify_quality['quality_score']

            result_msg = f"Calibration successful!\n\nNew quality: {rating} ({score*100:.0f}%)"
            if accel_offsets:
                result_msg += f"\n\nAccel offsets:\nX:{accel_offsets[0]:.3f} Y:{accel_offsets[1]:.3f} Z:{accel_offsets[2]:.3f}"
            if gyro_offsets:
                result_msg += f"\n\nGyro offsets:\nX:{gyro_offsets[0]:.3f} Y:{gyro_offsets[1]:.3f} Z:{gyro_offsets[2]:.3f}"

            print(f"[CalibrateIMU] Calibration compl	ete! Result: {result_msg[:80]}")
            self.update_ui_threadsafe_if_foreground(self.show_calibration_complete, result_msg)

            print("[CalibrateIMU] === Calibration thread finished ===")

        except Exception as e:
            print(f"[CalibrateIMU] Calibration error: {e}")
            import sys
            sys.print_exception(e)
            self.update_ui_threadsafe_if_foreground(self.handle_calibration_error, str(e))
	
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

    def get_mock_quality(self, good=False):
        """Generate mock quality data for desktop testing."""
        import random

        if good:
            # Simulate excellent calibration after calibration
            return {
                'accel_mean': (random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 9.8 + random.uniform(-0.1, 0.1)),
                'accel_variance': (random.uniform(0.001, 0.02), random.uniform(0.001, 0.02), random.uniform(0.001, 0.02)),
                'gyro_mean': (random.uniform(-0.1, 0.1), random.uniform(-0.1, 0.1), random.uniform(-0.1, 0.1)),
                'gyro_variance': (random.uniform(0.01, 0.2), random.uniform(0.01, 0.2), random.uniform(0.01, 0.2)),
                'quality_score': random.uniform(0.90, 0.99),
                'quality_rating': "Good",
                'issues': []
            }
        else:
            # Simulate mediocre calibration before calibration
            return {
                'accel_mean': (random.uniform(-1.0, 1.0), random.uniform(-1.0, 1.0), 9.8 + random.uniform(-2.0, 2.0)),
                'accel_variance': (random.uniform(0.2, 0.5), random.uniform(0.2, 0.5), random.uniform(0.2, 0.5)),
                'gyro_mean': (random.uniform(-3.0, 3.0), random.uniform(-3.0, 3.0), random.uniform(-3.0, 3.0)),
                'gyro_variance': (random.uniform(2.0, 5.0), random.uniform(2.0, 5.0), random.uniform(2.0, 5.0)),
                'quality_score': random.uniform(0.4, 0.6),
                'quality_rating': "Fair",
                'issues': ["High accelerometer variance", "Gyro not near zero"]
            }
