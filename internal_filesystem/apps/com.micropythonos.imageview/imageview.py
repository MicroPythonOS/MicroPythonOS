import logging
import gc
import os
import lvgl as lv

from mpos import Activity, WidgetAnimator, DisplayMetrics, Intent, add_focus_border

logger = logging.getLogger(__name__)

class ImageView(Activity):

    imagedir = "data/images"
    images = []
    image_nr = None
    fullscreen = False

    # Widgets
    image = None
    current_image_dsc = None  # Track current image descriptor
    open_button = None

    def onCreate(self):
        screen = lv.obj()
        screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.image = lv.image(screen)
        self.image.center()
        self.image.add_flag(lv.obj.FLAG.CLICKABLE)
        self.image.add_event_cb(lambda e: self.toggle_fullscreen(),lv.EVENT.CLICKED,None)
        add_focus_border(self.image, 2)
        self.label = lv.label(screen)
        self.label.set_text(f"Loading images from\n{self.imagedir}")
        self.label.align(lv.ALIGN.TOP_LEFT, 4, 4)
        screen_width = DisplayMetrics.width()
        if screen_width:
            self.label.set_width(screen_width - 112)
        else:
            self.label.set_width(lv.pct(60))

        self.open_button = lv.button(screen)
        self.open_button.set_size(DisplayMetrics.pct_of_width(25), DisplayMetrics.pct_of_height(15))
        self.open_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        self.open_button.add_event_cb(self._open_file_clicked, lv.EVENT.CLICKED, None)
        open_label = lv.label(self.open_button)
        open_label.set_text("Open file...")
        open_label.center()

        self.prev_button = lv.button(screen)
        self.prev_button.align(lv.ALIGN.BOTTOM_LEFT,0,0)
        self.prev_button.add_event_cb(lambda e: self.show_prev_image_if_fullscreen(),lv.EVENT.FOCUSED,None)
        self.prev_button.add_event_cb(lambda e: self.show_prev_image(),lv.EVENT.CLICKED,None)
        prev_label = lv.label(self.prev_button)
        prev_label.set_text(lv.SYMBOL.LEFT)
        prev_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        self.delete_button = lv.button(screen)
        self.delete_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.delete_button.add_event_cb(lambda e: self.delete_image(),lv.EVENT.CLICKED,None)
        delete_label = lv.label(self.delete_button)
        delete_label.set_text(lv.SYMBOL.TRASH)
        delete_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        self.next_button = lv.button(screen)
        self.next_button.align(lv.ALIGN.BOTTOM_RIGHT,0,0)
        self.next_button.add_event_cb(lambda e: self.show_next_image_if_fullscreen(),lv.EVENT.FOCUSED,None)
        self.next_button.add_event_cb(lambda e: self.show_next_image(),lv.EVENT.CLICKED,None)
        next_label = lv.label(self.next_button)
        next_label.set_text(lv.SYMBOL.RIGHT)
        next_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        self.setContentView(screen)

    def onResume(self, screen):
        self.images.clear()

        # If we were launched via "Open With", start at that file but still
        # allow browsing the rest of the folder with next/previous.
        incoming_filename = self.getIntent().extras.get("filename") or self.getIntent().data
        if incoming_filename:
            image_dir = self.imagedir
            slash = incoming_filename.rfind("/")
            if slash >= 0:
                image_dir = incoming_filename[:slash]
            self.images = self._collect_images_from_dir(image_dir)
            try:
                self.image_nr = self.images.index(incoming_filename)
            except ValueError:
                self.images = [incoming_filename]
                self.image_nr = 0
            self.show_image(incoming_filename)
            self.stop_fullscreen()
            return

        self.images = self._collect_images_from_dir(self.imagedir)
        if len(self.images) == 0:
            self.no_image_mode()
        else:
            # Begin with one image:
            self.show_next_image()
            self.stop_fullscreen()

    def no_image_mode(self):
        self.label.set_text(f"No images found in {self.imagedir}...")
        WidgetAnimator.smooth_hide(self.prev_button)
        WidgetAnimator.smooth_hide(self.delete_button)
        WidgetAnimator.smooth_hide(self.next_button)

    def _open_file_clicked(self, event):
        intent = Intent(
            action="pick_file",
            extras={"start_dir": self.imagedir, "path_pattern": [".jpg", ".jpeg", ".png", ".raw", ".bmp"]},
        )
        self.startActivityForResult(intent, self._on_file_picked)

    def _on_file_picked(self, result):
        if not result or not result.get("result_code"):
            return
        paths = result.get("data", {}).get("paths", [])
        images = []
        for path in paths:
            if path.endswith("/"):
                images.extend(self._collect_images_from_dir(path))
            else:
                try:
                    size = os.stat(path)[6]
                    if size > 10 * 1024 * 1024:
                        print(f"Skipping file of size {size}")
                        continue
                except OSError:
                    pass
                if self._is_image_file(path):
                    images.append(path)
        if images:
            self.images = images
            self.image_nr = None
            self.show_next_image()
            self.stop_fullscreen()

    def _is_image_file(self, filename):
        lowercase = filename.lower()
        return (
            lowercase.endswith(".jpg")
            or lowercase.endswith(".jpeg")
            or lowercase.endswith(".png")
            or lowercase.endswith(".raw")
            or lowercase.endswith(".bmp")
        )

    def _collect_images_from_dir(self, path):
        images = []
        try:
            # FAT32 (SD card) rejects directory paths ending with '/' for os.listdir().
            for item in os.listdir(path.rstrip("/") or "/"):
                print(item)
                if not self._is_image_file(item):
                    continue
                fullname = path.rstrip("/") + "/" + item
                size = os.stat(fullname)[6]
                print(f"size: {size}")
                if size > 10 * 1024 * 1024:
                    print(f"Skipping file of size {size}")
                    continue
                images.append(fullname)
        except Exception as e:
            print(f"ImageView encountered exception for {path}: {e}")
        images.sort()
        return images

    def show_prev_image(self, event=None):
        print("showing previous image...")
        if len(self.images) < 1:
            self.no_image_mode()
            return
        if self.image_nr is None or self.image_nr == 0:
            self.image_nr = len(self.images) - 1
        else:
            self.image_nr = self.image_nr - 1
        name = self.images[self.image_nr]
        print(f"show_prev_image showing {name}")
        self.show_image(name)

    def toggle_fullscreen(self, event=None):
        if self.fullscreen:
            self.stop_fullscreen()
        else:
            self.start_fullscreen()

    def stop_fullscreen(self):
        self.fullscreen = False
        print("stopping fullscreen")
        WidgetAnimator.smooth_show(self.label)
        WidgetAnimator.smooth_show(self.open_button)
        WidgetAnimator.smooth_show(self.prev_button)
        WidgetAnimator.smooth_show(self.delete_button)
        WidgetAnimator.smooth_show(self.next_button)
        self.scale_image()
        lv.group_focus_obj(self.image) # especially focus on the delete button

    def start_fullscreen(self):
        print("starting fullscreen")
        self.fullscreen = True
        WidgetAnimator.smooth_hide(self.label)
        WidgetAnimator.smooth_hide(self.open_button)
        WidgetAnimator.smooth_hide(self.prev_button, hide=False)
        WidgetAnimator.smooth_hide(self.delete_button, hide=False)
        WidgetAnimator.smooth_hide(self.next_button, hide=False)
        self.scale_image()
        lv.group_focus_obj(self.delete_button)

    def show_prev_image_if_fullscreen(self, event=None):
        if self.fullscreen:
            lv.group_focus_obj(self.delete_button)
            self.show_prev_image()

    def show_next_image_if_fullscreen(self, event=None):
        if self.fullscreen:
            lv.group_focus_obj(self.delete_button)
            self.show_next_image()

    def show_next_image(self, event=None):
        print("showing next image...")
        if len(self.images) < 1:
            self.no_image_mode()
            return
        if self.image_nr is None or self.image_nr  >= len(self.images) - 1:
            self.image_nr = 0
        else:
            self.image_nr = self.image_nr + 1
        name = self.images[self.image_nr]
        print(f"show_next_image showing {name}")
        self.show_image(name)

    def delete_image(self, event=None):
        if self.fullscreen:
            self.stop_fullscreen()
            return
        filename = self.images[self.image_nr]
        try:
            os.remove(filename)
            self.clear_image()
            self.label.set_text(f"Deleted\n{filename}")
            del self.images[self.image_nr]
        except Exception as e:
            print(f"Error deleting {filename}: {e}")

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

    def show_image(self, name):
        self.current_image = name
        try:
            self.label.set_text(name)
            self.clear_image()
            self.image.set_src(f"M:{name}")

            if name.lower().endswith(".raw"):
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
                if color_format == "GRAY":
                    cf = lv.COLOR_FORMAT.L8
                    stride = width
                elif color_format != "RGB565":
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
            self.scale_image()
        except OSError as e:
            print(f"show_image got exception: {e}")

    def scale_image(self):
        if self.fullscreen:
            pct = 100
        else:
            pct = 70
        lvgl_w = DisplayMetrics.pct_of_width(pct)
        lvgl_h = DisplayMetrics.pct_of_height(pct)
        print(f"scaling to size: {lvgl_w}x{lvgl_h}")
        header = lv.image_header_t()
        self.image.decoder_get_info(self.image.get_src(), header)
        image_w = header.w
        image_h = header.h
        if image_w == 0 or image_h == 0:
            print("WARNING: original image has width or height 0, returning!")
            return
        print(f"the real image has size: {header.w}x{header.h}")
        scale_factor_w = round(lvgl_w * 256 / image_w)
        scale_factor_h = round(lvgl_h * 256 / image_h)
        print(f"scale_factors: {scale_factor_w},{scale_factor_h}")
        self.image.set_size(lvgl_w, lvgl_h)
        self.image.set_scale(min(scale_factor_w,scale_factor_h))
        print(f"after set_scale, the LVGL image has size: {self.image.get_width()}x{self.image.get_height()}")

    def clear_image(self):
        self.image.set_src(None)
        gc.collect()
