# This code grabs images from the camera in RGB565 format (2 bytes per pixel)
# and sends that to the QR decoder if QR decoding is enabled.
# The QR decoder then converts the RGB565 to grayscale, as that's what quirc operates on.
# It would be slightly more efficient to capture the images from the camera in L8/grayscale format,
# or in YUV format and discarding the U and V planes, but then the image will be gray (not great UX)
# and the performance impact of converting RGB565 to grayscale is probably minimal anyway.

import lvgl as lv

try:
    import webcam
except Exception as e:
    print(f"Info: could not import webcam module: {e}")

from mpos.apps import Activity
from mpos.config import SharedPreferences
from mpos.content.intent import Intent
import mpos.time

class CameraApp(Activity):

    button_width = 40
    button_height = 40
    width = 320
    height = 240

    status_label_text = "No camera found."
    status_label_text_searching = "Searching QR codes...\n\nHold still and try varying scan distance (10-25cm) and QR size (4-12cm). Ensure proper lighting."
    status_label_text_found = "Decoding QR..."

    cam = None
    current_cam_buffer = None # Holds the current memoryview to prevent garbage collection

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

    def load_resolution_preference(self):
        """Load resolution preference from SharedPreferences and update width/height."""
        prefs = SharedPreferences("com.micropythonos.camera")
        resolution_str = prefs.get_string("resolution", "320x240")
        try:
            width_str, height_str = resolution_str.split('x')
            self.width = int(width_str)
            self.height = int(height_str)
            print(f"Camera resolution loaded: {self.width}x{self.height}")
        except Exception as e:
            print(f"Error parsing resolution '{resolution_str}': {e}, using default 320x240")
            self.width = 320
            self.height = 240

    def onCreate(self):
        self.load_resolution_preference()
        self.scanqr_mode = self.getIntent().extras.get("scanqr_mode")
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(0, 0)
        self.main_screen.set_style_border_width(0, 0)
        self.main_screen.set_size(lv.pct(100), lv.pct(100))
        self.main_screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        # Initialize LVGL image widget
        self.create_preview_image()
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
        settings_button.align(lv.ALIGN.TOP_RIGHT, 0, self.button_height + 10)
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
        self.cam = init_internal_cam(self.width, self.height)
        if self.cam:
            self.image.set_rotation(900) # internal camera is rotated 90 degrees
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
            self.set_image_size()
            self.capture_timer = lv.timer_create(self.try_capture, 100, None)
            self.status_label_cont.add_flag(lv.obj.FLAG.HIDDEN)
            if self.scanqr_mode:
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

    def set_image_size(self):
        disp = lv.display_get_default()
        target_h = disp.get_vertical_resolution()
        target_w = disp.get_horizontal_resolution() - self.button_width - 5 # leave 5px for border
        if target_w == self.width and target_h == self.height:
            print("Target width and height are the same as native image, no scaling required.")
            return
        print(f"scaling to size: {target_w}x{target_h}")
        scale_factor_w = round(target_w * 256 / self.width)
        scale_factor_h = round(target_h * 256 / self.height)
        print(f"scale_factors: {scale_factor_w},{scale_factor_h}")
        self.image.set_size(target_w, target_h)
        #self.image.set_scale(max(scale_factor_w,scale_factor_h)) # fills the entire screen but cuts off borders
        self.image.set_scale(min(scale_factor_w,scale_factor_h))

    def create_preview_image(self):
        self.image = lv.image(self.main_screen)
        self.image.align(lv.ALIGN.LEFT_MID, 0, 0)
        # Create image descriptor once
        self.image_dsc = lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": self.width,
                "h": self.height,
                "stride": self.width * 2,
                "cf": lv.COLOR_FORMAT.RGB565
                #"cf": lv.COLOR_FORMAT.L8
            },
            'data_size': self.width * self.height * 2,
            'data': None # Will be updated per frame
        })
        self.image.set_src(self.image_dsc)
        #self.image.set_size(160, 120)


    def qrdecode_one(self):
        try:
            import qrdecode
            import utime
            before = utime.ticks_ms()
            result = qrdecode.qrdecode_rgb565(self.current_cam_buffer, self.width, self.height)
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
            filename=f"data/images/camera_capture_{mpos.time.epoch_seconds()}_{self.width}x{self.height}_RGB565.raw"
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

    def open_settings(self):
        self.image_dsc.data = None
        self.current_cam_buffer = None
        """Launch the camera settings activity."""
        intent = Intent(activity_class=CameraSettingsActivity)
        self.startActivityForResult(intent, self.handle_settings_result)

    def handle_settings_result(self, result):
        print(f"handle_settings_result: {result}")
        """Handle result from settings activity."""
        if result.get("result_code") == True:
            print("Settings changed, reloading resolution...")
            # Reload resolution preference
            self.load_resolution_preference()

            # CRITICAL: Pause capture timer to prevent race conditions during reconfiguration
            if self.capture_timer:
                self.capture_timer.delete()
                self.capture_timer = None
                print("Capture timer paused")

            # Clear stale data pointer to prevent segfault during LVGL rendering
            self.image_dsc.data = None
            self.current_cam_buffer = None
            print("Image data cleared")

            # Update image descriptor with new dimensions
            # Note: image_dsc is an LVGL struct, use attribute access not dictionary access
            self.image_dsc.header.w = self.width
            self.image_dsc.header.h = self.height
            self.image_dsc.header.stride = self.width * 2
            self.image_dsc.data_size = self.width * self.height * 2
            print(f"Image descriptor updated to {self.width}x{self.height}")

            # Reconfigure camera if active
            if self.cam:
                if self.use_webcam:
                    print(f"Reconfiguring webcam to {self.width}x{self.height}")
                    # Reconfigure webcam resolution (input and output are the same)
                    webcam.reconfigure(self.cam, width=self.width, height=self.height)
                    # Resume capture timer for webcam
                    self.capture_timer = lv.timer_create(self.try_capture, 100, None)
                    print("Webcam reconfigured, capture timer resumed")
                else:
                    # For internal camera, need to reinitialize
                    print(f"Reinitializing internal camera to {self.width}x{self.height}")
                    self.cam.deinit()
                    self.cam = init_internal_cam(self.width, self.height)
                    if self.cam:
                        self.capture_timer = lv.timer_create(self.try_capture, 100, None)
                        print("Internal camera reinitialized, capture timer resumed")
                    else:
                        print("ERROR: Failed to reinitialize camera after resolution change")
                        self.status_label.set_text("Failed to reinitialize camera.\nPlease restart the app.")
                        self.status_label_cont.remove_flag(lv.obj.FLAG.HIDDEN)
                        return  # Don't continue if camera failed

                self.set_image_size()

    def try_capture(self, event):
        #print("capturing camera frame")
        try:
            if self.use_webcam:
                self.current_cam_buffer = webcam.capture_frame(self.cam, "rgb565")
            elif self.cam.frame_available():
                self.current_cam_buffer = self.cam.capture()

            if self.current_cam_buffer and len(self.current_cam_buffer):
                # Defensive check: verify buffer size matches expected dimensions
                expected_size = self.width * self.height * 2  # RGB565 = 2 bytes per pixel
                actual_size = len(self.current_cam_buffer)

                if actual_size == expected_size:
                    self.image_dsc.data = self.current_cam_buffer
                    #image.invalidate() # does not work so do this:
                    self.image.set_src(self.image_dsc)
                    if not self.use_webcam:
                        self.cam.free_buffer()  # Free the old buffer
                    if self.keepliveqrdecoding:
                        self.qrdecode_one()
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
            #(128, 128): FrameSize.R128X128, it's actually FrameSize.R128x128 but let's ignore it to be safe
            (176, 144): FrameSize.QCIF,
            (240, 176): FrameSize.HQVGA,
            (240, 240): FrameSize.R240X240,
            (320, 240): FrameSize.QVGA,
            (320, 320): FrameSize.R320X320,
            (400, 296): FrameSize.CIF,
            (480, 320): FrameSize.HVGA,
            (640, 480): FrameSize.VGA,
            (800, 600): FrameSize.SVGA,
            (1024, 768): FrameSize.XGA,
            (1280, 720): FrameSize.HD,
            (1280, 1024): FrameSize.SXGA,
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
                    pixel_format=PixelFormat.RGB565,
                    frame_size=frame_size,
                    grab_mode=GrabMode.LATEST
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


