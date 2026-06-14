import lvgl as lv

from mpos import Activity, IRManager

try:
    from machine import Pin
    from ir.ir_rx.acquire import IR_GET

    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/IR_GET: {e}")
    simulation_mode = True
    Pin = None
    IR_GET = None


def _decode_blaster(burst):
    """Decode a raw NEC-timing IR burst into a 16-bit code.

    This protocol uses NEC-style pulse-distance encoding:
      header mark ~8.5-9ms, header space >3ms,
      data bits encoded as ~560us mark + short (~470us=0) or long (~1530us=1) space.
    The frame is 16 bits with no checksum (unlike standard 32-bit NEC).
    Returns (code, nbits) on success or raises ValueError with a reason string.
    """
    if len(burst) < 4:
        raise ValueError("burst too short")

    if not (burst[0] > 6000):
        raise ValueError(f"bad header mark {burst[0]}")
    if not (burst[1] > 3000):
        raise ValueError(f"bad header space {burst[1]}")

    # Collect bits from spaces; skip the optional trailing stop-mark (odd tail)
    # burst layout: [hdr_mark, hdr_space, bit0_mark, bit0_space, ..., stop_mark?]
    bits = []
    i = 2
    while i + 1 < len(burst):
        space = burst[i + 1]
        bits.append(1 if space > 1120 else 0)
        i += 2

    nbits = len(bits)
    if nbits < 8:
        raise ValueError(f"too few bits: {nbits}")

    # Build value LSB first (standard NEC bit order)
    val = 0
    for b in reversed(bits):
        val = (val << 1) | b

    return val, nbits


class LearnBlasterIR(Activity):

    status = None
    screen = None
    check_timer = None

    def onCreate(self):
        self.screen = lv.obj()
        self.status = lv.label(self.screen)
        self.status.set_text("Listening for Blaster IR data...")
        self.setContentView(self.screen)

    def onResume(self, screen):
        super().onResume(screen)
        import mpos.ui

        mpos.ui.change_task_handler(100)
        if simulation_mode:
            print("IR receiver not available; running in simulation mode.")
            self.ir = None
            return
        try:
            self.ir = IR_GET(IRManager.rxPin, display=False)
        except Exception as e:
            print(f"Failed to init IR receiver: {e}")
            self.ir = None
        self.check_timer = lv.timer_create(self.check_data, 1000, None)

    def onPause(self, screen):
        if self.check_timer is not None:
            self.check_timer.delete()
            self.check_timer = None
        if getattr(self, "ir", None):
            try:
                self.ir.close()
            except Exception as e:
                print(f"Failed to close IR receiver: {e}")
            self.ir = None
        import mpos.ui

        mpos.ui.change_task_handler()

    def check_data(self, args):
        if self.ir is None or self.ir.data is None:
            return
        burst = self.ir.data
        self.ir.data = None
        print(f"burst: {burst}")
        try:
            val, nbits = _decode_blaster(burst)
            lo = val & 0xff
            hi = (val >> 8) & 0xff
            line = f"0x{val:04x} ({nbits}bit) lo=0x{lo:02x} hi=0x{hi:02x}"
        except ValueError as e:
            line = f"Decode error: {e}"
        print(line)
        self._add_line(line)

    def _add_line(self, line):
        current = self.status.get_text() if self.status else ""
        if current:
            current = f"{current}\n{line}"
        else:
            current = line
        if self.status:
            self.status.set_text(current)
