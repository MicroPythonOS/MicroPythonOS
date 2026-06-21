import logging

logger = logging.getLogger(__name__)

import os
import lvgl as lv

from .. import sdcard
from ..content.app_manager import AppManager
from ..content.intent import Intent
from ..app.activity import Activity
from .display_metrics import DisplayMetrics
from .input_activity import InputActivity


class FileExplorerActivity(Activity):
    MODE_BROWSE = "browse"
    MODE_PICK = "pick"

    # Widgets
    _screen = None
    _path_label = None
    _list = None
    _action_bar = None
    _bottom_bar = None
    _cancel_btn = None
    _confirm_btn = None
    _new_file_btn = None
    _new_folder_btn = None
    _pending_create_kind = None
    _pending_rename_path = None

    # State
    _current_path = None
    _selected_paths = None
    _path_to_btn = None
    _selected_style = None
    _mode = None
    _path_pattern = None
    _start_dir = None

    _selected_path = None
    _suppress_btn = None
    _highlighted_btn = None
    _highlighted_text = None

    def onCreate(self):
        sdcard.mount_with_optional_format("/sdcard")
        self._mode = self.getIntent().extras.get("mode", self.MODE_BROWSE)
        self._start_dir = self.getIntent().extras.get("start_dir", ".")
        self._path_pattern = self.getIntent().extras.get("path_pattern", [])
        if isinstance(self._path_pattern, str):
            self._path_pattern = [self._path_pattern]
        self._selected_paths = []
        self._path_to_btn = {}

        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        header = lv.obj(screen)
        header.set_width(lv.pct(100))
        header.set_height(lv.SIZE_CONTENT)
        header.set_flex_flow(lv.FLEX_FLOW.ROW)
        header.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        header.set_style_pad_all(4, lv.PART.MAIN)

        self._path_label = lv.label(header)
        self._path_label.set_flex_grow(1)
        self._path_label.set_style_pad_all(6, lv.PART.MAIN)
        self._path_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)

        btn_size = DisplayMetrics.pct_of_width(10)

        self._new_file_btn = lv.button(header)
        self._new_file_btn.set_size(btn_size, btn_size)
        file_lbl = lv.label(self._new_file_btn)
        file_lbl.set_text(lv.SYMBOL.FILE)
        file_lbl.center()
        self._new_file_btn.add_event_cb(lambda e: self._prompt_create_name("file"), lv.EVENT.CLICKED, None)

        self._new_folder_btn = lv.button(header)
        self._new_folder_btn.set_size(btn_size, btn_size)
        folder_lbl = lv.label(self._new_folder_btn)
        folder_lbl.set_text(lv.SYMBOL.DIRECTORY)
        folder_lbl.center()
        self._new_folder_btn.add_event_cb(lambda e: self._prompt_create_name("folder"), lv.EVENT.CLICKED, None)

        if self._mode == self.MODE_PICK:
            self._new_file_btn.add_flag(lv.obj.FLAG.HIDDEN)
            self._new_folder_btn.add_flag(lv.obj.FLAG.HIDDEN)

        self._list = lv.list(screen)
        self._list.set_width(lv.pct(100))
        self._list.set_flex_grow(1)

        if self._mode == self.MODE_PICK:
            self._create_bottom_bar(screen)

        self._populate_dir(self._resolve_start_dir(self._start_dir))
        self.setContentView(screen)

    def onResume(self, screen):
        sdcard.mount_with_optional_format("/sdcard")

    def _resolve_start_dir(self, start_dir):
        path = start_dir.rstrip("/")
        if path == "":
            path = "/"
        while path:
            try:
                st = os.stat(path)
                if st[0] & 0x4000:
                    if __debug__: logger.debug("FileExplorer: resolved start_dir %s", path)
                    return path
            except OSError:
                pass
            if path == "/":
                break
            path = "/".join(path.rstrip("/").split("/")[:-1])
            if path == "":
                path = "/"
        return "/"

    def _create_bottom_bar(self, parent):
        bar = lv.obj(parent)
        bar.set_size(lv.pct(100), lv.SIZE_CONTENT)
        bar.set_style_pad_all(8, lv.PART.MAIN)
        bar.set_flex_flow(lv.FLEX_FLOW.ROW)
        bar.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        bar.set_style_bg_color(lv.color_hex(0x444444), lv.PART.MAIN)

        cancel_btn = lv.button(bar)
        lv.label(cancel_btn).set_text("Cancel")
        cancel_btn.add_event_cb(lambda e: self._cancel_pick(), lv.EVENT.CLICKED, None)

        confirm_btn = lv.button(bar)
        lv.label(confirm_btn).set_text("Confirm")
        confirm_btn.add_event_cb(lambda e: self._confirm_pick(), lv.EVENT.CLICKED, None)

        self._cancel_btn = cancel_btn
        self._confirm_btn = confirm_btn
        self._bottom_bar = bar

        group = lv.group_get_default()
        if group:
            group.add_obj(cancel_btn)
            group.add_obj(confirm_btn)

    def _cancel_pick(self):
        self.setResult(False, {})
        self.finish()

    def _confirm_pick(self):
        if self._selected_paths:
            self.setResult(True, {"paths": self._selected_paths[:]})
        else:
            self.setResult(True, {"paths": [self._current_path]})
        self.finish()

    def _populate_dir(self, path):
        self._dismiss_action_bar()
        self._clear_highlight()
        self._list.clean()
        self._path_to_btn = {}
        path = path.rstrip("/") + "/"
        self._current_path = path
        self._path_label.set_text("  " + path)

        if path != "/":
            parent = "/".join(path.rstrip("/").split("/")[:-1]) + "/"
            if parent == "":
                parent = "/"
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
            self._path_to_btn[fullpath] = btn

        for f in files:
            fullpath = path + f
            btn = self._list.add_button(None, lv.SYMBOL.FILE + "  " + f)
            btn.add_event_cb(lambda e, p=fullpath: self._on_item_clicked(e, p, False), lv.EVENT.CLICKED, None)
            btn.add_event_cb(lambda e, p=fullpath: self._on_any_long_press(e, p), lv.EVENT.LONG_PRESSED, None)
            self._path_to_btn[fullpath] = btn

    def _on_item_clicked(self, e, path, is_dir):
        target = e.get_target_obj()
        if self._mode == self.MODE_PICK:
            self._toggle_selection(path, target)
            return
        if target == self._suppress_btn:
            self._suppress_btn = None
            if __debug__: logger.debug("FileExplorer: CLICK (suppressed) on %s", path)
            self._focus_action_bar()
            return
        if is_dir:
            if __debug__: logger.debug("FileExplorer: CLICK navigate into %s", path)
            self._populate_dir(path)
        else:
            if __debug__: logger.debug("FileExplorer: CLICK view intent for %s", path)
            self.startActivity(Intent(action="view", data=path))

    def _path_matches(self, filename):
        if not self._path_pattern:
            return True
        lower_name = filename.lower()
        for pat in self._path_pattern:
            pat = pat.strip().lower()
            if pat.startswith("*"):
                pat = pat[1:]
            if lower_name.endswith(pat):
                return True
        return False

    def _toggle_selection(self, path, btn):
        if path in self._selected_paths:
            self._selected_paths.remove(path)
            self._set_unselected_style(btn)
            if __debug__: logger.debug("FileExplorer: deselected %s", path)
            return

        if not path.endswith("/") and not self._path_matches(path.rstrip("/").split("/")[-1]):
            if __debug__: logger.debug("FileExplorer: ignoring %s due to path_pattern", path)
            return

        self._selected_paths.append(path)
        self._set_selected_style(btn)
        if __debug__: logger.debug("FileExplorer: selected %s", path)

    def _set_selected_style(self, btn):
        if self._selected_style is None:
            self._selected_style = lv.style_t()
            self._selected_style.init()
            self._selected_style.set_bg_color(lv.theme_get_color_primary(None))
            self._selected_style.set_bg_opa(lv.OPA.COVER)
        btn.add_style(self._selected_style, lv.PART.MAIN)

    def _set_unselected_style(self, btn):
        if self._selected_style is not None:
            btn.remove_style(self._selected_style, lv.PART.MAIN)

    def _on_any_long_press(self, e, path):
        if self._mode == self.MODE_PICK:
            return
        btn = e.get_target_obj()
        self._suppress_btn = btn
        self._selected_path = path
        self._highlight_btn(btn)
        self._show_action_bar()
        if __debug__: logger.debug("FileExplorer: LONG_PRESSED on %s", path)

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
        rename_btn.add_event_cb(lambda e: self._prompt_rename(), lv.EVENT.CLICKED, None)

        cancel_btn = lv.button(bar)
        lv.label(cancel_btn).set_text("Cancel")
        cancel_btn.add_event_cb(lambda e: self._dismiss_action_bar(), lv.EVENT.CLICKED, None)

        self._cancel_btn = cancel_btn
        group = lv.group_get_default()
        if group:
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
        mbox.add_text("Delete {}?".format(name))
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
                logger.error("FileExplorer: delete error %s: %s", path, e)
        if __debug__: logger.debug("FileExplorer: deleted %s", path)
        self._populate_dir(self._current_path)

    def _prompt_rename(self):
        self._dismiss_action_bar()
        self._pending_rename_path = self._selected_path
        old_name = self._selected_path.rstrip("/").split("/")[-1]
        setting = {
            "key": "name",
            "title": "Rename",
            "ui": "textarea",
            "placeholder": old_name,
        }
        intent = Intent(activity_class=InputActivity, extras={"setting": setting, "value": old_name})
        self.startActivityForResult(intent, self._on_rename_result)

    def _on_rename_result(self, result):
        old_path = self._pending_rename_path
        self._pending_rename_path = None
        if not result or not result.get("result_code"):
            if __debug__: logger.debug("FileExplorer: rename cancelled")
            return
        new_name = result.get("data", {}).get("value", "").strip()
        if not new_name:
            return
        parts = old_path.rstrip("/").split("/")
        if len(parts) > 1:
            new_path = "/".join(parts[:-1]) + "/" + new_name
        else:
            new_path = new_name
        try:
            os.rename(old_path, new_path)
            if __debug__: logger.debug("FileExplorer: renamed %s -> %s", old_path, new_path)
        except OSError as e:
            logger.error("FileExplorer: rename error %s -> %s: %s", old_path, new_path, e)
            return
        self._populate_dir(self._current_path)

    def _prompt_create_name(self, kind):
        self._dismiss_action_bar()
        self._pending_create_kind = kind
        title = "Create File" if kind == "file" else "Create Folder"
        placeholder = "filename.txt" if kind == "file" else "foldername"
        setting = {
            "key": "name",
            "title": title,
            "ui": "textarea",
            "placeholder": placeholder,
        }
        intent = Intent(activity_class=InputActivity, extras={"setting": setting})
        self.startActivityForResult(intent, self._on_create_name_result)

    def _on_create_name_result(self, result):
        kind = self._pending_create_kind
        self._pending_create_kind = None
        if not result or not result.get("result_code"):
            if __debug__: logger.debug("FileExplorer: create cancelled")
            return
        name = result.get("data", {}).get("value", "").strip()
        if not name:
            return
        full = self._current_path + name
        try:
            if kind == "folder":
                os.mkdir(full)
            else:
                open(full, "w").close()
            if __debug__: logger.debug("FileExplorer: created %s %s", kind, full)
        except OSError as e:
            logger.error("FileExplorer: create %s error %s: %s", kind, full, e)
            return
        self._populate_dir(self._current_path)

    def onBackPressed(self, screen):
        if self._action_bar:
            self._dismiss_action_bar()
            return True
        return False


AppManager.register_activity("pick_file", FileExplorerActivity)
