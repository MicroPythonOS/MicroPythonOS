import gc
import os

from mpos.apps import Activity
import mpos.ui
import mpos.ui.anim

class ImageView(Activity):

    imagedir = "data/images"
    images = []
    image_nr = None
    image_timer = None
    fullscreen = False
    stopping = False

    # Widgets
    image = None
    gif = None
    current_image_dsc = None  # Track current image descriptor

    def onCreate(self):
        screen = lv.obj()
        self.image = lv.image(screen)
        self.image.center()
        self.image.add_flag(lv.obj.FLAG.CLICKABLE)
        self.image.add_event_cb(lambda e: self.toggle_fullscreen(),lv.EVENT.CLICKED,None)
        self.gif = lv.gif(screen)
        self.gif.center()
        self.gif.add_flag(lv.obj.FLAG.CLICKABLE)
        self.gif.add_flag(lv.obj.FLAG.HIDDEN)
        self.gif.add_event_cb(lambda e: self.toggle_fullscreen(),lv.EVENT.CLICKED,None)
        self.label = lv.label(screen)
        self.label.set_text(f"Loading images from\n{self.imagedir}")
        self.label.align(lv.ALIGN.TOP_MID,0,0)
        self.prev_button = lv.button(screen)
        self.prev_button.align(lv.ALIGN.BOTTOM_LEFT,0,0)
        self.prev_button.add_event_cb(lambda e: self.show_prev_image_if_fullscreen(),lv.EVENT.FOCUSED,None)
        self.prev_button.add_event_cb(lambda e: self.show_prev_image(),lv.EVENT.CLICKED,None)
        prev_label = lv.label(self.prev_button)
        prev_label.set_text(lv.SYMBOL.LEFT)
        self.play_button = lv.button(screen)
        self.play_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.play_button.set_style_opa(lv.OPA.TRANSP, 0)
        #self.play_button.add_flag(lv.obj.FLAG.HIDDEN)
        #self.play_button.add_event_cb(lambda e: self.unfocus_if_not_fullscreen(),lv.EVENT.FOCUSED,None)
        #self.play_button.set_style_shadow_opa(lv.OPA.TRANSP, 0)
        #self.play_button.add_event_cb(lambda e: self.play(),lv.EVENT.CLICKED,None)
        #play_label = lv.label(self.play_button)
        #play_label.set_text(lv.SYMBOL.PLAY)
        self.next_button = lv.button(screen)
        self.next_button.align(lv.ALIGN.BOTTOM_RIGHT,0,0)
        #self.next_button.add_event_cb(self.print_events, lv.EVENT.ALL, None)
        self.next_button.add_event_cb(lambda e: self.show_next_image_if_fullscreen(),lv.EVENT.FOCUSED,None)
        self.next_button.add_event_cb(lambda e: self.show_next_image(),lv.EVENT.CLICKED,None)
        next_label = lv.label(self.next_button)
        next_label.set_text(lv.SYMBOL.RIGHT)
        #screen.add_event_cb(self.print_events, lv.EVENT.ALL, None)
        self.setContentView(screen)

    def onResume(self, screen):
        self.stopping = False
        self.images.clear()
        try:
            for item in os.listdir(self.imagedir):
                print(item)
                lowercase = item.lower()
                if not (lowercase.endswith(".jpg") or lowercase.endswith(".jpeg") or lowercase.endswith(".png") or lowercase.endswith(".raw") or lowercase.endswith(".gif")):
                    continue
                fullname = f"{self.imagedir}/{item}"
                size = os.stat(fullname)[6]
                print(f"size: {size}")
                if size > 10 * 1024*1024:
                    print(f"Skipping file of size {size}")
                    continue
                self.images.append(fullname)

            self.images.sort()
            # Begin with one image:
            self.show_next_image()
            self.stop_fullscreen()
            #self.image_timer = lv.timer_create(self.show_next_image, 1000, None)
        except Exception as e:
            print(f"ImageView encountered exception for {self.imagedir}: {e}")

    def onStop(self, screen):
        print("ImageView stopping")
        self.stopping = True
        if self.image_timer:
            print("ImageView: deleting image_timer")
            self.image_timer.delete()

    def show_prev_image(self, event=None):
        print("showing previous image...")
        if len(self.images) < 1:
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
        mpos.ui.anim.smooth_show(self.label)
        mpos.ui.anim.smooth_show(self.prev_button)
        #mpos.ui.anim.smooth_show(self.play_button)
        self.play_button.add_flag(lv.obj.FLAG.HIDDEN) # make it not accepting focus
        mpos.ui.anim.smooth_show(self.next_button)

    def start_fullscreen(self):
        print("starting fullscreen")
        mpos.ui.anim.smooth_hide(self.label)
        mpos.ui.anim.smooth_hide(self.prev_button, hide=False)
        #mpos.ui.anim.smooth_hide(self.play_button, hide=False)
        self.play_button.remove_flag(lv.obj.FLAG.HIDDEN) # make it accepting focus
        mpos.ui.anim.smooth_hide(self.next_button, hide=False)
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
        print("got focus group")
        # group.focus_obj(self.play_button) would be better but appears missing?!
        focused = focusgroup.get_focused()
        print("got focus button")
        #focused.remove_state(lv.STATE.FOCUSED) # this doesn't seem to work to remove focus
        if focused:
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
            return
        if self.image_nr is None or self.image_nr  >= len(self.images) - 1:
            self.image_nr = 0
        else:
            self.image_nr = self.image_nr + 1
        name = self.images[self.image_nr]
        print(f"show_next_image showing {name}")
        self.show_image(name)

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
        try:
            self.label.set_text(name)
            self.clear_image()
            if name.lower().endswith(".gif"):
                print("switching to gif mode...")
                self.image.add_flag(lv.obj.FLAG.HIDDEN)
                self.gif.remove_flag(lv.obj.FLAG.HIDDEN)
                self.gif.set_src(f"M:{name}")
            else:
                self.gif.add_flag(lv.obj.FLAG.HIDDEN)
                self.image.remove_flag(lv.obj.FLAG.HIDDEN)
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
                else:
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
            pct = 90
        lvgl_w = mpos.ui.pct_of_display_width(pct)
        lvgl_h = mpos.ui.pct_of_display_height(pct)
        print(f"scaling to size: {lvgl_w}x{lvgl_h}")
        header = lv.image_header_t()
        self.image.decoder_get_info(self.image.get_src(), header)
        image_w = header.w
        image_h = header.h
        if image_w == 0 or image_h == 0:
            return
        print(f"the real image has size: {header.w}x{header.h}")
        scale_factor_w = round(lvgl_w * 256 / image_w)
        scale_factor_h = round(lvgl_h * 256 / image_h)
        print(f"scale_factors: {scale_factor_w},{scale_factor_h}")
        self.image.set_size(lvgl_w, lvgl_h)
        #self.gif.set_size(lvgl_w, lvgl_h) doesn't seem to do anything. get_style_transform_scale_x/y works but then it needs get_style_translate_x/y
        #self.image.set_scale(max(scale_factor_w,scale_factor_h)) # fills the entire screen but cuts off borders
        self.image.set_scale(min(scale_factor_w,scale_factor_h))
        print(f"after set_scale, the LVGL image has size: {self.image.get_width()}x{self.image.get_height()}")


    def clear_image(self):
        """Clear current image or GIF source to free memory."""
        #if self.current_image_dsc:
        #    self.current_image_dsc = None  # Release reference to descriptor
        #self.image.set_src(None)  # Clear image source
        #self.gif.set_src(None)  # Clear GIF source causes crash!
        #self.gif.add_flag(lv.obj.FLAG.HIDDEN)
        #self.image.remove_flag(lv.obj.FLAG.HIDDEN)
        #lv.image_cache_invalidate_src(None)  # Invalidate LVGL image cache
        # These 2 are needed to enable infinite slides with just 10MB RAM:
        lv.image.cache_drop(None) # This helps a lot!
        gc.collect() # Force garbage collection seems to fix memory alloc issues!
