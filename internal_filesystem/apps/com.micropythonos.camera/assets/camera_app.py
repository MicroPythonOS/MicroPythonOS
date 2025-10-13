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
import mpos.time

class CameraApp(Activity):

    width = 240
    height = 240

    status_label_text = "No camera found."
    status_label_text_searching = "Searching QR codes...\n\nHold still and make them big!\n10cm for simple QR codes,\n20cm for complex."
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
    qr_label = None
    qr_button = None
    snap_button = None
    status_label = None
    status_label_cont = None

    def onCreate(self):
        self.scanqr_mode = self.getIntent().extras.get("scanqr_mode")
        main_screen = lv.obj()
        main_screen.set_style_pad_all(0, 0)
        main_screen.set_style_border_width(0, 0)
        main_screen.set_size(lv.pct(100), lv.pct(100))
        main_screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        close_button = lv.button(main_screen)
        close_button.set_size(60,60)
        close_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        close_label = lv.label(close_button)
        close_label.set_text(lv.SYMBOL.CLOSE)
        close_label.center()
        close_button.add_event_cb(lambda e: self.finish(),lv.EVENT.CLICKED,None)
        self.snap_button = lv.button(main_screen)
        self.snap_button.set_size(60, 60)
        self.snap_button.align(lv.ALIGN.RIGHT_MID, 0, 0)
        self.snap_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.snap_button.add_event_cb(self.snap_button_click,lv.EVENT.CLICKED,None)
        snap_label = lv.label(self.snap_button)
        snap_label.set_text(lv.SYMBOL.OK)
        snap_label.center()
        self.qr_button = lv.button(main_screen)
        self.qr_button.set_size(60, 60)
        self.qr_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.qr_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.qr_button.add_event_cb(self.qr_button_click,lv.EVENT.CLICKED,None)
        self.qr_label = lv.label(self.qr_button)
        self.qr_label.set_text(lv.SYMBOL.EYE_OPEN)
        self.qr_label.center()
        # Initialize LVGL image widget
        self.image = lv.image(main_screen)
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
        self.status_label_cont = lv.obj(main_screen)
        self.status_label_cont.set_size(lv.pct(66),lv.pct(60))
        self.status_label_cont.align(lv.ALIGN.LEFT_MID, lv.pct(5), 0)
        self.status_label_cont.set_style_bg_color(lv.color_white(), 0)
        self.status_label_cont.set_style_bg_opa(66, 0)
        self.status_label_cont.set_style_border_width(0, 0)
        self.status_label = lv.label(self.status_label_cont)
        self.status_label.set_text("No camera found.")
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(100))
        self.status_label.center()
        self.setContentView(main_screen)
    
    def onResume(self, screen):
        self.cam = init_internal_cam()
        if self.cam:
            self.image.set_rotation(900) # internal camera is rotated 90 degrees
        else:
            print("camera app: no internal camera found, trying webcam on /dev/video0")
            try:
                self.cam = webcam.init("/dev/video0")
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


    def onStop(self, screen):
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
        target_h = mpos.ui.vertical_resolution
        target_w = target_h
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
    
    def try_capture(self, event):
        #print("capturing camera frame")
        try:
            if self.use_webcam:
                self.current_cam_buffer = webcam.capture_frame(self.cam, "rgb565")
            elif self.cam.frame_available():
                self.current_cam_buffer = self.cam.capture()
            if self.current_cam_buffer and len(self.current_cam_buffer):
                self.image_dsc.data = self.current_cam_buffer
                #image.invalidate() # does not work so do this:
                self.image.set_src(self.image_dsc)
                if not self.use_webcam:
                    self.cam.free_buffer()  # Free the old buffer
                if self.keepliveqrdecoding:
                    self.qrdecode_one()
        except Exception as e:
            print(f"Camera capture exception: {e}")


# Non-class functions:
def init_internal_cam():
    try:
        from camera import Camera, GrabMode, PixelFormat, FrameSize, GainCeiling
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
            #pixel_format=PixelFormat.GRAYSCALE,
            frame_size=FrameSize.R240X240,
            grab_mode=GrabMode.LATEST 
        )
        #cam.init() automatically done when creating the Camera()
        #cam.reconfigure(frame_size=FrameSize.HVGA)
        #frame_size=FrameSize.HVGA, # 480x320
        #frame_size=FrameSize.QVGA, # 320x240
        #frame_size=FrameSize.QQVGA # 160x120
        cam.set_vflip(True)
        return cam
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
