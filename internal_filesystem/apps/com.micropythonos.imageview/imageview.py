import gc
import os
import lvgl as lv

from mpos import Activity, WidgetAnimator, DisplayMetrics, Intent

class ImageView(Activity):

    imagedir = "data/images"
    images = []
    image_nr = None
    image_timer = None
    fullscreen = False
    stopping = False

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
        self.label = lv.label(screen)
        self.label.set_text(f"Loading images from\n{self.imagedir}")
        self.label.align(lv.ALIGN.TOP_LEFT, 4, 4)
        screen_width = DisplayMetrics.width()
        if screen_width:
            self.label.set_width(screen_width - 112)
        else:
            self.label.set_width(lv.pct(60))

        self.open_button = lv.button(screen)
        self.open_button.set_size(100, 42)
        self.open_button.align(lv.ALIGN.TOP_RIGHT, -4, 4)
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

        # Invisible button, just for defocusing the prev and next buttons:
        self.play_button = lv.button(screen)
        self.play_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.play_button.set_style_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        #self.play_button.add_flag(lv.obj.FLAG.HIDDEN)
        #self.play_button.add_event_cb(lambda e: self.unfocus_if_not_fullscreen(),lv.EVENT.FOCUSED,None)
        #self.play_button.set_style_shadow_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        #self.play_button.add_event_cb(lambda e: self.play(),lv.EVENT.CLICKED,None)
        #play_label = lv.label(self.play_button)
        #play_label.set_text(lv.SYMBOL.PLAY)
        self.delete_button = lv.button(screen)
        self.delete_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.delete_button.add_event_cb(lambda e: self.delete_image(),lv.EVENT.CLICKED,None)
        delete_label = lv.label(self.delete_button)
        delete_label.set_text(lv.SYMBOL.TRASH)
        delete_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        self.next_button = lv.button(screen)
        self.next_button.align(lv.ALIGN.BOTTOM_RIGHT,0,0)
        #self.next_button.add_event_cb(self.print_events, lv.EVENT.ALL, None)
        self.next_button.add_event_cb(lambda e: self.show_next_image_if_fullscreen(),lv.EVENT.FOCUSED,None)
        self.next_button.add_event_cb(lambda e: self.show_next_image(),lv.EVENT.CLICKED,None)
        next_label = lv.label(self.next_button)
        next_label.set_text(lv.SYMBOL.RIGHT)
        next_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        #screen.add_event_cb(self.print_events, lv.EVENT.ALL, None)
        self.setContentView(screen)

    def onResume(self, screen):
        self.stopping = False
        self.images.clear()

        # If we were launched via "Open With", display just that one file.
        incoming_filename = self.getIntent().extras.get("filename") or self.getIntent().data
        if incoming_filename:
            self.label.set_text(incoming_filename)
            self.images = [incoming_filename]
            self.image_nr = None
            self.show_next_image()
            return

        self.images = self._collect_images_from_dir(self.imagedir)
        if len(self.images) == 0:
            self.no_image_mode()
        else:
            # Begin with one image:
            self.show_next_image()
            self.stop_fullscreen()

    def onStop(self, screen):
        print("ImageView stopping")
        self.stopping = True
        if self.image_timer:
            print("ImageView: deleting image_timer")
            self.image_timer.delete()

    def no_image_mode(self):
        self.label.set_text(f"No images found in {self.imagedir}...")
        WidgetAnimator.smooth_hide(self.prev_button)
        WidgetAnimator.smooth_hide(self.delete_button)
        WidgetAnimator.smooth_hide(self.next_button)

    def _open_file_clicked(self, event):
        intent = Intent(
            action="pick_file",
            extras={"start_dir": self.imagedir, "path_pattern": [".jpg", ".jpeg", ".png", ".raw"]},
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
        )

    def _collect_images_from_dir(self, path):
        images = []
        try:
            for item in os.listdir(path):
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
        print("playing...")
        if self.fullscreen:
            self.fullscreen = False
            self.stop_fullscreen()
        else:
            self.fullscreen = True
            self.start_fullscreen()
        self.scale_image()

    def stop_fullscreen(self):
        print("stopping fullscreen")
        WidgetAnimator.smooth_show(self.label)
        WidgetAnimator.smooth_show(self.open_button)
        WidgetAnimator.smooth_show(self.prev_button)
        WidgetAnimator.smooth_show(self.delete_button)
        #WidgetAnimator.smooth_show(self.play_button)
        self.play_button.add_flag(lv.obj.FLAG.HIDDEN) # make it not accepting focus
        WidgetAnimator.smooth_show(self.next_button)

    def start_fullscreen(self):
        print("starting fullscreen")
        WidgetAnimator.smooth_hide(self.label)
        WidgetAnimator.smooth_hide(self.open_button)
        WidgetAnimator.smooth_hide(self.prev_button, hide=False)
        WidgetAnimator.smooth_hide(self.delete_button, hide=False)
        #WidgetAnimator.smooth_hide(self.play_button, hide=False)
        self.play_button.remove_flag(lv.obj.FLAG.HIDDEN) # make it accepting focus
        WidgetAnimator.smooth_hide(self.next_button, hide=False)
        self.unfocus() # focus on the invisible center button, not previous or next

    def show_prev_image_if_fullscreen(self, event=None):
        if self.stopping: # closing the window results in a focus shift, which can trigger the next action in fullscreen
            return
        if self.fullscreen:
            self.unfocus()
            self.show_prev_image()

    def show_next_image_if_fullscreen(self, event=None):
        if self.stopping: # closing the window results in a focus shift, which can trigger the next action in fullscreen
            return
        if self.fullscreen:
            self.unfocus()
            self.show_next_image()

    def unfocus(self):
        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: imageview.py could not get default focus group")
            return
        focused = focusgroup.get_focused()
        if focused:
            print(f"got focus button: {focused}")
            #focused.remove_state(lv.STATE.FOCUSED) # this doesn't seem to work to remove focus
            print("checking which button is focused")
            if focused == self.next_button:
                print("next is focused")
                focusgroup.focus_prev()
            elif focused == self.prev_button:
                print("prev is focused")
                focusgroup.focus_next()
            else:
                print("focus isn't on next or previous, leaving it...")

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
