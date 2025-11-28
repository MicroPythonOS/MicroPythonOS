import lvgl as lv
from mpos.ui.keyboard import MposKeyboard

try:
    import webcam
except Exception as e:
    print(f"Info: could not import webcam module: {e}")

from mpos.apps import Activity
from mpos.config import SharedPreferences
from mpos.content.intent import Intent
import mpos.time

class CameraApp(Activity):

    DEFAULT_WIDTH = 320 # 240 would be better but webcam doesn't support this (yet)
    DEFAULT_HEIGHT = 240

    button_width = 60
    button_height = 45
    colormode = False

    status_label_text = "No camera found."
    status_label_text_searching = "Searching QR codes...\n\nHold still and try varying scan distance (10-25cm) and QR size (4-12cm). Ensure proper lighting."
    status_label_text_found = "Decoding QR..."

    cam = None
    current_cam_buffer = None # Holds the current memoryview to prevent garbage collection
    width = None
    height = None

    image = None
    image_dsc = None
    scanqr_mode = None
    use_webcam = False
    keepliveqrdecoding = False
    
    capture_timer = None
    
    # Widgets:
    main_screen = None
    qr_label = None
    qr_button = None
    snap_button = None
    status_label = None
    status_label_cont = None

    def onCreate(self):
        self.scanqr_mode = self.getIntent().extras.get("scanqr_mode")
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(1, 0)
        self.main_screen.set_style_border_width(0, 0)
        self.main_screen.set_size(lv.pct(100), lv.pct(100))
        self.main_screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        # Initialize LVGL image widget
        self.image = lv.image(self.main_screen)
        self.image.align(lv.ALIGN.LEFT_MID, 0, 0)
        close_button = lv.button(self.main_screen)
        close_button.set_size(self.button_width, self.button_height)
        close_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        close_label = lv.label(close_button)
        close_label.set_text(lv.SYMBOL.CLOSE)
        close_label.center()
        close_button.add_event_cb(lambda e: self.finish(),lv.EVENT.CLICKED,None)
        # Settings button
        settings_button = lv.button(self.main_screen)
        settings_button.set_size(self.button_width, self.button_height)
        settings_button.align(lv.ALIGN.TOP_RIGHT, 0, self.button_height + 5)
        settings_label = lv.label(settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.center()
        settings_button.add_event_cb(lambda e: self.open_settings(),lv.EVENT.CLICKED,None)
        self.snap_button = lv.button(self.main_screen)
        self.snap_button.set_size(self.button_width, self.button_height)
        self.snap_button.align(lv.ALIGN.RIGHT_MID, 0, 0)
        self.snap_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.snap_button.add_event_cb(self.snap_button_click,lv.EVENT.CLICKED,None)
        snap_label = lv.label(self.snap_button)
        snap_label.set_text(lv.SYMBOL.OK)
        snap_label.center()
        self.zoom_button = lv.button(self.main_screen)
        self.zoom_button.set_size(self.button_width, self.button_height)
        self.zoom_button.align(lv.ALIGN.RIGHT_MID, 0, self.button_height + 5)
        self.zoom_button.add_event_cb(self.zoom_button_click,lv.EVENT.CLICKED,None)
        zoom_label = lv.label(self.zoom_button)
        zoom_label.set_text("Z")
        zoom_label.center()
        self.qr_button = lv.button(self.main_screen)
        self.qr_button.set_size(self.button_width, self.button_height)
        self.qr_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.qr_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.qr_button.add_event_cb(self.qr_button_click,lv.EVENT.CLICKED,None)
        self.qr_label = lv.label(self.qr_button)
        self.qr_label.set_text(lv.SYMBOL.EYE_OPEN)
        self.qr_label.center()
        self.status_label_cont = lv.obj(self.main_screen)
        width = mpos.ui.pct_of_display_width(70)
        height = mpos.ui.pct_of_display_width(60)
        self.status_label_cont.set_size(width,height)
        center_w = round((mpos.ui.pct_of_display_width(100) - self.button_width - 5 - width)/2)
        center_h = round((mpos.ui.pct_of_display_height(100) - height)/2)
        self.status_label_cont.set_pos(center_w,center_h)
        self.status_label_cont.set_style_bg_color(lv.color_white(), 0)
        self.status_label_cont.set_style_bg_opa(66, 0)
        self.status_label_cont.set_style_border_width(0, 0)
        self.status_label = lv.label(self.status_label_cont)
        self.status_label.set_text("No camera found.")
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(100))
        self.status_label.center()
        self.setContentView(self.main_screen)
    
    def onResume(self, screen):
        self.load_resolution_preference() # needs to be done BEFORE the camera is initialized
        self.cam = init_internal_cam(self.width, self.height)
        if self.cam:
            self.image.set_rotation(900) # internal camera is rotated 90 degrees
            # Apply saved camera settings, only for internal camera for now:
            apply_camera_settings(self.cam, self.use_webcam) # needs to be done AFTER the camera is initialized
        else:
            print("camera app: no internal camera found, trying webcam on /dev/video0")
            try:
                # Initialize webcam with desired resolution directly
                print(f"Initializing webcam at {self.width}x{self.height}")
                self.cam = webcam.init("/dev/video0", width=self.width, height=self.height)
                self.use_webcam = True
            except Exception as e:
                print(f"camera app: webcam exception: {e}")
        if self.cam:
            print("Camera app initialized, continuing...")
            self.update_preview_image()
            self.capture_timer = lv.timer_create(self.try_capture, 100, None)
            self.status_label_cont.add_flag(lv.obj.FLAG.HIDDEN)
            if self.scanqr_mode or self.keepliveqrdecoding:
                self.start_qr_decoding()
            else:
                self.qr_button.remove_flag(lv.obj.FLAG.HIDDEN)
                self.snap_button.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            print("No camera found, stopping camera app")
            if self.scanqr_mode:
                self.finish()

    def onPause(self, screen):
        print("camera app backgrounded, cleaning up...")
        if self.capture_timer:
            self.capture_timer.delete()
        if self.use_webcam:
            webcam.deinit(self.cam)
        elif self.cam:
            self.cam.deinit()
            # Power off, otherwise it keeps using a lot of current
            try:
                from machine import Pin, I2C
                i2c = I2C(1, scl=Pin(16), sda=Pin(21))  # Adjust pins and frequency
                #devices = i2c.scan()
                #print([hex(addr) for addr in devices]) # finds it on 60 = 0x3C after init
                camera_addr = 0x3C # for OV5640
                reg_addr = 0x3008
                reg_high = (reg_addr >> 8) & 0xFF  # 0x30
                reg_low = reg_addr & 0xFF         # 0x08
                power_off_command = 0x42 # Power off command
                i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
            except Exception as e:
                print(f"Warning: powering off camera got exception: {e}")
        print("camera app cleanup done.")

    def load_resolution_preference(self):
        """Load resolution preference from SharedPreferences and update width/height."""
        prefs = SharedPreferences("com.micropythonos.camera")
        resolution_str = prefs.get_string("resolution", f"{self.DEFAULT_WIDTH}x{self.DEFAULT_HEIGHT}")
        self.colormode = prefs.get_bool("colormode", False)
        try:
            width_str, height_str = resolution_str.split('x')
            self.width = int(width_str)
            self.height = int(height_str)
            print(f"Camera resolution loaded: {self.width}x{self.height}")
        except Exception as e:
            print(f"Error parsing resolution '{resolution_str}': {e}, using default 320x240")
            self.width = self.DEFAULT_WIDTH
            self.height = self.DEFAULT_HEIGHT

    def update_preview_image(self):
        self.image_dsc = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": self.width,
                "h": self.height,
                "stride": self.width * (2 if self.colormode else 1),
                "cf": lv.COLOR_FORMAT.RGB565 if self.colormode else lv.COLOR_FORMAT.L8
            },
            'data_size': self.width * self.height * (2 if self.colormode else 1),
            'data': None # Will be updated per frame
        })
        self.image.set_src(self.image_dsc)
        disp = lv.display_get_default()
        target_h = disp.get_vertical_resolution()
        #target_w = disp.get_horizontal_resolution() - self.button_width - 5 # leave 5px for border
        target_w = target_h # square
        print(f"scaling to size: {target_w}x{target_h}")
        scale_factor_w = round(target_w * 256 / self.width)
        scale_factor_h = round(target_h * 256 / self.height)
        print(f"scale_factors: {scale_factor_w},{scale_factor_h}")
        self.image.set_size(target_w, target_h)
        #self.image.set_scale(max(scale_factor_w,scale_factor_h)) # fills the entire screen but cuts off borders
        self.image.set_scale(min(scale_factor_w,scale_factor_h))

    def qrdecode_one(self):
        try:
            import qrdecode
            import utime
            before = utime.ticks_ms()
            result = qrdecode.qrdecode(self.current_cam_buffer, self.width, self.height)
            after = utime.ticks_ms()
            #result = bytearray("INSERT_QR_HERE", "utf-8")
            if not result:
                self.status_label.set_text(self.status_label_text_searching)
            else:
                print(f"SUCCESSFUL QR DECODE TOOK: {after-before}ms")
                result = remove_bom(result)
                result = print_qr_buffer(result)
                print(f"QR decoding found: {result}")
                if self.scanqr_mode:
                    self.setResult(True, result)
                    self.finish()
                else:
                    self.status_label.set_text(result) # in the future, the status_label text should be copy-paste-able
                self.stop_qr_decoding()
        except ValueError as e:
            print("QR ValueError: ", e)
            self.status_label.set_text(self.status_label_text_searching)
        except TypeError as e:
            print("QR TypeError: ", e)
            self.status_label.set_text(self.status_label_text_found)
        except Exception as e:
            print("QR got other error: ", e)

    def snap_button_click(self, e):
        print("Picture taken!")
        import os
        try:
            os.mkdir("data")
        except OSError:
            pass
        try:
            os.mkdir("data/images")
        except OSError:
            pass
        if self.current_cam_buffer is not None:
            colorname = "RGB565" if self.colormode else "GRAY"
            filename=f"data/images/camera_capture_{mpos.time.epoch_seconds()}_{self.width}x{self.height}_{colorname}.raw"
            try:
                with open(filename, 'wb') as f:
                    f.write(self.current_cam_buffer)
                print(f"Successfully wrote current_cam_buffer to {filename}")
            except OSError as e:
                print(f"Error writing to file: {e}")
    
    def start_qr_decoding(self):
        print("Activating live QR decoding...")
        self.keepliveqrdecoding = True
        self.qr_label.set_text(lv.SYMBOL.EYE_CLOSE)
        self.status_label_cont.remove_flag(lv.obj.FLAG.HIDDEN)
        self.status_label.set_text(self.status_label_text_searching)
    
    def stop_qr_decoding(self):
        print("Deactivating live QR decoding...")
        self.keepliveqrdecoding = False
        self.qr_label.set_text(lv.SYMBOL.EYE_OPEN)
        self.status_label_text = self.status_label.get_text()
        if self.status_label_text in (self.status_label_text_searching or self.status_label_text_found): # if it found a QR code, leave it
            self.status_label_cont.add_flag(lv.obj.FLAG.HIDDEN)
    
    def qr_button_click(self, e):
        if not self.keepliveqrdecoding:
            self.start_qr_decoding()
        else:
            self.stop_qr_decoding()

    def zoom_button_click(self, e):
        print("zooming...")
        if self.use_webcam:
            print("zoom_button_click is not supported for webcam")
            return
        if self.cam:
            prefs = SharedPreferences("com.micropythonos.camera")
            startX = prefs.get_int("startX", CameraSettingsActivity.startX_default)
            startY = prefs.get_int("startX", CameraSettingsActivity.startY_default)
            endX = prefs.get_int("startX", CameraSettingsActivity.endX_default)
            endY = prefs.get_int("startX", CameraSettingsActivity.endY_default)
            offsetX = prefs.get_int("startX", CameraSettingsActivity.offsetX_default)
            offsetY = prefs.get_int("startX", CameraSettingsActivity.offsetY_default)
            totalX = prefs.get_int("startX", CameraSettingsActivity.totalX_default)
            totalY = prefs.get_int("startX", CameraSettingsActivity.totalY_default)
            outputX = prefs.get_int("startX", CameraSettingsActivity.outputX_default)
            outputY = prefs.get_int("startX", CameraSettingsActivity.outputY_default)
            scale = prefs.get_bool("scale", CameraSettingsActivity.scale_default)
            binning = prefs.get_bool("binning", CameraSettingsActivity.binning_default)
            result = self.cam.set_res_raw(startX,startY,endX,endY,offsetX,offsetY,totalX,totalY,outputX,outputY,scale,binning)
            print(f"self.cam.set_res_raw returned {result}")

    def open_settings(self):
        self.image_dsc.data = None
        self.current_cam_buffer = None
        intent = Intent(activity_class=CameraSettingsActivity)
        self.startActivity(intent)

    def try_capture(self, event):
        #print("capturing camera frame")
        try:
            if self.use_webcam:
                self.current_cam_buffer = webcam.capture_frame(self.cam, "rgb565" if self.colormode else "grayscale")
            elif self.cam.frame_available():
                #self.cam.free_buffer()
                self.current_cam_buffer = self.cam.capture()
                #self.cam.free_buffer()

            if self.current_cam_buffer and len(self.current_cam_buffer):
                # Defensive check: verify buffer size matches expected dimensions
                expected_size = self.width * self.height * (2 if self.colormode else 1)
                actual_size = len(self.current_cam_buffer)

                if actual_size == expected_size:
                    self.image_dsc.data = self.current_cam_buffer
                    #self.image.invalidate() # does not work so do this:
                    self.image.set_src(self.image_dsc)
                    if not self.use_webcam:
                        self.cam.free_buffer()  # Free the old buffer
                    try:
                        if self.keepliveqrdecoding:
                            self.qrdecode_one()
                    except Exception as qre:
                        print(f"try_capture: qrdecode_one got exception: {qre}")
                else:
                    print(f"Warning: Buffer size mismatch! Expected {expected_size} bytes, got {actual_size} bytes")
                    print(f"  Resolution: {self.width}x{self.height}, discarding frame")
        except Exception as e:
            print(f"Camera capture exception: {e}")


