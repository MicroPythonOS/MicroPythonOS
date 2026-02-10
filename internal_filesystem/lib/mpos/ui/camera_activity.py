import lvgl as lv
import time

try:
    import webcam
except Exception as e:
    print(f"Info: could not import webcam module: {e}")

from ..time import epoch_seconds
from .camera_settings import CameraSettingsActivity
from ..camera_manager import CameraManager
from .. import ui as mpos_ui
from ..app.activity import Activity

class CameraActivity(Activity):

    PACKAGE = "com.micropythonos.camera"
    CONFIGFILE = "config.json"
    SCANQR_CONFIG = "config_scanqr_mode.json"

    button_width = 75
    button_height = 50

    STATUS_NO_CAMERA = "No camera found."
    STATUS_SEARCHING_QR = "Searching QR codes...\n\nHold still and try varying scan distance (10-25cm) and make the QR code big (4-12cm). Ensure proper lighting."
    STATUS_FOUND_QR = "Found QR, trying to decode... hold still..."

    cam = None
    current_cam_buffer = None # Holds the current memoryview to prevent garba
    width = None
    height = None
    colormode = False

    image_dsc = None
    scanqr_mode = False
    scanqr_intent = False
    use_webcam = False
    capture_timer = None

    prefs = None # regular prefs
    scanqr_prefs = None # qr code scanning prefs
    
    # Widgets:
    main_screen = None
    image = None
    qr_label = None
    qr_button = None
    snap_button = None
    status_label = None
    status_label_cont = None

    def onCreate(self):
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(1, lv.PART.MAIN)
        self.main_screen.set_style_border_width(0, lv.PART.MAIN)
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
        settings_button.align_to(close_button, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        settings_label = lv.label(settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.center()
        settings_button.add_event_cb(lambda e: self.open_settings(),lv.EVENT.CLICKED,None)
        #self.zoom_button = lv.button(self.main_screen)
        #self.zoom_button.set_size(self.button_width, self.button_height)
        #self.zoom_button.align(lv.ALIGN.RIGHT_MID, 0, self.button_height + 5)
        #self.zoom_button.add_event_cb(self.zoom_button_click,lv.EVENT.CLICKED,None)
        #zoom_label = lv.label(self.zoom_button)
        #zoom_label.set_text("Z")
        #zoom_label.center()
        self.qr_button = lv.button(self.main_screen)
        self.qr_button.set_size(self.button_width, self.button_height)
        self.qr_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.qr_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.qr_button.add_event_cb(self.qr_button_click,lv.EVENT.CLICKED,None)
        self.qr_label = lv.label(self.qr_button)
        self.qr_label.set_text(lv.SYMBOL.EYE_OPEN)
        self.qr_label.center()

        self.snap_button = lv.button(self.main_screen)
        self.snap_button.set_size(self.button_width, self.button_height)
        self.snap_button.align_to(self.qr_button, lv.ALIGN.OUT_TOP_MID, 0, -10)
        self.snap_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.snap_button.add_event_cb(self.snap_button_click,lv.EVENT.CLICKED,None)
        snap_label = lv.label(self.snap_button)
        snap_label.set_text(lv.SYMBOL.OK)
        snap_label.center()


        self.status_label_cont = lv.obj(self.main_screen)
        width = mpos_ui.DisplayMetrics.pct_of_width(70)
        height = mpos_ui.DisplayMetrics.pct_of_width(60)
        self.status_label_cont.set_size(width,height)
        center_w = round((mpos_ui.DisplayMetrics.pct_of_width(100) - self.button_width - 5 - width)/2)
        center_h = round((mpos_ui.DisplayMetrics.pct_of_height(100) - height)/2)
        self.status_label_cont.set_pos(center_w,center_h)
        self.status_label_cont.set_style_bg_color(lv.color_white(), lv.PART.MAIN)
        self.status_label_cont.set_style_bg_opa(66, lv.PART.MAIN)
        self.status_label_cont.set_style_border_width(0, lv.PART.MAIN)
        self.status_label = lv.label(self.status_label_cont)
        self.status_label.set_text(self.STATUS_NO_CAMERA)
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(100))
        self.status_label.center()
        self.setContentView(self.main_screen)
    
    def onResume(self, screen):
        self.scanqr_intent = self.getIntent().extras.get("scanqr_intent")
        self.status_label_cont.add_flag(lv.obj.FLAG.HIDDEN)
        if self.scanqr_mode or self.scanqr_intent:
            self.start_qr_decoding()
            if not self.cam and self.scanqr_mode:
                self.status_label.set_text(self.STATUS_NO_CAMERA)
                # leave it open so the user can read the error and maybe open the settings
        else:
            self.load_settings_cached()
            self.start_cam()
            self.qr_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.snap_button.remove_flag(lv.obj.FLAG.HIDDEN)

    def onPause(self, screen):
        print("camera app backgrounded, cleaning up...")
        self.stop_cam()
        print("camera app cleanup done.")

    def start_cam(self):
        # Init camera:
        self.cam = CameraManager.get_cameras()[0].init(self.width, self.height, self.colormode)
        if self.cam:
            # Apply saved camera settings, only for internal camera for now:
            self.apply_camera_settings(self.scanqr_prefs if self.scanqr_mode else self.prefs, self.cam, self.use_webcam) # needs to be done AFTER the camera is initialized
        else:
            print("camera app: no internal camera found, trying webcam on /dev/video0")
            try:
                # Initialize webcam with desired resolution directly
                print(f"Initializing webcam at {self.width}x{self.height}")
                self.cam = webcam.init("/dev/video0", width=self.width, height=self.height)
                self.use_webcam = True
            except Exception as e:
                print(f"camera app: webcam exception: {e}")
        # Start refreshing:
        if self.cam:
            print("Camera app initialized, continuing...")
            self.update_preview_image()
            self.capture_timer = lv.timer_create(self.try_capture, 100, None)

    def stop_cam(self):
        if self.capture_timer:
            self.capture_timer.delete()
        if self.use_webcam:
            webcam.deinit(self.cam)
        elif self.cam:
            CameraManager.get_cameras()[0].deinit(self.cam)
        self.cam = None
        if self.image_dsc: # it's important to delete the image when stopping the camera, otherwise LVGL might try to display it and crash
            print("emptying self.current_cam_buffer...")
            self.image_dsc.data = None

    def load_settings_cached(self):
        from mpos import SharedPreferences
        if self.scanqr_mode:
            print("loading scanqr settings...")
            if not self.scanqr_prefs:
                # Merge common and scanqr-specific defaults
                scanqr_defaults = {}
                scanqr_defaults.update(CameraSettingsActivity.COMMON_DEFAULTS)
                scanqr_defaults.update(CameraSettingsActivity.SCANQR_DEFAULTS)
                self.scanqr_prefs = SharedPreferences(
                    self.PACKAGE,
                    filename=self.SCANQR_CONFIG,
                    defaults=scanqr_defaults
                )
            # Defaults come from constructor, no need to pass them here
            self.width = self.scanqr_prefs.get_int("resolution_width")
            self.height = self.scanqr_prefs.get_int("resolution_height")
            self.colormode = self.scanqr_prefs.get_bool("colormode")
        else:
            if not self.prefs:
                # Merge common and normal-specific defaults
                normal_defaults = {}
                normal_defaults.update(CameraSettingsActivity.COMMON_DEFAULTS)
                normal_defaults.update(CameraSettingsActivity.NORMAL_DEFAULTS)
                self.prefs = SharedPreferences(self.PACKAGE, defaults=normal_defaults)
            # Defaults come from constructor, no need to pass them here
            self.width = self.prefs.get_int("resolution_width")
            self.height = self.prefs.get_int("resolution_height")
            self.colormode = self.prefs.get_bool("colormode")

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
            result = None
            before = time.ticks_ms()
            import qrdecode
            if self.colormode:
                result = qrdecode.qrdecode_rgb565(self.current_cam_buffer, self.width, self.height)
            else:
                result = qrdecode.qrdecode(self.current_cam_buffer, self.width, self.height)
            after = time.ticks_ms()
            print(f"qrdecode took {after-before}ms")
        except ValueError as e:
            print("QR ValueError: ", e)
            self.status_label.set_text(self.STATUS_SEARCHING_QR)
        except TypeError as e:
            print("QR TypeError: ", e)
            self.status_label.set_text(self.STATUS_FOUND_QR)
        except Exception as e:
            print("QR got other error: ", e)
        #result = bytearray("INSERT_TEST_QR_DATA_HERE", "utf-8")
        if result is None:
            return
        result = self.remove_bom(result)
        result = self.print_qr_buffer(result)
        print(f"QR decoding found: {result}")
        if self.scanqr_intent:
            self.stop_qr_decoding(activate_non_qr_mode=False)
            self.setResult(True, result)
            self.finish()
        else:
            self.status_label.set_text(result) # in the future, the status_label text should be copy-paste-able
            self.stop_qr_decoding()

    def snap_button_click(self, e):
        print("Taking picture...")
        # Would be nice to check that there's enough free space here, and show an error if not...
        import os
        path = "data/images"
        try:
            os.mkdir("data")
        except OSError:
            pass
        try:
            os.mkdir(path)
        except OSError:
            pass
        if self.current_cam_buffer is None:
            print("snap_button_click: won't save empty image")
            return
        # Check enough free space?
        stat = os.statvfs("data/images")
        free_space = stat[0] * stat[3]
        size_needed = len(self.current_cam_buffer)
        print(f"Free space {free_space} and size needed {size_needed}")
        if free_space < size_needed:
            self.status_label.set_text(f"Free storage space is {free_space}, need {size_needed}, not saving...")
            self.status_label_cont.remove_flag(lv.obj.FLAG.HIDDEN)
            return
        colorname = "RGB565" if self.colormode else "GRAY"
        filename=f"{path}/picture_{epoch_seconds()}_{self.width}x{self.height}_{colorname}.raw"
        try:
            with open(filename, 'wb') as f:
                f.write(self.current_cam_buffer) # This takes around 17 seconds to store 921600 bytes, so ~50KB/s, so would be nice to show some progress bar
            report = f"Successfully wrote image to {filename}"
            print(report)
            self.status_label.set_text(report)
            self.status_label_cont.remove_flag(lv.obj.FLAG.HIDDEN)
        except OSError as e:
            print(f"Error writing to file: {e}")
    
    def start_qr_decoding(self):
        print("Activating live QR decoding...")
        self.scanqr_mode = True
        oldwidth = self.width
        oldheight = self.height
        oldcolormode = self.colormode
        # Activate QR mode settings
        self.load_settings_cached()
        # Check if it's necessary to restart the camera:
        if not self.cam or self.width != oldwidth or self.height != oldheight or self.colormode != oldcolormode:
            if self.cam:
                self.stop_cam()
            self.start_cam()
        self.qr_label.set_text(lv.SYMBOL.EYE_CLOSE)
        self.status_label_cont.remove_flag(lv.obj.FLAG.HIDDEN)
        self.status_label.set_text(self.STATUS_SEARCHING_QR)
    
    def stop_qr_decoding(self, activate_non_qr_mode=True):
        print("Deactivating live QR decoding...")
        self.scanqr_mode = False
        self.qr_label.set_text(lv.SYMBOL.EYE_OPEN)
        status_label_text = self.status_label.get_text()
        if status_label_text in (self.STATUS_NO_CAMERA, self.STATUS_SEARCHING_QR, self.STATUS_FOUND_QR): # if it found a QR code, leave it
            self.status_label_cont.add_flag(lv.obj.FLAG.HIDDEN)
        # Check if it's necessary to restart the camera:
        if activate_non_qr_mode is False:
            return
        # Instead of checking if any setting changed, just reload and restart the camera:
        self.load_settings_cached()
        self.stop_cam()
        self.start_cam()
    
    def qr_button_click(self, e):
        if not self.scanqr_mode:
            self.start_qr_decoding()
        else:
            self.stop_qr_decoding()

    def open_settings(self):
        from ..content.intent import Intent
        intent = Intent(activity_class=CameraSettingsActivity, extras={"prefs": self.prefs if not self.scanqr_mode else self.scanqr_prefs, "use_webcam": self.use_webcam, "scanqr_mode": self.scanqr_mode})
        self.startActivity(intent)

    def try_capture(self, event):
        try:
            if self.use_webcam and self.cam:
                self.current_cam_buffer = webcam.capture_frame(self.cam, "rgb565" if self.colormode else "grayscale")
            elif self.cam and self.cam.frame_available():
                self.current_cam_buffer = self.cam.capture()
        except Exception as e:
            print(f"Camera capture exception: {e}")
            return
        # Display the image:
        self.image_dsc.data = self.current_cam_buffer
        #self.image.invalidate() # does not work so do this:
        self.image.set_src(self.image_dsc)
        if self.scanqr_mode:
            self.qrdecode_one()
        if not self.use_webcam and self.cam:
            self.cam.free_buffer()  # After QR decoding, free the old buffer, otherwise the camera doesn't provide a new one

    def print_qr_buffer(self, buffer):
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
    def remove_bom(self, buffer):
        bom = b'\xEF\xBB\xBF'
        if buffer.startswith(bom):
            return buffer[3:]
        return buffer
    
    
    def apply_camera_settings(self, prefs, cam, use_webcam):
        """Apply all saved camera settings to the camera.
    
        Only applies settings when use_webcam is False (ESP32 camera).
        Settings are applied in dependency order (master switches before dependent values).
    
        Args:
            cam: Camera object
            use_webcam: Boolean indicating if using webcam
        """
        if not cam or use_webcam:
            print("apply_camera_settings: Skipping (no camera or webcam mode)")
            return
    
        try:
            # Basic image adjustments
            brightness = prefs.get_int("brightness")
            cam.set_brightness(brightness)
    
            contrast = prefs.get_int("contrast")
            cam.set_contrast(contrast)
    
            saturation = prefs.get_int("saturation")
            cam.set_saturation(saturation)

            # Orientation
            hmirror = prefs.get_bool("hmirror")
            cam.set_hmirror(hmirror)

            vflip = prefs.get_bool("vflip")
            cam.set_vflip(vflip)

            # Special effect
            special_effect = prefs.get_int("special_effect")
            cam.set_special_effect(special_effect)

            # Exposure control (apply master switch first, then manual value)
            exposure_ctrl = prefs.get_bool("exposure_ctrl")
            cam.set_exposure_ctrl(exposure_ctrl)

            if not exposure_ctrl:
                aec_value = prefs.get_int("aec_value")
                cam.set_aec_value(aec_value)

            # Mode-specific default comes from constructor
            ae_level = prefs.get_int("ae_level")
            cam.set_ae_level(ae_level)

            aec2 = prefs.get_bool("aec2")
            cam.set_aec2(aec2)
    
            # Gain control (apply master switch first, then manual value)
            gain_ctrl = prefs.get_bool("gain_ctrl")
            cam.set_gain_ctrl(gain_ctrl)

            if not gain_ctrl:
                agc_gain = prefs.get_int("agc_gain")
                cam.set_agc_gain(agc_gain)

            gainceiling = prefs.get_int("gainceiling")
            cam.set_gainceiling(gainceiling)

            # White balance (apply master switch first, then mode)
            whitebal = prefs.get_bool("whitebal")
            cam.set_whitebal(whitebal)

            if not whitebal:
                wb_mode = prefs.get_int("wb_mode")
                cam.set_wb_mode(wb_mode)

            awb_gain = prefs.get_bool("awb_gain")
            cam.set_awb_gain(awb_gain)
    
            # Sensor-specific settings (try/except for unsupported sensors)
            try:
                sharpness = prefs.get_int("sharpness")
                cam.set_sharpness(sharpness)
            except:
                pass  # Not supported on OV2640?

            try:
                denoise = prefs.get_int("denoise")
                cam.set_denoise(denoise)
            except:
                pass  # Not supported on OV2640?

            # Advanced corrections
            colorbar = prefs.get_bool("colorbar")
            cam.set_colorbar(colorbar)

            dcw = prefs.get_bool("dcw")
            cam.set_dcw(dcw)

            bpc = prefs.get_bool("bpc")
            cam.set_bpc(bpc)

            wpc = prefs.get_bool("wpc")
            cam.set_wpc(wpc)

            # Mode-specific default comes from constructor
            raw_gma = prefs.get_bool("raw_gma")
            print(f"applying raw_gma: {raw_gma}")
            cam.set_raw_gma(raw_gma)

            lenc = prefs.get_bool("lenc")
            cam.set_lenc(lenc)
    
            # JPEG quality (only relevant for JPEG format)
            #try:
            #    quality = prefs.get_int("quality", 85)
            #    cam.set_quality(quality)
            #except:
            #    pass  # Not in JPEG mode
    
            print("Camera settings applied successfully")
    
        except Exception as e:
            print(f"Error applying camera settings: {e}")


"""
    def zoom_button_click_unused(self, e):
        print("zooming...")
        if self.use_webcam:
            print("zoom_button_click is not supported for webcam")
            return
        if self.cam:
            startX = self.prefs.get_int("startX", CameraSettingsActivity.startX_default)
            startY = self.prefs.get_int("startX", CameraSettingsActivity.startY_default)
            endX = self.prefs.get_int("startX", CameraSettingsActivity.endX_default)
            endY = self.prefs.get_int("startX", CameraSettingsActivity.endY_default)
            offsetX = self.prefs.get_int("startX", CameraSettingsActivity.offsetX_default)
            offsetY = self.prefs.get_int("startX", CameraSettingsActivity.offsetY_default)
            totalX = self.prefs.get_int("startX", CameraSettingsActivity.totalX_default)
            totalY = self.prefs.get_int("startX", CameraSettingsActivity.totalY_default)
            outputX = self.prefs.get_int("startX", CameraSettingsActivity.outputX_default)
            outputY = self.prefs.get_int("startX", CameraSettingsActivity.outputY_default)
            scale = self.prefs.get_bool("scale", CameraSettingsActivity.scale_default)
            binning = self.prefs.get_bool("binning", CameraSettingsActivity.binning_default)
            result = self.cam.set_res_raw(startX,startY,endX,endY,offsetX,offsetY,totalX,totalY,outputX,outputY,scale,binning)
            print(f"self.cam.set_res_raw returned {result}")
"""
