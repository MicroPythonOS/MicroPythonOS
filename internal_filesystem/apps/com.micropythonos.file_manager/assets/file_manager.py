import os
import lvgl as lv
from mpos import Activity, Intent, sdcard
from rename_activity import RenameActivity


class FileManager(Activity):

    _action_bar = None
    _cancel_btn = None
    _selected_path = None
    _current_path = None
    _list = None
    _path_label = None
    _suppress_btn = None
    _highlighted_btn = None
    _highlighted_text = None

    def onCreate(self):
        sdcard.mount_with_optional_format("/sdcard")
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        self._path_label = lv.label(screen)
        self._path_label.set_width(lv.pct(100))
        self._path_label.set_style_pad_all(6, lv.PART.MAIN)

        self._list = lv.list(screen)
        self._list.set_size(lv.pct(100), lv.pct(100))

        self._populate_dir(".")
        self.setContentView(screen)

    def onResume(self, screen):
        sdcard.mount_with_optional_format("/sdcard")

    def _populate_dir(self, path):
        self._dismiss_action_bar()
        self._clear_highlight()
        self._list.clean()
        path = path.rstrip("/") + "/"
        self._current_path = path
        self._path_label.set_text("  " + path)

        if path != "/":
            parent = "/".join(path.rstrip("/").split("/")[:-1]) + "/"
            btn = self._list.add_button(None, "< Back")
            btn.add_event_cb(lambda e, p=parent: self._populate_dir(p), lv.EVENT.CLICKED, None)

        try:
            items = os.listdir(path)
        except OSError:
            return

        dirs = []
        files = []
        for item in items:
            full = path + item
            try:
                if os.stat(full)[0] & 0x4000:
                    dirs.append(item)
                else:
                    files.append(item)
            except OSError:
                files.append(item)

        dirs.sort()
        files.sort()

        for d in dirs:
            fullpath = path + d + "/"
            btn = self._list.add_button(None, lv.SYMBOL.DIRECTORY + "  " + d)
            btn.add_event_cb(lambda e, p=fullpath: self._on_item_clicked(e, p, True), lv.EVENT.CLICKED, None)
            btn.add_event_cb(lambda e, p=fullpath: self._on_any_long_press(e, p), lv.EVENT.LONG_PRESSED, None)

        for f in files:
            fullpath = path + f
            btn = self._list.add_button(None, lv.SYMBOL.FILE + "  " + f)
            btn.add_event_cb(lambda e, p=fullpath: self._on_item_clicked(e, p, False), lv.EVENT.CLICKED, None)
            btn.add_event_cb(lambda e, p=fullpath: self._on_any_long_press(e, p), lv.EVENT.LONG_PRESSED, None)

    def _highlight_btn(self, btn):
        self._clear_highlight()
        self._highlighted_btn = btn
        self._highlighted_text = self._list.get_button_text(btn)
        self._list.set_button_text(btn, "> " + self._highlighted_text)

    def _clear_highlight(self):
        if self._highlighted_btn:
            self._list.set_button_text(self._highlighted_btn, self._highlighted_text)
            self._highlighted_btn = None
            self._highlighted_text = None

    def _on_any_long_press(self, e, path):
        btn = e.get_target_obj()
        self._suppress_btn = btn
        self._selected_path = path
        self._highlight_btn(btn)
        self._show_action_bar()
        print(f"FileManager: LONG_PRESSED on {path}")

    def _on_item_clicked(self, e, path, is_dir):
        target = e.get_target_obj()
        if target == self._suppress_btn:
            self._suppress_btn = None
            print(f"FileManager: CLICKED (suppressed) on {path}, focusing action bar")
            self._focus_action_bar()
            return
        if is_dir:
            print(f"FileManager: CLICKED -> navigating into {path}")
            self._populate_dir(path)
        else:
            print(f"FileManager: CLICKED on file {path} (no action)")

    def _focus_action_bar(self):
        if not self._cancel_btn:
            return
        lv.group_focus_obj(self._cancel_btn)

    def _show_action_bar(self):
        self._dismiss_action_bar()
        screen = lv.screen_active()
        bar = lv.obj(screen)
        bar.add_flag(lv.obj.FLAG.FLOATING)
        bar.set_size(lv.pct(100), 60)
        bar.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        bar.set_style_bg_color(lv.color_hex(0x444444), lv.PART.MAIN)
        bar.set_style_pad_all(8, lv.PART.MAIN)
        bar.set_flex_flow(lv.FLEX_FLOW.ROW)
        bar.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        delete_btn = lv.button(bar)
        lv.label(delete_btn).set_text("Delete")
        delete_btn.add_event_cb(lambda e: self._delete_selected(), lv.EVENT.CLICKED, None)

        rename_btn = lv.button(bar)
        lv.label(rename_btn).set_text("Rename")
        rename_btn.add_event_cb(lambda e: self._show_rename_screen(), lv.EVENT.CLICKED, None)

        cancel_btn = lv.button(bar)
        lv.label(cancel_btn).set_text("Cancel")
        cancel_btn.add_event_cb(lambda e: self._dismiss_action_bar(), lv.EVENT.CLICKED, None)

        self._cancel_btn = cancel_btn
        group = lv.group_get_default()
        group.add_obj(delete_btn)
        group.add_obj(rename_btn)
        group.add_obj(cancel_btn)

        self._action_bar = bar

    def _dismiss_action_bar(self):
        self._clear_highlight()
        if self._action_bar:
            self._action_bar.delete()
            self._action_bar = None
            self._cancel_btn = None

    def _delete_selected(self):
        self._dismiss_action_bar()
        path = self._selected_path
        name = path.rstrip("/").split("/")[-1]
        mbox = lv.msgbox(lv.layer_top())
        mbox.add_title("Delete")
        mbox.add_text(f"Delete {name}?")
        cancel = mbox.add_footer_button("Cancel")
        cancel.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CLICKED, None)
        delete = mbox.add_footer_button("Delete")
        delete.add_event_cb(lambda e: self._do_delete(mbox), lv.EVENT.CLICKED, None)
        close = mbox.add_close_button()
        close.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CLICKED, None)
        mbox.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CANCEL, None)

    def _do_delete(self, mbox):
        mbox.delete()
        path = self._selected_path
        try:
            os.remove(path)
        except OSError:
            try:
                os.rmdir(path.rstrip("/"))
            except OSError as e:
                print(f"FileManager: delete error {path}: {e}")
        print(f"FileManager: deleted {path}")
        self._populate_dir(self._current_path)

    def _show_rename_screen(self):
        self._dismiss_action_bar()
        intent = Intent(RenameActivity, extras={"path": self._selected_path})
        self.startActivityForResult(intent, self._on_rename_result)

    def _on_rename_result(self, result):
        if result and result.get("result_code"):
            print(f"FileManager: rename succeeded: {result.get('data', {})}")
        else:
            print(f"FileManager: rename cancelled or failed")
        self._populate_dir(self._current_path)