# Non-class functions:
def init_internal_cam(width, height):
    """Initialize internal camera with specified resolution.

    Automatically retries once if initialization fails (to handle I2C poweroff issue).
    """
    try:
        from camera import Camera, GrabMode, PixelFormat, FrameSize, GainCeiling

        # Map resolution to FrameSize enum
        # Format: (width, height): FrameSize
        resolution_map = {
            (96, 96): FrameSize.R96X96,
            (160, 120): FrameSize.QQVGA,
            (128, 128): FrameSize.R128X128,
            (176, 144): FrameSize.QCIF,
            (240, 176): FrameSize.HQVGA,
            (240, 240): FrameSize.R240X240,
            (320, 240): FrameSize.QVGA,
            (320, 320): FrameSize.R320X320,
            (400, 296): FrameSize.CIF,
            (480, 320): FrameSize.HVGA,
            (480, 480): FrameSize.R480X480,
            (640, 480): FrameSize.VGA,
            (640, 640): FrameSize.R640X640,
            (720, 720): FrameSize.R720X720,
            (800, 600): FrameSize.SVGA,
            (800, 800): FrameSize.R800X800,
            (960, 960): FrameSize.R960X960,
            (1024, 768): FrameSize.XGA,
            (1024,1024): FrameSize.R1024X1024,
            (1280, 720): FrameSize.HD,
            (1280, 1024): FrameSize.SXGA,
            (1280, 1280): FrameSize.R1280X1280,
            (1600, 1200): FrameSize.UXGA,
            (1920, 1080): FrameSize.FHD,
        }

        frame_size = resolution_map.get((width, height), FrameSize.QVGA)
        print(f"init_internal_cam: Using FrameSize for {width}x{height}")

        # Try to initialize, with one retry for I2C poweroff issue
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                cam = Camera(
                    data_pins=[12,13,15,11,14,10,7,2],
                    vsync_pin=6,
                    href_pin=4,
                    sda_pin=21,
                    scl_pin=16,
                    pclk_pin=9,
                    xclk_pin=8,
                    xclk_freq=20000000,
                    powerdown_pin=-1,
                    reset_pin=-1,
                    pixel_format=PixelFormat.RGB565 if self.colormode else PixelFormat.GRAYSCALE,
                    frame_size=frame_size,
                    #grab_mode=GrabMode.WHEN_EMPTY,
                    grab_mode=GrabMode.LATEST,
                    fb_count=1
                )
                cam.set_vflip(True)
                return cam
            except Exception as e:
                if attempt < max_attempts-1:
                    print(f"init_cam attempt {attempt} failed: {e}, retrying...")
                else:
                    print(f"init_cam final exception: {e}")
                    return None
    except Exception as e:
        print(f"init_cam exception: {e}")
        return None