class CameraSettingsActivity(Activity):
    """Settings activity for camera resolution configuration."""

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

    # Resolution options for internal camera (ESP32) - all available FrameSize options
    ESP32_RESOLUTIONS = [
        ("96x96", "96x96"),
        ("160x120", "160x120"),
        ("128x128", "128x128"),
        ("176x144", "176x144"),
        ("240x176", "240x176"),
        ("240x240", "240x240"),  # Default
        ("320x240", "320x240"),
        ("320x320", "320x320"),
        ("400x296", "400x296"),
        ("480x320", "480x320"),
        ("640x480", "640x480"),
        ("800x600", "800x600"),
        ("1024x768", "1024x768"),
        ("1280x720", "1280x720"),
        ("1280x1024", "1280x1024"),
        ("1600x1200", "1600x1200"),
        ("1920x1080", "1920x1080"),
    ]

    dropdown = None
    current_resolution = None

    def onCreate(self):
        # Load preferences
        prefs = SharedPreferences("com.micropythonos.camera")
        self.current_resolution = prefs.get_string("resolution", "320x240")

        # Create main screen
        screen = lv.obj()
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_style_pad_all(10, 0)

        # Title
        title = lv.label(screen)
        title.set_text("Camera Settings")
        title.align(lv.ALIGN.TOP_MID, 0, 10)

        # Resolution label
        resolution_label = lv.label(screen)
        resolution_label.set_text("Resolution:")
        resolution_label.align(lv.ALIGN.TOP_LEFT, 0, 50)

        # Detect if we're on desktop or ESP32 based on available modules
        try:
            import webcam
            resolutions = self.WEBCAM_RESOLUTIONS
            print("Using webcam resolutions")
        except:
            resolutions = self.ESP32_RESOLUTIONS
            print("Using ESP32 camera resolutions")
	
        # Create dropdown
        self.dropdown = lv.dropdown(screen)
        self.dropdown.set_size(200, 40)
        self.dropdown.align(lv.ALIGN.TOP_LEFT, 0, 80)

        # Build dropdown options string
        options_str = "\n".join([label for label, _ in resolutions])
        self.dropdown.set_options(options_str)

        # Set current selection
        for idx, (label, value) in enumerate(resolutions):
            if value == self.current_resolution:
                self.dropdown.set_selected(idx)
                break

        # Save button
        save_button = lv.button(screen)
        save_button.set_size(100, 50)
        save_button.align(lv.ALIGN.BOTTOM_MID, -60, -10)
        save_button.add_event_cb(lambda e: self.save_and_close(resolutions), lv.EVENT.CLICKED, None)
        save_label = lv.label(save_button)
        save_label.set_text("Save")
        save_label.center()

        # Cancel button
        cancel_button = lv.button(screen)
        cancel_button.set_size(100, 50)
        cancel_button.align(lv.ALIGN.BOTTOM_MID, 60, -10)
        cancel_button.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
        cancel_label = lv.label(cancel_button)
        cancel_label.set_text("Cancel")
        cancel_label.center()

        self.setContentView(screen)

    def save_and_close(self, resolutions):
        """Save selected resolution and return result."""
        selected_idx = self.dropdown.get_selected()
        _, new_resolution = resolutions[selected_idx]

        # Save to preferences
        prefs = SharedPreferences("com.micropythonos.camera")
        editor = prefs.edit()
        editor.put_string("resolution", new_resolution)
        editor.commit()

        print(f"Camera resolution saved: {new_resolution}")

        # Return success result
        self.setResult(True, {"resolution": new_resolution})
        self.finish()
