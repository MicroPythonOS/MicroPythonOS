from mpos.apps import Activity
import mpos.ui

class FileManager(Activity):

    # Widgets:
    file_explorer = None

    def onCreate(self):
        #lv.log_register_print_cb(self.log_callback)
        screen = lv.obj()
        self.file_explorer = lv.file_explorer(screen)
        #self.file_explorer.set_root_path("M:data/images/")
        #self.file_explorer.explorer_open_dir('/')
        #self.file_explorer.explorer_open_dir('M:data/images/')
        #self.file_explorer.explorer_open_dir('M:/')
        self.file_explorer.explorer_open_dir('M:/') # unicode error on desktop, maybe reoccurence of https://github.com/lvgl-micropython/lvgl_micropython/issues/398 https://github.com/lvgl-micropython/lvgl_micropython/pull/399
        #self.file_explorer.explorer_open_dir('M:data/images/')
        #self.file_explorer.explorer_open_dir('P:.') # POSIX works on desktop, fs_driver doesn't because it doesn't have dir_open, dir_read, dir_close
        #self.file_explorer.explorer_open_dir('P:/tmp') # POSIX works, fs_driver doesn't because it doesn't have dir_open, dir_read, dir_close
        #file_explorer.explorer_open_dir('S:/')
        #self.file_explorer.set_size(lv.pct(100), lv.pct(100))
        #file_explorer.set_mode(lv.FILE_EXPLORER.MODE.DEFAULT)  # Default browsing mode
        #file_explorer.set_sort(lv.FILE_EXPLORER.SORT.NAME_ASC)  # Sort by name, ascending
        self.file_explorer.align(lv.ALIGN.CENTER, 0, 0)
        # Attach event callback
        self.file_explorer.add_event_cb(self.file_explorer_event_cb, lv.EVENT.ALL, None)
        self.setContentView(screen)

    def file_explorer_event_cb(self, event):
        event_code = event.get_code()
        # Ignore:	
        # =======
        # 2: PRESSING
        # 19: HIT_TEST
        # COVER_CHECK
        # 24: REFR_EXT_DRAW_SIZE
        # DRAW_MAIN
        # DRAW_MAIN_BEGIN
        # DRAW_MAIN_END
        # DRAW_POST
        # DRAW_POST_BEGIN
        # DRAW_POST_END
        # GET_SELF_SIZE
        # 47 STYLE CHANGED
        if event_code not in [2,19,23,24,25,26,27,28,29,30,47,49]:
            name = mpos.ui.get_event_name(event_code)
            print(f"file_explorer_event_cb {event_code} with name {name}")
            if event_code == lv.EVENT.VALUE_CHANGED:
                path = self.file_explorer.explorer_get_current_path()
                file = self.file_explorer.explorer_get_selected_file_name()
                print(f"Selected: {path}{file}")

    # Custom log callback to capture FPS
    def log_callback(self, level, log_str):
        # Convert log_str to string if it's a bytes object
        log_str = log_str.decode() if isinstance(log_str, bytes) else log_str
        print(f"Level: {level}, Log: {log_str}")
