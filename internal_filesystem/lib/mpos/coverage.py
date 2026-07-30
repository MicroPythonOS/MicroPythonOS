"""Line coverage for MicroPython using sys.settrace.

Requires MICROPY_PY_SYS_SETTRACE=1 (mpcov build variant).
Usage:
    import mpos.coverage
    mpos.coverage.start()
    # ... run tests ...
    mpos.coverage.stop()
    print(mpos.coverage.report_json())
"""
import sys

_tracker = None


def _trace_callback(frame, event, arg):
    if event != "line":
        return _trace_callback
    fn = frame.f_code.co_filename
    if _tracker._skip(fn):
        return _trace_callback
    lineno = frame.f_lineno
    d = _tracker._hits.get(fn)
    if d is None:
        _tracker._hits[fn] = {lineno: 1}
    else:
        d[lineno] = d.get(lineno, 0) + 1
    return _trace_callback


class Tracker:
    def __init__(self):
        self._hits = {}

    def _skip(self, filename):
        return not (
            filename.startswith("apps/")
            or (filename.startswith("lib/mpos/") and not filename.endswith("/coverage.py"))
        )

    def start(self):
        global _tracker
        _tracker = self
        sys.settrace(_trace_callback)

    def stop(self):
        sys.settrace(None)

    def report_json(self):
        import ujson

        files = {}
        for fn, lines in sorted(self._hits.items()):
            files[fn] = {"lines": {str(k): v for k, v in lines.items()}}
        return ujson.dumps({"files": files})


def start():
    if not hasattr(sys, "settrace"):
        raise RuntimeError("sys.settrace not available; build with mpcov variant")
    tracker = Tracker()
    tracker.start()
    return tracker


def stop():
    sys.settrace(None)