def print_qr_buffer(buffer):
    try:
        # Try to decode buffer as a UTF-8 string
        result = buffer.decode('utf-8')
        # Check if the string is printable (ASCII printable characters)
        if all(32 <= ord(c) <= 126 for c in result):
            return result
    except Exception as e:
        pass
    # If not a valid string or not printable, convert to hex
    hex_str = ' '.join([f'{b:02x}' for b in buffer])
    return hex_str.lower()

# Byte-Order-Mark is added sometimes
def remove_bom(buffer):
    bom = b'\xEF\xBB\xBF'
    if buffer.startswith(bom):
        return buffer[3:]
    return buffer


def apply_camera_settings(cam, use_webcam):
    """Apply all saved camera settings from SharedPreferences to ESP32 camera.

    Only applies settings when use_webcam is False (ESP32 camera).
    Settings are applied in dependency order (master switches before dependent values).

    Args:
        cam: Camera object
        use_webcam: Boolean indicating if using webcam
    """
    if not cam or use_webcam:
        print("apply_camera_settings: Skipping (no camera or webcam mode)")
        return

    prefs = SharedPreferences("com.micropythonos.camera")

    try:
        # Basic image adjustments
        brightness = prefs.get_int("brightness", 0)
        cam.set_brightness(brightness)

        contrast = prefs.get_int("contrast", 0)
        cam.set_contrast(contrast)

        saturation = prefs.get_int("saturation", 0)
        cam.set_saturation(saturation)

        # Orientation
        hmirror = prefs.get_bool("hmirror", False)
        cam.set_hmirror(hmirror)

        vflip = prefs.get_bool("vflip", True)
        cam.set_vflip(vflip)

        # Special effect
        special_effect = prefs.get_int("special_effect", 0)
        cam.set_special_effect(special_effect)

        # Exposure control (apply master switch first, then manual value)
        exposure_ctrl = prefs.get_bool("exposure_ctrl", True)
        cam.set_exposure_ctrl(exposure_ctrl)

        if not exposure_ctrl:
            aec_value = prefs.get_int("aec_value", 300)
            cam.set_aec_value(aec_value)

        ae_level = prefs.get_int("ae_level", 0)
        cam.set_ae_level(ae_level)

        aec2 = prefs.get_bool("aec2", False)
        cam.set_aec2(aec2)

        # Gain control (apply master switch first, then manual value)
        gain_ctrl = prefs.get_bool("gain_ctrl", True)
        cam.set_gain_ctrl(gain_ctrl)

        if not gain_ctrl:
            agc_gain = prefs.get_int("agc_gain", 0)
            cam.set_agc_gain(agc_gain)

        gainceiling = prefs.get_int("gainceiling", 0)
        cam.set_gainceiling(gainceiling)

        # White balance (apply master switch first, then mode)
        whitebal = prefs.get_bool("whitebal", True)
        cam.set_whitebal(whitebal)

        if not whitebal:
            wb_mode = prefs.get_int("wb_mode", 0)
            cam.set_wb_mode(wb_mode)

        awb_gain = prefs.get_bool("awb_gain", True)
        cam.set_awb_gain(awb_gain)

        # Sensor-specific settings (try/except for unsupported sensors)
        try:
            sharpness = prefs.get_int("sharpness", 0)
            cam.set_sharpness(sharpness)
        except:
            pass  # Not supported on OV2640

        try:
            denoise = prefs.get_int("denoise", 0)
            cam.set_denoise(denoise)
        except:
            pass  # Not supported on OV2640

        # Advanced corrections
        colorbar = prefs.get_bool("colorbar", False)
        cam.set_colorbar(colorbar)

        dcw = prefs.get_bool("dcw", True)
        cam.set_dcw(dcw)

        bpc = prefs.get_bool("bpc", False)
        cam.set_bpc(bpc)

        wpc = prefs.get_bool("wpc", True)
        cam.set_wpc(wpc)

        raw_gma = prefs.get_bool("raw_gma", True)
        cam.set_raw_gma(raw_gma)

        lenc = prefs.get_bool("lenc", True)
        cam.set_lenc(lenc)

        # JPEG quality (only relevant for JPEG format)
        try:
            quality = prefs.get_int("quality", 85)
            cam.set_quality(quality)
        except:
            pass  # Not in JPEG mode

        print("Camera settings applied successfully")

    except Exception as e:
        print(f"Error applying camera settings: {e}")








