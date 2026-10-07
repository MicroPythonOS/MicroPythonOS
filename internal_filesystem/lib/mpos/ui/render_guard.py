import sys

import micropython

STACK_SIZE = 16 * 1024 if sys.platform == "esp32" else None
RENDER_RESERVE = 9 * 1024


def has_render_headroom():
    if STACK_SIZE is None:
        return True
    return STACK_SIZE - micropython.stack_use() >= RENDER_RESERVE


def on_task_handler(event, user_data):
    return has_render_headroom()


def install(task_handler, started_event):
    task_handler.add_event_cb(on_task_handler, started_event)
