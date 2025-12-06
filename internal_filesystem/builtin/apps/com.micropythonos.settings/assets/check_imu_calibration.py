"""Check IMU Calibration Activity.

Shows current IMU calibration quality with real-time sensor values,
variance, expected value comparison, and overall quality score.
"""

import lvgl as lv
import time
import sys
from mpos.app.activity import Activity
import mpos.ui
import mpos.sensor_manager as SensorManager


class CheckIMUCalibrationActivity(Activity):
    """Display IMU calibration quality with real-time monitoring."""

    # Update interval for real-time display (milliseconds)
    UPDATE_INTERVAL = 100

    # State
    updating = False
    update_timer = None

    # Widgets
    status_label = None
    quality_label = None
    accel_labels = []  # [x_label, y_label, z_label]
    gyro_labels = []
    issues_label = None
    quality_score_label = None

    def __init__(self):
        super().__init__()
        self.is_desktop = sys.platform != "esp32"

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        # Title
        title = lv.label(screen)
        title.set_text("IMU Calibration Check")
        title.set_style_text_font(lv.font_montserrat_20, 0)

        # Status label
        self.status_label = lv.label(screen)
        self.status_label.set_text("Checking...")
        self.status_label.set_style_text_font(lv.font_montserrat_14, 0)

        # Separator
        sep1 = lv.obj(screen)
        sep1.set_size(lv.pct(100), 2)
        sep1.set_style_bg_color(lv.color_hex(0x666666), 0)

        # Quality score (large, prominent)
        self.quality_score_label = lv.label(screen)
        self.quality_score_label.set_text("Quality: --")
        self.quality_score_label.set_style_text_font(lv.font_montserrat_20, 0)

        # Accelerometer section
        accel_title = lv.label(screen)
        accel_title.set_text("Accelerometer (m/s²)")
        accel_title.set_style_text_font(lv.font_montserrat_14, 0)

        for axis in ['X', 'Y', 'Z']:
            label = lv.label(screen)
            label.set_text(f"{axis}: --")
            label.set_style_text_font(lv.font_montserrat_12, 0)
            self.accel_labels.append(label)

        # Gyroscope section
        gyro_title = lv.label(screen)
        gyro_title.set_text("Gyroscope (deg/s)")
        gyro_title.set_style_text_font(lv.font_montserrat_14, 0)

        for axis in ['X', 'Y', 'Z']:
            label = lv.label(screen)
            label.set_text(f"{axis}: --")
            label.set_style_text_font(lv.font_montserrat_12, 0)
            self.gyro_labels.append(label)

        # Separator
        sep2 = lv.obj(screen)
        sep2.set_size(lv.pct(100), 2)
        sep2.set_style_bg_color(lv.color_hex(0x666666), 0)

        # Issues label
        self.issues_label = lv.label(screen)
        self.issues_label.set_text("Issues: None")
        self.issues_label.set_style_text_font(lv.font_montserrat_12, 0)
        self.issues_label.set_style_text_color(lv.color_hex(0xFF6666), 0)
        self.issues_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.issues_label.set_width(lv.pct(95))

        # Button container
        btn_cont = lv.obj(screen)
        btn_cont.set_width(lv.pct(100))
        btn_cont.set_height(lv.SIZE_CONTENT)
        btn_cont.set_style_border_width(0, 0)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, 0)

        # Back button
        back_btn = lv.button(btn_cont)
        back_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        back_label = lv.label(back_btn)
        back_label.set_text("Back")
        back_label.center()
        back_btn.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)

        # Calibrate button
        calibrate_btn = lv.button(btn_cont)
        calibrate_btn.set_size(lv.pct(45), lv.SIZE_CONTENT)
        calibrate_label = lv.label(calibrate_btn)
        calibrate_label.set_text("Calibrate")
        calibrate_label.center()
        calibrate_btn.add_event_cb(self.start_calibration, lv.EVENT.CLICKED, None)

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)

        # Check if IMU is available
        if not self.is_desktop and not SensorManager.is_available():
            self.status_label.set_text("IMU not available on this device")
            self.quality_score_label.set_text("N/A")
            return

        # Start real-time updates
        self.updating = True
        self.update_timer = lv.timer_create(self.update_display, self.UPDATE_INTERVAL, None)

    def onPause(self, screen):
        # Stop updates
        self.updating = False
        if self.update_timer:
            self.update_timer.delete()
            self.update_timer = None
        super().onPause(screen)

    def update_display(self, timer=None):
        """Update display with current sensor values and quality."""
        if not self.updating:
            return

        try:
            # Get quality check (desktop or hardware)
            if self.is_desktop:
                quality = self.get_mock_quality()
            else:
                # Use only 5 samples for real-time display (faster, less blocking)
                quality = SensorManager.check_calibration_quality(samples=5)

            if quality is None:
                self.status_label.set_text("Error reading IMU")
                return

            # Update quality score
            score = quality['quality_score']
            rating = quality['quality_rating']
            self.quality_score_label.set_text(f"Quality: {rating} ({score*100:.0f}%)")

            # Color based on rating
            if rating == "Good":
                color = 0x66FF66  # Green
            elif rating == "Fair":
                color = 0xFFFF66  # Yellow
            else:
                color = 0xFF6666  # Red
            self.quality_score_label.set_style_text_color(lv.color_hex(color), 0)

            # Update accelerometer values
            accel_mean = quality['accel_mean']
            accel_var = quality['accel_variance']
            for i, (mean, var) in enumerate(zip(accel_mean, accel_var)):
                axis = ['X', 'Y', 'Z'][i]
                self.accel_labels[i].set_text(f"{axis}: {mean:6.2f} (var: {var:.3f})")

            # Update gyroscope values
            gyro_mean = quality['gyro_mean']
            gyro_var = quality['gyro_variance']
            for i, (mean, var) in enumerate(zip(gyro_mean, gyro_var)):
                axis = ['X', 'Y', 'Z'][i]
                self.gyro_labels[i].set_text(f"{axis}: {mean:6.2f} (var: {var:.3f})")

            # Update issues
            issues = quality['issues']
            if issues:
                issues_text = "Issues:\n" + "\n".join(f"- {issue}" for issue in issues)
            else:
                issues_text = "Issues: None - calibration looks good!"
            self.issues_label.set_text(issues_text)

            self.status_label.set_text("Real-time monitoring (place on flat surface)")
        except:
            # Widgets were deleted (activity closed), stop updating
            self.updating = False

    def get_mock_quality(self):
        """Generate mock quality data for desktop testing."""
        import random

        # Simulate good calibration with small random noise
        return {
            'accel_mean': (
                random.uniform(-0.2, 0.2),
                random.uniform(-0.2, 0.2),
                9.8 + random.uniform(-0.3, 0.3)
            ),
            'accel_variance': (
                random.uniform(0.01, 0.1),
                random.uniform(0.01, 0.1),
                random.uniform(0.01, 0.1)
            ),
            'gyro_mean': (
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5),
                random.uniform(-0.5, 0.5)
            ),
            'gyro_variance': (
                random.uniform(0.1, 1.0),
                random.uniform(0.1, 1.0),
                random.uniform(0.1, 1.0)
            ),
            'quality_score': random.uniform(0.75, 0.95),
            'quality_rating': "Good",
            'issues': []
        }

    def start_calibration(self, event):
        """Navigate to calibration activity."""
        from mpos.content.intent import Intent
        from calibrate_imu import CalibrateIMUActivity

        intent = Intent(activity_class=CalibrateIMUActivity)
        self.startActivity(intent)
