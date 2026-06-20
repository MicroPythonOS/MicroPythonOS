import logging
import os

import lvgl as lv

from mpos import Activity, DisplayMetrics, Intent, MposKeyboard

logger = logging.getLogger(__name__)


class TextEditor(Activity):
    _DEFAULT_DIR = "data/text"
    _SUPPORTED_EXTENSIONS = [
        ".txt",
        ".py",
        ".html",
        ".csv",
        ".json",
        ".md",
        ".log",
        ".xml",
        ".cfg",
        ".ini",
    ]

    _filename = None
    _saved_content = ""
    _loading = False

    _top_bar = None
    _open_button = None
    _save_button = None
    _filename_label = None
    _textarea = None
    _keyboard = None

    _save_as_overlay = None
    _save_as_textarea = None
    _pause_overlay = None
    _expecting_pause = False

    def onCreate(self):
        self._ensure_dir(self._DEFAULT_DIR)

        screen = lv.obj()
        screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_gap(4, 0)

        self._top_bar = lv.obj(screen)
        self._top_bar.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self._top_bar.set_style_pad_all(4, lv.PART.MAIN)
        self._top_bar.set_flex_flow(lv.FLEX_FLOW.ROW)
        self._top_bar.set_flex_align(
            lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER
        )

        self._open_button = lv.button(self._top_bar)
        self._open_button.set_size(
            DisplayMetrics.pct_of_width(24), DisplayMetrics.pct_of_height(13)
        )
        self._open_button.add_event_cb(self._open_file_clicked, lv.EVENT.CLICKED, None)
        open_label = lv.label(self._open_button)
        open_label.set_text("Open")
        open_label.center()

        self._filename_label = lv.label(self._top_bar)
        self._filename_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)
        self._filename_label.set_flex_grow(1)
        self._filename_label.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.PART.MAIN)
        self._filename_label.set_style_pad_left(6, lv.PART.MAIN)
        self._filename_label.set_style_pad_right(6, lv.PART.MAIN)

        self._save_button = lv.button(self._top_bar)
        self._save_button.set_size(
            DisplayMetrics.pct_of_width(24), DisplayMetrics.pct_of_height(13)
        )
        self._save_button.add_event_cb(self._save_file_clicked, lv.EVENT.CLICKED, None)
        save_label = lv.label(self._save_button)
        save_label.set_text("Save")
        save_label.center()

        self._textarea = lv.textarea(screen)
        self._textarea.set_text("")
        self._textarea.set_placeholder_text("Type your text here...")
        self._textarea.set_width(lv.pct(100))
        self._textarea.set_flex_grow(1)
        self._textarea.add_event_cb(self._on_text_changed, lv.EVENT.VALUE_CHANGED, None)
        self._textarea.add_event_cb(self._show_keyboard, lv.EVENT.CLICKED, None)

        self._keyboard = MposKeyboard(screen)
        self._keyboard.set_textarea(self._textarea)
        self._keyboard.set_style_min_height(0, lv.PART.MAIN)
        self._keyboard.set_size(lv.pct(100), DisplayMetrics.pct_of_height(40))
        self._keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self._keyboard.add_event_cb(self._on_keyboard_ready, lv.EVENT.READY, None)

        self.setContentView(screen)

        group = lv.group_get_default()
        if group:
            group.add_obj(self._open_button)
            group.add_obj(self._save_button)
            group.add_obj(self._textarea)

    def onResume(self, screen):
        super().onResume(screen)
        self._expecting_pause = False

        path = self.getIntent().extras.get("filename") or self.getIntent().data
        if path:
            self._load_file(path)
        elif self._filename is None:
            self._new_file()
        self._update_title()

    def onPause(self, screen):
        super().onPause(screen)
        if self._pause_overlay is not None or self._save_as_overlay is not None:
            return
        if self._has_unsaved_changes() and not self._expecting_pause:
            self._hide_keyboard()
            self._show_pause_confirm()

    def _ensure_dir(self, path):
        path = path.rstrip("/")
        if path == "" or path == "/":
            return
        parent = "/".join(path.split("/")[:-1])
        if parent and parent != "/":
            self._ensure_dir(parent)
        try:
            os.mkdir(path)
        except OSError:
            pass

    def _basename(self, path):
        name = path.rstrip("/").split("/")[-1]
        return name if name else path

    def _new_file(self):
        self._filename = None
        self._saved_content = ""
        self._loading = True
        try:
            self._textarea.set_text("")
        finally:
            self._loading = False
        self._update_title()

    def _load_file(self, path):
        try:
            with open(path, "r") as f:
                content = f.read()
        except OSError as e:
            logger.error("TextEditor: failed to read %s: %s", path, e)
            self._new_file()
            return
        self._filename = path
        self._saved_content = content
        self._loading = True
        try:
            self._textarea.set_text(content)
        finally:
            self._loading = False
        self._update_title()

    def _has_unsaved_changes(self):
        return self._textarea.get_text() != self._saved_content

    def _update_title(self):
        name = self._basename(self._filename) if self._filename else "Untitled"
        if self._has_unsaved_changes():
            name = name + " *"
        self._filename_label.set_text(name)

    def _on_text_changed(self, event):
        if self._loading:
            return
        self._update_title()

    def _show_keyboard(self, event=None, textarea=None):
        ta = textarea or self._textarea
        self._keyboard.set_textarea(ta)
        self._keyboard.show_keyboard()

    def _hide_keyboard(self):
        self._keyboard.hide_keyboard()

    def _on_keyboard_ready(self, event):
        self._hide_keyboard()

    def _open_file_clicked(self, event):
        self._expecting_pause = True
        intent = Intent(
            action="pick_file",
            extras={
                "start_dir": self._DEFAULT_DIR,
                "path_pattern": self._SUPPORTED_EXTENSIONS,
            },
        )
        self.startActivityForResult(intent, self._on_file_picked)

    def _on_file_picked(self, result):
        self._expecting_pause = False
        if not result or not result.get("result_code"):
            return
        paths = result.get("data", {}).get("paths", [])
        for path in paths:
            if not path.endswith("/"):
                self._load_file(path)
                return

    def _save_file_clicked(self, event):
        self._save_file()

    def _save_file(self):
        if not self._filename:
            self._show_save_as_dialog()
            return
        self._perform_save(self._filename)

    def _perform_save(self, path):
        self._ensure_dir(self._default_dir_for(path))
        content = self._textarea.get_text()
        try:
            with open(path, "w") as f:
                f.write(content)
        except OSError as e:
            logger.error("TextEditor: failed to write %s: %s", path, e)
            self._filename_label.set_text("Save failed")
            return
        self._filename = path
        self._saved_content = content
        self._update_title()

    def _default_dir_for(self, path):
        if "/" not in path:
            return self._DEFAULT_DIR
        return "/".join(path.rstrip("/").split("/")[:-1])

    def _show_save_as_dialog(self):
        if self._save_as_overlay:
            return
        self._hide_keyboard()

        overlay = lv.obj(self._top_bar.get_parent())
        overlay.remove_flag(lv.obj.FLAG.SCROLLABLE)
        overlay.set_size(lv.pct(100), lv.pct(100))
        overlay.add_flag(lv.obj.FLAG.FLOATING)
        overlay.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        overlay.set_style_bg_opa(lv.OPA._50, lv.PART.MAIN)
        overlay.add_flag(lv.obj.FLAG.CLICKABLE)
        overlay.align(lv.ALIGN.CENTER, 0, 0)

        container = lv.obj(overlay)
        container.set_size(lv.pct(90), lv.SIZE_CONTENT)
        container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        container.set_style_pad_all(10, lv.PART.MAIN)
        container.set_style_pad_gap(8, 0)
        container.set_style_bg_color(lv.color_hex(0x333333), lv.PART.MAIN)
        container.center()

        prompt_label = lv.label(container)
        prompt_label.set_text("Enter filename:")
        prompt_label.set_width(lv.pct(100))

        name_ta = lv.textarea(container)
        name_ta.set_one_line(True)
        name_ta.set_width(lv.pct(100))
        name_ta.set_placeholder_text("filename.txt")
        name_ta.set_text("")
        name_ta.add_event_cb(lambda e: self._show_keyboard(textarea=name_ta), lv.EVENT.CLICKED, None)

        btn_row = lv.obj(container)
        btn_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        btn_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_row.set_flex_align(
            lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER
        )

        ok_btn = lv.button(btn_row)
        lv.label(ok_btn).set_text("OK")
        ok_btn.add_event_cb(lambda e: self._on_save_as_confirm(name_ta, overlay), lv.EVENT.CLICKED, None)

        cancel_btn = lv.button(btn_row)
        lv.label(cancel_btn).set_text("Cancel")
        cancel_btn.add_event_cb(lambda e: self._on_save_as_cancel(overlay), lv.EVENT.CLICKED, None)

        group = lv.group_get_default()
        if group:
            group.add_obj(name_ta)
            group.add_obj(ok_btn)
            group.add_obj(cancel_btn)

        self._save_as_overlay = overlay
        self._save_as_textarea = name_ta
        self._show_keyboard(textarea=name_ta)
        lv.group_focus_obj(name_ta)

    def _on_save_as_confirm(self, name_ta, overlay):
        name = name_ta.get_text().strip()
        if not name:
            return
        if "." not in name:
            name = name + ".txt"
        path = self._DEFAULT_DIR + "/" + name
        self._close_save_as_dialog(overlay)
        self._perform_save(path)

    def _on_save_as_cancel(self, overlay):
        self._close_save_as_dialog(overlay)

    def _close_save_as_dialog(self, overlay):
        overlay.delete()
        self._save_as_overlay = None
        self._save_as_textarea = None
        self._keyboard.set_textarea(self._textarea)
        self._hide_keyboard()
        self._update_title()

    def _show_pause_confirm(self):
        overlay = lv.obj(lv.layer_top())
        overlay.remove_flag(lv.obj.FLAG.SCROLLABLE)
        overlay.set_size(lv.pct(100), lv.pct(100))
        overlay.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        overlay.set_style_bg_opa(lv.OPA._50, lv.PART.MAIN)
        overlay.add_flag(lv.obj.FLAG.CLICKABLE)
        overlay.align(lv.ALIGN.CENTER, 0, 0)

        container = lv.obj(overlay)
        container.set_size(lv.pct(80), lv.SIZE_CONTENT)
        container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        container.set_style_pad_all(12, lv.PART.MAIN)
        container.set_style_pad_gap(10, 0)
        container.set_style_bg_color(lv.color_hex(0x333333), lv.PART.MAIN)
        container.center()

        prompt = lv.label(container)
        prompt.set_text("Save file?")
        prompt.set_width(lv.pct(100))

        btn_row = lv.obj(container)
        btn_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        btn_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_row.set_flex_align(
            lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER
        )

        yes_btn = lv.button(btn_row)
        lv.label(yes_btn).set_text("Yes")
        yes_btn.add_event_cb(lambda e: self._on_pause_yes(overlay), lv.EVENT.CLICKED, None)

        no_btn = lv.button(btn_row)
        lv.label(no_btn).set_text("No")
        no_btn.add_event_cb(lambda e: self._on_pause_no(overlay), lv.EVENT.CLICKED, None)

        group = lv.group_get_default()
        if group:
            group.add_obj(yes_btn)
            group.add_obj(no_btn)

        self._pause_overlay = overlay
        lv.group_focus_obj(yes_btn)

    def _on_pause_yes(self, overlay):
        overlay.delete()
        self._pause_overlay = None
        self._save_file()

    def _on_pause_no(self, overlay):
        overlay.delete()
        self._pause_overlay = None
