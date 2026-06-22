import lvgl as lv

from mpos import Activity, IRManager

try:
    from machine import Pin
    from utime import ticks_diff
    from ir.ir_rx import IR_RX

    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/IR_RX: {e}")
    simulation_mode = True
    Pin = None
    IR_RX = object  # fallback so class definition doesn't fail


class NEC_16_RAW(IR_RX):
    """NEC-timing receiver sized for 16-bit (no-checksum) frames.

    Standard NEC_16 waits for 68 edges; this device sends only ~35
    (2 header + 16 bits × 2 + 1 stop).  nedges=40 captures the full
    frame and lets the block timer fire normally.
    Delivers (val & 0xff, (val >> 8) & 0xff, nbits) to the callback,
    matching the (cmd, addr, ext) convention of the other IR_RX decoders.
    """

    def __init__(self, pin, callback, *args):
        super().__init__(pin, 40, 80, callback, *args)

    def decode(self, _):
        try:
            lb = self.edge - 1
            if lb < 4:
                raise ValueError("burst too short")

            hdr_mark = ticks_diff(self._times[1], self._times[0])
            hdr_space = ticks_diff(self._times[2], self._times[1])
            if hdr_mark < 6000:
                raise ValueError(f"bad header mark {hdr_mark}")
            if hdr_space < 3000:
                raise ValueError(f"bad header space {hdr_space}")

            bits = []
            for x in range(2, lb - 1, 2):
                space = ticks_diff(self._times[x + 2], self._times[x + 1])
                bits.append(1 if space > 1120 else 0)

            nbits = len(bits)
            if nbits < 8:
                raise ValueError(f"too few bits: {nbits}")

            val = 0
            for b in reversed(bits):
                val = (val << 1) | b

            cmd = val & 0xff
            addr = (val >> 8) & 0xff
        except (ValueError, IndexError) as e:
            print(f"NEC_16_RAW decode error: {e}")
            self.do_callback(IR_RX.BADDATA, 0, 0)
            return

        self.do_callback(cmd, addr, nbits)


class LearnBlasterIR(Activity):

    status = None
    screen = None

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
            self.ir = NEC_16_RAW(IRManager.rxPin, self._on_ir)
        except Exception as e:
            print(f"Failed to init IR receiver: {e}")
            self.ir = None

    def onPause(self, screen):
        if getattr(self, "ir", None):
            try:
                self.ir.close()
            except Exception as e:
                print(f"Failed to close IR receiver: {e}")
            self.ir = None
        import mpos.ui

        mpos.ui.change_task_handler()

    def _on_ir(self, cmd, addr, nbits):
        if cmd < 0:
            line = "Decode error."
        else:
            val = cmd | (addr << 8)
            line = f"0x{val:04x} ({nbits}bit) lo=0x{cmd:02x} hi=0x{addr:02x}"
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
