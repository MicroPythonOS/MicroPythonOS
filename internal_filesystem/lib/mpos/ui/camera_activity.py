import logging
import lvgl as lv
from .activity import Activity
from .appearance_manager import AppearanceManager
from .display_metrics import DisplayMetrics
from .settings_activity import SettingsActivity

logger = logging.getLogger(__name__)


class CameraActivity(Activity):
    def __init__(self):
        super().__init__()
        self._camera = None
        self._container = None
        self._main_btn = None
        self._is_recording = False
        self._settings_button = None
        self._timer = None
        self._flash_ctrl = None
        self._current_mode = "photo"

        self.SETTINGS = {
            "settings_resolution": {
                "type": "options",
                "label": "Resolution",
                "values": {
                    "64x64": 0,
                    "QVGA": 1,
                    "CIF": 2,
                    "VGA": 4,
                    "SVGA": 5,
                    "XGA": 6,
                    "SXGA": 7,
                    "UXGA": 8,
                },
                "value": 4,
                "dropdown": True,
            },
            "settings_pixformat": {
                "type": "options",
                "label": "Pixel Format",
                "values": {
                    "RGB565": 1,
                    "YUV422": 2,
                    "GRAYSCALE": 4,
                    "JPEG": 5,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_led_intensity": {
                "type": "options",
                "label": "LED Intensity",
                "values": {
                    "0": 0,
                    "1": 1,
                    "2": 2,
                    "3": 3,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_quality": {
                "type": "options",
                "label": "Quality",
                "values": {
                    "10": 10,
                    "12": 12,
                    "14": 14,
                    "16": 16,
                    "18": 18,
                    "20": 20,
                    "22": 22,
                    "24": 24,
                    "26": 26,
                    "28": 28,
                    "30": 30,
                    "32": 32,
                    "34": 34,
                    "36": 36,
                    "38": 38,
                    "40": 40,
                    "42": 42,
                    "44": 44,
                    "46": 46,
                    "48": 48,
                    "50": 50,
                    "52": 52,
                    "54": 54,
                    "56": 56,
                    "58": 58,
                    "60": 60,
                    "62": 62,
                    "63": 63,
                },
                "value": 10,
                "dropdown": True,
            },
            "settings_brightness": {
                "type": "options",
                "label": "Brightness",
                "values": {
                    "-2": -2,
                    "-1": -1,
                    "0": 0,
                    "1": 1,
                    "2": 2,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_contrast": {
                "type": "options",
                "label": "Contrast",
                "values": {
                    "-2": -2,
                    "-1": -1,
                    "0": 0,
                    "1": 1,
                    "2": 2,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_saturation": {
                "type": "options",
                "label": "Saturation",
                "values": {
                    "-2": -2,
                    "-1": -1,
                    "0": 0,
                    "1": 1,
                    "2": 2,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_hmirror": {
                "type": "bool",
                "label": "H-Mirror",
                "value": False,
            },
            "settings_vflip": {
                "type": "bool",
                "label": "V-Flip",
                "value": False,
            },
            "settings_gainceiling": {
                "type": "options",
                "label": "Gain Ceiling",
                "values": {
                    "2x": 0,
                    "4x": 1,
                    "8x": 2,
                    "16x": 3,
                    "32x": 4,
                    "64x": 5,
                    "128x": 6,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_agc_gain": {
                "type": "options",
                "label": "AGC Gain",
                "values": {
                    "0x": 0,
                    "2x": 1,
                    "4x": 2,
                    "8x": 3,
                    "16x": 4,
                    "32x": 5,
                    "64x": 6,
                    "128x": 7,
                },
                "value": 0,
                "dropdown": True,
            },
            "settings_dcw": {
                "type": "options",
                "label": "DCW",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_raw_gma": {
                "type": "options",
                "label": "Raw GMA",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_bpc": {
                "type": "options",
                "label": "BPC",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_wpc": {
                "type": "options",
                "label": "WPC",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_aec_sensor": {
                "type": "options",
                "label": "AEC Sensor",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
            "settings_aec_dsp": {
                "type": "options",
                "label": "AEC DSP",
                "values": {
                    "Enable": 1,
                    "Disable": 0,
                },
                "value": 1,
                "dropdown": True,
            },
        }

    def on_start(self, request):
        super().on_start(request)
        self._create_ui()

    def on_resume(self):
        super().on_resume()

    def on_new_intent(self, request):
        super().on_new_intent(request)

    def on_pause(self):
        super().on_pause()
        self._stop_camera()

    def _create_ui(self):
        container = lv.obj(lv.screen_active())
        container.set_size(lv.pct(100), lv.pct(100))
        self._container = container

        try:
            import camera
            self._camera = camera
            self._init_camera()
            self._create_camera_feed()
            if __debug__: logger.debug("Camera initialized successfully")
        except ImportError:
            logger.error("Camera module not available on this device")
            self._show_no_camera_message()
        except Exception as e:
            logger.error("Failed to initialize camera: %s", e)
            self._show_no_camera_message()

        self._create_controls()
        self._create_settings_button()

    def _init_camera(self):
        if self._camera is None:
            return
        self._cam = self._camera.init(0, format=self._camera.JPEG,
                                      fb_location=self._camera.PSRAM_HUB)
        if __debug__: logger.debug("Camera init returned: %s", self._cam)

    def _show_no_camera_message(self):
        no_cam_label = lv.label(self._container)
        no_cam_label.set_text("Camera not available")
        no_cam_label.center()

    def _create_camera_feed(self):
        if self._cam is None:
            if __debug__: logger.debug("No camera object, not creating feed")
            return
        try:
            self._img = lv.image(self._container)
            self._img.set_size(lv.pct(100), DisplayMetrics.height_pct(80))
            self._img.align(lv.ALIGN.TOP_MID, 0, 0)
            self._img.set_style_border_width(0, 0)
            self._img.set_style_border_opa(lv.OPA.TRANSP, 0)
            self._img.set_style_radius(0, 0)
            self._img.set_style_bg_opa(lv.OPA.TRANSP, 0)
            self._img.set_style_pad_all(0, 0)
            self._img.set_style_pad_top(0, 0)
            self._img.set_style_pad_bottom(0, 0)
            self._img.set_style_pad_left(0, 0)
            self._img.set_style_pad_right(0, 0)
            self._img.set_style_clip_corner(True, 0)

            self._img.add_flag(lv.obj.FLAG.CLICKABLE)
            self._img.add_event_cb(self._on_feed_click, lv.EVENT.CLICKED, None)
        except Exception as e:
            logger.error("Error creating camera feed: %s", e)

    def _create_controls(self):
        ctrl_bar = lv.obj(self._container)
        ctrl_bar.set_size(lv.pct(100), lv.pct(20))
        ctrl_bar.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        capture_btn = lv.button(ctrl_bar)
        capture_btn.set_size(64, 64)
        capture_btn.align(lv.ALIGN.CENTER, 0, 0)
        capture_btn.add_event_cb(self._on_capture, lv.EVENT.CLICKED, None)
        capture_btn.set_style_radius(32, 0)
        self._main_btn = capture_btn

        cap_label = lv.label(capture_btn)
        cap_label.set_text("Capture")

        if self._camera is not None:
            mode_btn = lv.button(ctrl_bar)
            mode_btn.align_to(capture_btn, lv.ALIGN.OUT_LEFT_MID, -10, 0)
            mode_btn.add_event_cb(self._on_mode_switch, lv.EVENT.CLICKED, None)

            mode_label = lv.label(mode_btn)
            mode_label.set_text("Photo")

            flash_btn = lv.button(ctrl_bar)
            flash_btn.align_to(capture_btn, lv.ALIGN.OUT_RIGHT_MID, 10, 0)
            flash_btn.add_event_cb(self._on_flash_toggle, lv.EVENT.CLICKED, None)

            flash_label = lv.label(flash_btn)
            flash_label.set_text("Flash: OFF")
            self._flash_ctrl = flash_label

    def _create_settings_button(self):
        self._settings_button = lv.button(self._container)
        self._settings_button.set_size(40, 40)
        self._settings_button.align(lv.ALIGN.TOP_RIGHT, 0, AppearanceManager.NOTIFICATION_BAR_HEIGHT)
        self._settings_button.add_event_cb(self._on_settings_click, lv.EVENT.CLICKED, None)

        settings_label = lv.label(self._settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)

    def _on_settings_click(self, event):
        if __debug__: logger.debug("Settings button clicked, starting SettingsActivity")
        from .activity_manager import start_activity
        start_activity(self, SettingsActivity(self.SETTINGS))

    def _on_capture(self, event):
        if self._cam is None:
            if __debug__: logger.debug("Camera not available, cannot capture")
            return
        if __debug__: logger.debug("Capture button pressed")
        try:
            buf = self._cam.capture()
            if buf is not None:
                if __debug__: logger.debug("Captured image, buffer length: %s", len(buf))
            else:
                if __debug__: logger.debug("Captured image is None")
        except Exception as e:
            logger.error("Error during capture: %s", e)

    def _on_mode_switch(self, event):
        if self._current_mode == "photo":
            self._current_mode = "video"
            if __debug__: logger.debug("Switched to video mode")
        else:
            self._current_mode = "photo"
            if __debug__: logger.debug("Switched to photo mode")

    def _on_flash_toggle(self, event):
        if __debug__: logger.debug("Flash toggle pressed")
        if self._flash_ctrl.get_text() == "Flash: OFF":
            self._flash_ctrl.set_text("Flash: ON")
            if __debug__: logger.debug("Flash turned ON")
        else:
            self._flash_ctrl.set_text("Flash: OFF")
            if __debug__: logger.debug("Flash turned OFF")

    def _on_feed_click(self, event):
        if __debug__: logger.debug("Camera feed clicked (acts as tap-to-focus)")

    def _start_recording(self):
        if __debug__: logger.debug("Starting recording...")
        self._is_recording = True

    def _stop_recording(self):
        if __debug__: logger.debug("Stopping recording...")
        self._is_recording = False

    def _stop_camera(self):
        if self._cam is not None:
            try:
                self._cam.deinit()
                if __debug__: logger.debug("Camera deinitialized")
            except Exception as e:
                logger.error("Error deinitializing camera: %s", e)
        if self._timer is not None:
            self._timer.delete()
            self._timer = None
