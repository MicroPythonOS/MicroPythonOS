from collections import deque

import lvgl as lv
from mpos import Activity, MposKeyboard


class ReplShell(Activity):
    def onCreate(self):
        self.namespace = {}
        self.buffer = deque((), 200)

        main = lv.obj()
        main.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        main.set_style_pad_gap(10, 0)

        self.input_area = lv.textarea(main)
        self.input_area.set_placeholder_text("Python code...")
        self.input_area.set_one_line(True)
        self.input_area.set_width(lv.pct(100))
        self.input_area.add_event_cb(self._show_keyboard, lv.EVENT.CLICKED, None)

        self.keyboard = MposKeyboard(main)
        self.keyboard.set_textarea(self.input_area)
        self.keyboard.add_event_cb(self._on_submit, lv.EVENT.READY, None)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        self.output = lv.label(main)
        self.output.set_text("")
        self.output.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.output.set_flex_grow(1)

        self.setContentView(main)

    def _show_keyboard(self, event):
        self.keyboard.remove_flag(lv.obj.FLAG.HIDDEN)

    def _on_submit(self, event):
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        code = self.input_area.get_text()
        if not code:
            return
        self.input_area.set_text("")

        self._append(">>> %s" % code)
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        self.namespace["print"] = _print
        error = None
        try:
            exec(code, self.namespace)
        except Exception as e:
            error = "!!! %s: %s" % (type(e).__name__, e)
        for line in "".join(captured).rstrip("\n").split("\n"):
            if line:
                self._append(line)
        if error:
            self._append(error)

    def _append(self, line):
        self.buffer.append(line)
        self.output.set_text("\n".join(self.buffer))
