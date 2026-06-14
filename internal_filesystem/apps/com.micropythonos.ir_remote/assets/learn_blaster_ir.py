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


def _decode_nec16(burst):
    """Decode a raw NEC/Blaster burst (variable edge count) into (cmd, addr).

    NEC extended (16-bit addr): header mark ~9ms, header space ~4.5ms,
    then 32 data bits encoded as ~562us mark + short/long space (0/1).
    Returns (cmd, addr) on success or raises ValueError with a reason string.
    """
    if len(burst) < 4:
        raise ValueError("burst too short")

    # Header: mark ~9000, space ~4500 (Samsung-style leader ~4500/4500 also ok)
    def near(v, target, pct=0.25):
        return target * (1 - pct) < v < target * (1 + pct)

    if not near(burst[0], 9000) and not near(burst[0], 8500):
        raise ValueError(f"bad header mark {burst[0]}")
    if not (burst[1] > 3000):
        raise ValueError(f"bad header space {burst[1]}")

    # Collect bit spaces (every other value starting at index 3)
    # burst layout: [mark, space, bit0_mark, bit0_space, bit1_mark, bit1_space, ...]
    bits = []
    i = 2
    while i + 1 < len(burst):
        space = burst[i + 1]
        bits.append(1 if space > 1120 else 0)
        i += 2

    if len(bits) < 16:
        raise ValueError(f"too few bits: {len(bits)}")

    # Build 32-bit value (LSB first per NEC)
    val = 0
    for b in reversed(bits[:32]):
        val = (val << 1) | b

    addr = val & 0xffff
    cmd = (val >> 16) & 0xff
    cmd_inv = (val >> 24) & 0xff

    if (cmd ^ cmd_inv) != 0xff:
        raise ValueError(f"cmd checksum fail: cmd=0x{cmd:02x} inv=0x{cmd_inv:02x}")

    return cmd, addr


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
            cmd, addr = _decode_nec16(burst)
            line = f"Cmd 0x{cmd:02x} Addr 0x{addr:04x}"
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
