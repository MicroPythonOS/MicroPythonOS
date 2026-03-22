import sys
import time

import machine


def _adc_read(adc):
    if hasattr(adc, "read_u16"):
        return adc.read_u16()
    return adc.read()


def _pin_snapshot(pin_id):
    pin = machine.Pin(pin_id)
    snapshot = {"pin": pin, "mode": None, "pull": None, "value": None}
    for attr in ("mode", "pull"):
        getter = getattr(pin, attr, None)
        if callable(getter):
            try:
                snapshot[attr] = getter()
            except Exception:
                pass
    try:
        snapshot["value"] = pin.value()
    except Exception:
        pass
    return snapshot


def _try_pin_snapshot(pin_id):
    try:
        return _pin_snapshot(pin_id), None
    except Exception as exc:
        return None, exc


def _restore_pin(snapshot):
    pin = snapshot["pin"]
    mode = snapshot.get("mode")
    pull = snapshot.get("pull")
    value = snapshot.get("value")

    try:
        if hasattr(pin, "init"):
            kwargs = {}
            if mode is not None:
                kwargs["mode"] = mode
            if pull is not None:
                kwargs["pull"] = pull
            if value is not None and mode in (machine.Pin.OUT, getattr(machine.Pin, "OPEN_DRAIN", None)):
                kwargs["value"] = value
            if kwargs:
                pin.init(**kwargs)
                return
        if value is not None and mode in (machine.Pin.OUT, getattr(machine.Pin, "OPEN_DRAIN", None)):
            pin.value(value)
    except Exception as exc:
        print("pinstates: WARNING: failed to restore GPIO%02d: %r" % (pin.id(), exc))


def _detect_board():
    impl = [repr(sys.implementation)]
    impl.append(getattr(sys.implementation, "_machine", ""))
    impl.append(getattr(sys.implementation, "machine", ""))
    haystack = " ".join(impl).upper()
    if "ESP32S3" in haystack:
        return "esp32s3"
    return "esp32"


def _candidate_pins(board, skiplist=None):
    extra_skip = set(skiplist or [])
    if board in ("esp32", "esp32-wroom", "esp32-wrover"):
        skip = {6, 7, 8, 9, 10, 11, 20, 24, 28, 29, 30, 31}
        return [p for p in range(0, 40) if p not in skip and p not in extra_skip]
    if board in ("esp32s3", "esp32-s3"):
        skip = {22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 45, 46}
        return [p for p in range(0, 49) if p not in skip and p not in extra_skip]
    raise ValueError("Unsupported board type: %r" % board)


def read_all_pins(skiplist=None):
    board = _detect_board()
    pins = _candidate_pins(board, skiplist=skiplist)
    results = {"digital": {}, "analog": {}, "errors": {"digital": {}, "analog": {}}}

    for p in pins:
        pin_snapshot, snapshot_error = _try_pin_snapshot(p)
        if snapshot_error is not None:
            results["errors"]["digital"][p] = repr(snapshot_error)
            continue
        try:
            print("Reading digital GPIO%02d..." % p)
            pin = machine.Pin(p, machine.Pin.IN)
            results["digital"][p] = pin.value()
            #time.sleep(1)
        except Exception as exc:
            results["errors"]["digital"][p] = repr(exc)
        finally:
            try:
                _restore_pin(pin_snapshot)
            except Exception as exc:
                results["errors"]["digital"][p] = repr(exc)
    
    for p in pins:
        pin_snapshot, snapshot_error = _try_pin_snapshot(p)
        if snapshot_error is not None:
            results["errors"]["analog"][p] = repr(snapshot_error)
            continue
        try:
            print("Reading analog GPIO%02d..." % p)
            adc = machine.ADC(machine.Pin(p))
            results["analog"][p] = _adc_read(adc)
            #time.sleep(1)
        except Exception as exc:
            results["errors"]["analog"][p] = repr(exc)
        finally:
            try:
                _restore_pin(pin_snapshot)
            except Exception as exc:
                results["errors"]["analog"][p] = repr(exc)
    
    print("=== Pin State Readout ===")
    print("Board:", board)
    print("=== Digital Reads ===")
    for p in pins:
        if p in results["digital"]:
            print("GPIO%02d:" % p, results["digital"][p])
        else:
            print("GPIO%02d:" % p, "ERR", results["errors"]["digital"].get(p))

    print("=== Analog Reads ===")
    for p in pins:
        if p in results["analog"]:
            print("GPIO%02d:" % p, results["analog"][p])
        else:
            print("GPIO%02d:" % p, "ERR", results["errors"]["analog"].get(p))

    return results