class CameraSettingsActivity(Activity):
    """Settings activity for comprehensive camera configuration."""

    # Original: { 2560, 1920,   0,   0, 2623, 1951, 32, 16, 2844, 1968 }
    # Worked for digital zoom in C: { 2560, 1920, 0, 0, 2623, 1951, 992, 736, 2844, 1968 }
    startX_default=0
    startY_default=0
    endX_default=2623
    endY_default=1951
    offsetX_default=32
    offsetY_default=16
    totalX_default=2844
    totalY_default=1968
    outputX_default=640
    outputY_default=480
    scale_default=False
    binning_default=False

    # Resolution options for desktop/webcam
    WEBCAM_RESOLUTIONS = [
        ("160x120", "160x120"),
        ("320x180", "320x180"),
        ("320x240", "320x240"),
        ("640x360", "640x360"),
        ("640x480 (30 fps)", "640x480"),
        ("1280x720 (10 fps)", "1280x720"),
        ("1920x1080 (5 fps)", "1920x1080"),
    ]

    # Resolution options for internal camera (ESP32)
    ESP32_RESOLUTIONS = [
        ("96x96", "96x96"),
        ("160x120", "160x120"),
        ("128x128", "128x128"),
        ("176x144", "176x144"),
        ("240x176", "240x176"),
        ("240x240", "240x240"),
        ("320x240", "320x240"),
        ("320x320", "320x320"),
        ("400x296", "400x296"),
        ("480x320", "480x320"),
        ("480x480", "480x480"),
        ("640x480", "640x480"),
        ("640x640", "640x640"),
        ("720x720", "720x720"),
        ("800x600", "800x600"),
        ("800x800", "800x800"),
        ("960x960", "960x960"),
        ("1024x768",  "1024x768"),
        ("1024x1024","1024x1024"),
        ("1280x720",  "1280x720"), # binned 2x2 (in default ov5640.c)
        ("1280x1024", "1280x1024"),
        ("1280x1280", "1280x1280"),
        ("1600x1200", "1600x1200"),
        ("1920x1080", "1920x1080"),
    ]

    # Widgets:
    button_cont = None

    def __init__(self):
        super().__init__()
        self.ui_controls = {}
        self.control_metadata = {}  # Store pref_key and option_values for each control
        self.dependent_controls = {}
        self.is_webcam = False
        self.resolutions = []

    def onCreate(self):
        # Load preferences
        prefs = SharedPreferences("com.micropythonos.camera")

        # Detect platform (webcam vs ESP32)
        try:
            import webcam
            self.is_webcam = True
            self.resolutions = self.WEBCAM_RESOLUTIONS
            print("Using webcam resolutions")
        except:
            self.resolutions = self.ESP32_RESOLUTIONS
            print("Using ESP32 camera resolutions")

        # Create main screen
        screen = lv.obj()
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_style_pad_all(1, 0)

        # Create tabview
        tabview = lv.tabview(screen)
        tabview.set_tab_bar_size(mpos.ui.pct_of_display_height(15))
        #tabview.set_size(lv.pct(100), mpos.ui.pct_of_display_height(80))

        # Create Basic tab (always)
        basic_tab = tabview.add_tab("Basic")
        self.create_basic_tab(basic_tab, prefs)

        # Create Advanced and Expert tabs only for ESP32 camera
        if not self.is_webcam or True: # for now, show all tabs
            advanced_tab = tabview.add_tab("Advanced")
            self.create_advanced_tab(advanced_tab, prefs)

            expert_tab = tabview.add_tab("Expert")
            self.create_expert_tab(expert_tab, prefs)

            #raw_tab = tabview.add_tab("Raw")
            #self.create_raw_tab(raw_tab, prefs)

        self.setContentView(screen)

    def create_slider(self, parent, label_text, min_val, max_val, default_val, pref_key):
        """Create slider with label showing current value."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), 60)
        cont.set_style_pad_all(3, 0)

        label = lv.label(cont)
        label.set_text(f"{label_text}: {default_val}")
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        slider = lv.slider(cont)
        slider.set_size(lv.pct(90), 15)
        slider.set_range(min_val, max_val)
        slider.set_value(default_val, False)
        slider.align(lv.ALIGN.BOTTOM_MID, 0, -10)

        def slider_changed(e):
            val = slider.get_value()
            label.set_text(f"{label_text}: {val}")

        slider.add_event_cb(slider_changed, lv.EVENT.VALUE_CHANGED, None)

        return slider, label, cont

    def create_checkbox(self, parent, label_text, default_val, pref_key):
        """Create checkbox with label."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), 35)
        cont.set_style_pad_all(3, 0)

        checkbox = lv.checkbox(cont)
        checkbox.set_text(label_text)
        if default_val:
            checkbox.add_state(lv.STATE.CHECKED)
        checkbox.align(lv.ALIGN.LEFT_MID, 0, 0)

        return checkbox, cont

    def create_dropdown(self, parent, label_text, options, default_idx, pref_key):
        """Create dropdown with label."""
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), 60)
        cont.set_style_pad_all(3, 0)

        label = lv.label(cont)
        label.set_text(label_text)
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        dropdown = lv.dropdown(cont)
        dropdown.set_size(lv.pct(90), 30)
        dropdown.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)

        options_str = "\n".join([text for text, _ in options])
        dropdown.set_options(options_str)
        dropdown.set_selected(default_idx)

        # Store metadata separately
        option_values = [val for _, val in options]
        self.control_metadata[id(dropdown)] = {
            "pref_key": pref_key,
            "type": "dropdown",
            "option_values": option_values
        }

        return dropdown, cont

    def create_textarea(self, parent, label_text, min_val, max_val, default_val, pref_key):
        cont = lv.obj(parent)
        cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        cont.set_style_pad_all(3, 0)

        label = lv.label(cont)
        label.set_text(f"{label_text}:")
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        textarea = lv.textarea(cont)
        textarea.set_width(lv.pct(50))
        textarea.set_one_line(True) # might not be good for all settings but it's good for most
        textarea.set_text(str(default_val))
        textarea.align(lv.ALIGN.TOP_RIGHT, 0, 0)

        # Initialize keyboard (hidden initially)
        keyboard = MposKeyboard(parent)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        keyboard.set_textarea(textarea)
        keyboard.add_event_cb(lambda e, kbd=keyboard: self.hide_keyboard(kbd), lv.EVENT.READY, None)
        keyboard.add_event_cb(lambda e, kbd=keyboard: self.hide_keyboard(kbd), lv.EVENT.CANCEL, None)
        textarea.add_event_cb(lambda e, kbd=keyboard: self.show_keyboard(kbd), lv.EVENT.CLICKED, None)

        return textarea, cont

    def show_keyboard(self, kbd):
        mpos.ui.anim.smooth_show(kbd)

    def hide_keyboard(self, kbd):
        mpos.ui.anim.smooth_hide(kbd)

    def add_buttons(self, parent):
        # Save/Cancel buttons at bottom
        button_cont = lv.obj(parent)
        button_cont.set_size(lv.pct(100), mpos.ui.pct_of_display_height(20))
        button_cont.remove_flag(lv.obj.FLAG.SCROLLABLE)
        button_cont.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        button_cont.set_style_border_width(0, 0)

        save_button = lv.button(button_cont)
        save_button.set_size(mpos.ui.pct_of_display_width(25), lv.SIZE_CONTENT)
        save_button.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        save_button.add_event_cb(lambda e: self.save_and_close(), lv.EVENT.CLICKED, None)
        save_label = lv.label(save_button)
        save_label.set_text("Save")
        save_label.center()

        cancel_button = lv.button(button_cont)
        cancel_button.set_size(mpos.ui.pct_of_display_width(25), lv.SIZE_CONTENT)
        cancel_button.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        cancel_button.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
        cancel_label = lv.label(cancel_button)
        cancel_label.set_text("Cancel")
        cancel_label.center()

        erase_button = lv.button(button_cont)
        erase_button.set_size(mpos.ui.pct_of_display_width(25), lv.SIZE_CONTENT)
        erase_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        erase_button.add_event_cb(lambda e: self.erase_and_close(), lv.EVENT.CLICKED, None)
        erase_label = lv.label(erase_button)
        erase_label.set_text("Erase")
        erase_label.center()


    def create_basic_tab(self, tab, prefs):
        """Create Basic settings tab."""
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        tab.set_style_pad_all(1, 0)

        # Color Mode
        colormode = prefs.get_bool("colormode", False)
        checkbox, cont = self.create_checkbox(tab, "Color Mode (slower)", colormode, "colormode")
        self.ui_controls["colormode"] = checkbox

        # Resolution dropdown
        current_resolution = prefs.get_string("resolution", "320x240")
        resolution_idx = 0
        for idx, (_, value) in enumerate(self.resolutions):
            if value == current_resolution:
                resolution_idx = idx
                break

        dropdown, cont = self.create_dropdown(tab, "Resolution:", self.resolutions, resolution_idx, "resolution")
        self.ui_controls["resolution"] = dropdown

        # Brightness
        brightness = prefs.get_int("brightness", 0)
        slider, label, cont = self.create_slider(tab, "Brightness", -2, 2, brightness, "brightness")
        self.ui_controls["brightness"] = slider

        # Contrast
        contrast = prefs.get_int("contrast", 0)
        slider, label, cont = self.create_slider(tab, "Contrast", -2, 2, contrast, "contrast")
        self.ui_controls["contrast"] = slider

        # Saturation
        saturation = prefs.get_int("saturation", 0)
        slider, label, cont = self.create_slider(tab, "Saturation", -2, 2, saturation, "saturation")
        self.ui_controls["saturation"] = slider

        # Horizontal Mirror
        hmirror = prefs.get_bool("hmirror", False)
        checkbox, cont = self.create_checkbox(tab, "Horizontal Mirror", hmirror, "hmirror")
        self.ui_controls["hmirror"] = checkbox

        # Vertical Flip
        vflip = prefs.get_bool("vflip", True)
        checkbox, cont = self.create_checkbox(tab, "Vertical Flip", vflip, "vflip")
        self.ui_controls["vflip"] = checkbox

        self.add_buttons(tab)

    def create_advanced_tab(self, tab, prefs):
        """Create Advanced settings tab."""
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(1, 0)

        # Auto Exposure Control (master switch)
        exposure_ctrl = prefs.get_bool("exposure_ctrl", True)
        aec_checkbox, cont = self.create_checkbox(tab, "Auto Exposure", exposure_ctrl, "exposure_ctrl")
        self.ui_controls["exposure_ctrl"] = aec_checkbox

        # Manual Exposure Value (dependent)
        aec_value = prefs.get_int("aec_value", 300)
        me_slider, label, cont = self.create_slider(tab, "Manual Exposure", 0, 1200, aec_value, "aec_value")
        self.ui_controls["aec_value"] = me_slider

        # Auto Exposure Level (dependent)
        ae_level = prefs.get_int("ae_level", 0)
        ae_slider, label, cont = self.create_slider(tab, "Auto Exposure Level", -2, 2, ae_level, "ae_level")
        self.ui_controls["ae_level"] = ae_slider

        # Add dependency handler
        def exposure_ctrl_changed(e=None):
            is_auto = aec_checkbox.get_state() & lv.STATE.CHECKED
            if is_auto:
                me_slider.add_state(lv.STATE.DISABLED)
                me_slider.set_style_opa(128, 0)
                ae_slider.remove_state(lv.STATE.DISABLED)
                ae_slider.set_style_opa(255, 0)
            else:
                me_slider.remove_state(lv.STATE.DISABLED)
                me_slider.set_style_opa(255, 0)
                ae_slider.add_state(lv.STATE.DISABLED)
                ae_slider.set_style_opa(128, 0)

        aec_checkbox.add_event_cb(exposure_ctrl_changed, lv.EVENT.VALUE_CHANGED, None)
        exposure_ctrl_changed()

        # Night Mode (AEC2)
        aec2 = prefs.get_bool("aec2", False)
        checkbox, cont = self.create_checkbox(tab, "Night Mode (AEC2)", aec2, "aec2")
        self.ui_controls["aec2"] = checkbox

        # Auto Gain Control (master switch)
        gain_ctrl = prefs.get_bool("gain_ctrl", True)
        agc_checkbox, cont = self.create_checkbox(tab, "Auto Gain", gain_ctrl, "gain_ctrl")
        self.ui_controls["gain_ctrl"] = agc_checkbox

        # Manual Gain Value (dependent)
        agc_gain = prefs.get_int("agc_gain", 0)
        slider, label, cont = self.create_slider(tab, "Manual Gain", 0, 30, agc_gain, "agc_gain")
        self.ui_controls["agc_gain"] = slider

        if gain_ctrl:
            slider.add_state(lv.STATE.DISABLED)
            slider.set_style_opa(128, 0)

        def gain_ctrl_changed(e):
            is_auto = agc_checkbox.get_state() & lv.STATE.CHECKED
            gain_slider = self.ui_controls["agc_gain"]
            if is_auto:
                gain_slider.add_state(lv.STATE.DISABLED)
                gain_slider.set_style_opa(128, 0)
            else:
                gain_slider.remove_state(lv.STATE.DISABLED)
                gain_slider.set_style_opa(255, 0)

        agc_checkbox.add_event_cb(gain_ctrl_changed, lv.EVENT.VALUE_CHANGED, None)

        # Gain Ceiling
        gainceiling_options = [
            ("2X", 0), ("4X", 1), ("8X", 2), ("16X", 3),
            ("32X", 4), ("64X", 5), ("128X", 6)
        ]
        gainceiling = prefs.get_int("gainceiling", 0)
        dropdown, cont = self.create_dropdown(tab, "Gain Ceiling:", gainceiling_options, gainceiling, "gainceiling")
        self.ui_controls["gainceiling"] = dropdown

        # Auto White Balance (master switch)
        whitebal = prefs.get_bool("whitebal", True)
        wbcheckbox, cont = self.create_checkbox(tab, "Auto White Balance", whitebal, "whitebal")
        self.ui_controls["whitebal"] = wbcheckbox

        # White Balance Mode (dependent)
        wb_mode_options = [
            ("Auto", 0), ("Sunny", 1), ("Cloudy", 2), ("Office", 3), ("Home", 4)
        ]
        wb_mode = prefs.get_int("wb_mode", 0)
        dropdown, cont = self.create_dropdown(tab, "WB Mode:", wb_mode_options, wb_mode, "wb_mode")
        self.ui_controls["wb_mode"] = dropdown

        if whitebal:
            dropdown.add_state(lv.STATE.DISABLED)

        def whitebal_changed(e):
            is_auto = wbcheckbox.get_state() & lv.STATE.CHECKED
            wb_dropdown = self.ui_controls["wb_mode"]
            if is_auto:
                wb_dropdown.add_state(lv.STATE.DISABLED)
            else:
                wb_dropdown.remove_state(lv.STATE.DISABLED)

        wbcheckbox.add_event_cb(whitebal_changed, lv.EVENT.VALUE_CHANGED, None)

        # AWB Gain
        awb_gain = prefs.get_bool("awb_gain", True)
        checkbox, cont = self.create_checkbox(tab, "AWB Gain", awb_gain, "awb_gain")
        self.ui_controls["awb_gain"] = checkbox

        self.add_buttons(tab)

        # Special Effect
        special_effect_options = [
            ("None", 0), ("Negative", 1), ("Grayscale", 2),
            ("Reddish", 3), ("Greenish", 4), ("Blue", 5), ("Retro", 6)
        ]
        special_effect = prefs.get_int("special_effect", 0)
        dropdown, cont = self.create_dropdown(tab, "Special Effect:", special_effect_options,
                                              special_effect, "special_effect")
        self.ui_controls["special_effect"] = dropdown

    def create_expert_tab(self, tab, prefs):
        """Create Expert settings tab."""
        #tab.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(1, 0)

        # Note: Sensor detection isn't performed right now
        # For now, show sharpness/denoise with note
        supports_sharpness = True  # Assume yes

        # Sharpness
        sharpness = prefs.get_int("sharpness", 0)
        slider, label, cont = self.create_slider(tab, "Sharpness", -3, 3, sharpness, "sharpness")
        self.ui_controls["sharpness"] = slider

        if not supports_sharpness:
            slider.add_state(lv.STATE.DISABLED)
            slider.set_style_opa(128, 0)
            note = lv.label(cont)
            note.set_text("(Not available on this sensor)")
            note.set_style_text_color(lv.color_hex(0x808080), 0)
            note.align(lv.ALIGN.TOP_RIGHT, 0, 0)

        # Denoise
        denoise = prefs.get_int("denoise", 0)
        slider, label, cont = self.create_slider(tab, "Denoise", 0, 8, denoise, "denoise")
        self.ui_controls["denoise"] = slider

        if not supports_sharpness:
            slider.add_state(lv.STATE.DISABLED)
            slider.set_style_opa(128, 0)
            note = lv.label(cont)
            note.set_text("(Not available on this sensor)")
            note.set_style_text_color(lv.color_hex(0x808080), 0)
            note.align(lv.ALIGN.TOP_RIGHT, 0, 0)

        # JPEG Quality
        # Disabled because JPEG is not used right now
        #quality = prefs.get_int("quality", 85)
        #slider, label, cont = self.create_slider(tab, "JPEG Quality", 0, 100, quality, "quality")
        #self.ui_controls["quality"] = slider

        # Color Bar
        colorbar = prefs.get_bool("colorbar", False)
        checkbox, cont = self.create_checkbox(tab, "Color Bar Test", colorbar, "colorbar")
        self.ui_controls["colorbar"] = checkbox

        # DCW Mode
        dcw = prefs.get_bool("dcw", True)
        checkbox, cont = self.create_checkbox(tab, "Downsize Crop Window", dcw, "dcw")
        self.ui_controls["dcw"] = checkbox

        # Black Point Compensation
        bpc = prefs.get_bool("bpc", False)
        checkbox, cont = self.create_checkbox(tab, "Black Point Compensation", bpc, "bpc")
        self.ui_controls["bpc"] = checkbox

        # White Point Compensation
        wpc = prefs.get_bool("wpc", True)
        checkbox, cont = self.create_checkbox(tab, "White Point Compensation", wpc, "wpc")
        self.ui_controls["wpc"] = checkbox

        # Raw Gamma Mode
        raw_gma = prefs.get_bool("raw_gma", True)
        checkbox, cont = self.create_checkbox(tab, "Raw Gamma Mode", raw_gma, "raw_gma")
        self.ui_controls["raw_gma"] = checkbox

        # Lens Correction
        lenc = prefs.get_bool("lenc", True)
        checkbox, cont = self.create_checkbox(tab, "Lens Correction", lenc, "lenc")
        self.ui_controls["lenc"] = checkbox

        self.add_buttons(tab)

    def create_raw_tab(self, tab, prefs):
        tab.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tab.set_style_pad_all(0, 0)

        # This would be nice but does not provide adequate resolution:
        #startX, label, cont = self.create_slider(tab, "startX", 0, 2844, startX, "startX")

        startX = prefs.get_int("startX", self.startX_default)
        textarea, cont = self.create_textarea(tab, "startX", 0, 2844, startX, "startX")
        self.ui_controls["startX"] = textarea

        startY = prefs.get_int("startY", self.startY_default)
        textarea, cont = self.create_textarea(tab, "startY", 0, 2844, startY, "startY")
        self.ui_controls["startY"] = textarea

        endX = prefs.get_int("endX", self.endX_default)
        textarea, cont = self.create_textarea(tab, "endX", 0, 2844, endX, "endX")
        self.ui_controls["endX"] = textarea

        endY = prefs.get_int("endY", self.endY_default)
        textarea, cont = self.create_textarea(tab, "endY", 0, 2844, endY, "endY")
        self.ui_controls["endY"] = textarea

        offsetX = prefs.get_int("offsetX", self.offsetX_default)
        textarea, cont = self.create_textarea(tab, "offsetX", 0, 2844, offsetX, "offsetX")
        self.ui_controls["offsetX"] = textarea

        offsetY = prefs.get_int("offsetY", self.offsetY_default)
        textarea, cont = self.create_textarea(tab, "offsetY", 0, 2844, offsetY, "offsetY")
        self.ui_controls["offsetY"] = textarea

        totalX = prefs.get_int("totalX", self.totalX_default)
        textarea, cont = self.create_textarea(tab, "totalX", 0, 2844, totalX, "totalX")
        self.ui_controls["totalX"] = textarea

        totalY = prefs.get_int("totalY", self.totalY_default)
        textarea, cont = self.create_textarea(tab, "totalY", 0, 2844, totalY, "totalY")
        self.ui_controls["totalY"] = textarea

        outputX = prefs.get_int("outputX", self.outputX_default)
        textarea, cont = self.create_textarea(tab, "outputX", 0, 2844, outputX, "outputX")
        self.ui_controls["outputX"] = textarea

        outputY = prefs.get_int("outputY", self.outputY_default)
        textarea, cont = self.create_textarea(tab, "outputY", 0, 2844, outputY, "outputY")
        self.ui_controls["outputY"] = textarea

        scale = prefs.get_bool("scale", self.scale_default)
        checkbox, cont = self.create_checkbox(tab, "Scale?", scale, "scale")
        self.ui_controls["scale"] = checkbox

        binning = prefs.get_bool("binning", self.binning_default)
        checkbox, cont = self.create_checkbox(tab, "Binning?", binning, "binning")
        self.ui_controls["binning"] = checkbox

        self.add_buttons(tab)

    def erase_and_close(self):
        SharedPreferences("com.micropythonos.camera").edit().remove_all().commit()
        self.setResult(True, {"settings_changed": True})
        self.finish()

    def save_and_close(self):
        """Save all settings to SharedPreferences and return result."""
        prefs = SharedPreferences("com.micropythonos.camera")
        editor = prefs.edit()

        # Save all UI control values
        for pref_key, control in self.ui_controls.items():
            print(f"saving {pref_key} with {control}")
            control_id = id(control)
            metadata = self.control_metadata.get(control_id, {})

            if isinstance(control, lv.slider):
                value = control.get_value()
                editor.put_int(pref_key, value)
            elif isinstance(control, lv.checkbox):
                is_checked = control.get_state() & lv.STATE.CHECKED
                editor.put_bool(pref_key, bool(is_checked))
            elif isinstance(control, lv.textarea):
                try:
                    value = int(control.get_text())
                    editor.put_int(pref_key, value)
                except Exception as e:
                    print(f"Error while trying to save {pref_key}: {e}")
            elif isinstance(control, lv.dropdown):
                selected_idx = control.get_selected()
                option_values = metadata.get("option_values", [])
                if pref_key == "resolution":
                    # Resolution stored as string
                    value = option_values[selected_idx]
                    editor.put_string(pref_key, value)
                else:
                    # Other dropdowns store integer enum values
                    value = option_values[selected_idx]
                    editor.put_int(pref_key, value)

        editor.commit()
        print("Camera settings saved")

        # Return success result
        self.setResult(True, {"settings_changed": True})
        self.finish()
