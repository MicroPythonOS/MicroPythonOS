import time
import _thread

from mpos.apps import Activity
import mpos.ui

class Benchmark(Activity):

    fps_buffer = [0] # Buffer to store FPS
    bird_x = 100
    bird_y = 0
    image_w = 296
    image_h = 240
    image_target_w = 160
    image_target_h = 120
    image_x = image_w
    image_y = 0
    
    #lvgl_w = 160
    #lvgl_h = 120

    # Widgets:
    canvas = None
    image = None

    def onCreate(self):
        screen = lv.obj()
        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)
        screen.add_event_cb(self.key_cb, lv.EVENT.KEY, None)
        self.image = lv.image(screen)
        self.load_image("data/images/screenshots/snapshot_296x240_RGB565.raw")
        scale_factor_w = round(self.image_target_w * 256 / self.image_w)
        self.image.set_scale(scale_factor_w)
        self.spinner = lv.spinner(screen)
        self.spinner.set_size(16, 16)
        self.setContentView(screen)

    def onResume(self, screen):
        lv.log_register_print_cb(self.log_callback)
        mpos.ui.th.add_event_cb(self.update_frame, 1)

    def onPause(self, screen):
        mpos.ui.th.remove_event_cb(self.update_frame)
        lv.log_register_print_cb(None)

    def key_cb(self, event):
        key = event.get_key()
        #print(f"got key {key}")

        if key == lv.KEY.UP:
            self.image_target_w += 20
            scale_factor_w = round(self.image_target_w * 256 / self.image_w)
            self.image.set_scale(scale_factor_w)
        elif key == lv.KEY.DOWN:
            self.image_target_w -= 20
            scale_factor_w = round(self.image_target_w * 256 / self.image_w)
            self.image.set_scale(scale_factor_w)
        elif key == lv.KEY.LEFT:
            self.bird_x -= 10
        elif key == lv.KEY.RIGHT:
            self.bird_x += 10
        elif key == lv.KEY.ENTER:
            self.bird_y -= 25

    def extract_dimensions_and_format(self, filename):
        # Split the filename by '_'
        parts = filename.split('_')
        # Get the color format (last part before '.raw')
        color_format = parts[-1].split('.')[0]  # e.g., "RGB565"
        # Get the resolution (second-to-last part)
        resolution = parts[-2]  # e.g., "240x240"
        # Split resolution by 'x' to get width and height
        width, height = map(int, resolution.split('x'))
        return width, height, color_format.upper()

    def load_image(self, name):
        if not name.lower().endswith(".raw"):
            self.image.remove_flag(lv.obj.FLAG.HIDDEN)
            self.image.set_src(f"M:{name}")
        else:
            f = open(name, 'rb')
            image_data = f.read()
            print(f"loaded {len(image_data)} bytes from .raw file")
            f.close()
            try:
                width, height, color_format = self.extract_dimensions_and_format(name)
            except ValueError as e:
                print(f"Warning: could not extract dimensions and format from raw image: {e}")
                return
            print(f"Raw image has width: {width}, Height: {height}, Color Format: {color_format}")
            stride = width * 2
            cf = lv.COLOR_FORMAT.RGB565
            if color_format != "RGB565":
                print(f"WARNING: unknown color format {color_format}, assuming RGB565...")
            self.current_image_dsc = lv.image_dsc_t({
                "header": {
                    "magic": lv.IMAGE_HEADER_MAGIC,
                    "w": width,
                    "h": height,
                    "stride": stride,
                    "cf": cf
                },
                'data_size': len(image_data),
                'data': image_data
            })
            self.image.set_src(self.current_image_dsc)

    def touch_cb(self, event):
        event_code=event.get_code()
        #print(f"lv_event_t: code={event_code}")
        if event_code == lv.EVENT.PRESSING:
            self.runall()

    # Custom log callback to capture FPS
    def log_callback(self,level, log_str):
        # Convert log_str to string if it's a bytes object
        log_str = log_str.decode() if isinstance(log_str, bytes) else log_str
        # Optional: Print for debugging
        #print(f"Level: {level}, Log: {log_str}")
        # Log message format: "sysmon: 25 FPS (refr_cnt: 8 | redraw_cnt: 1), ..."
        if "sysmon:" in log_str and "FPS" in log_str:
            try:
                # Extract FPS value (e.g., "25" from "sysmon: 25 FPS ...")
                fps_part = log_str.split("FPS")[0].split("sysmon:")[1].strip()
                fps = int(fps_part)
                print("Current FPS:", fps)
                self.fps_buffer[0] = fps
            except (IndexError, ValueError):
                pass


    def update_frame(self, a, b):
        self.spinner.set_pos(self.bird_x, self.bird_y)
        self.image.set_x(self.image_x)
        self.image_x -= 1
        if self.image_x < (-self.image_target_w*2):
            self.image_x = self.image_w
        self.bird_y += 1
        if self.bird_y > self.image_h:
            self.bird_y = 0

