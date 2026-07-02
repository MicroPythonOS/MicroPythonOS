import lvgl as lv
import sys
import logging

logger = logging.getLogger(__name__)

def _format_exception(e):
    try:
        import io
        buf = io.StringIO()
        sys.print_exception(e, buf)
        return buf.getvalue()
    except Exception:
        return repr(e)


def show_app_error_dialog(app_fullname, exception, is_lifecycle=False):
    if is_lifecycle:
        title = "Warning"
        message = 'App "' + str(app_fullname) + '" threw an exception. It might be glitchy. Maybe there\'s an update that fixes it?'
    else:
        title = "Error"
        message = 'Could not load app "' + str(app_fullname) + '". Maybe there\'s an update that fixes it?'

    detail = _format_exception(exception)
    logger.warning(detail)

    mbox = lv.msgbox(lv.layer_top())
    mbox.add_title(title)
    mbox.add_text(message)

    if detail:
        detail_label = mbox.add_text(detail)
        detail_label.add_flag(lv.obj.FLAG.HIDDEN)

        show_btn = mbox.add_footer_button("Show Details")

        def on_show_click(e):
            btn = e.get_target_obj()
            if detail_label.has_flag(lv.obj.FLAG.HIDDEN):
                detail_label.remove_flag(lv.obj.FLAG.HIDDEN)
                for i in range(btn.get_child_count()):
                    child = btn.get_child(i)
                    try:
                        if hasattr(child, "set_text"):
                            child.set_text("Hide Details")
                    except Exception:
                        pass
            else:
                detail_label.add_flag(lv.obj.FLAG.HIDDEN)
                for i in range(btn.get_child_count()):
                    child = btn.get_child(i)
                    try:
                        if hasattr(child, "set_text"):
                            child.set_text("Show Details")
                    except Exception:
                        pass

        show_btn.add_event_cb(on_show_click, lv.EVENT.CLICKED, None)

    close_btn = mbox.add_footer_button("Close")
    close_btn.add_event_cb(lambda e: mbox.close(), lv.EVENT.CLICKED, None)
