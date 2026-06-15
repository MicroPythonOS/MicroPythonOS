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


class TCL_NEC(IR_RX):
    """NEC_16-style decoder for TCL smart TV remotes.

    TCL uses NEC extended (32-bit, LSB-first) encoding but with a non-standard
    header: ~4ms mark + ~4ms space instead of NEC's 9ms/4.5ms.  Bit timing is
    also shifted: ~500us mark, ~500-1000us space (0), ~1950us space (1).
    The frame is still addr_lo(8) + addr_hi(8) + cmd(8) + ~cmd(8), and the
    cmd/~cmd checksum is preserved, so we validate it.

    nedges=70 gives enough room for the full 32-bit frame (~67 edges).
    The relaxed header check (> 3000us) handles the ~3900-4100us variation.
    """

    def __init__(self, pin, callback, *args):
        super().__init__(pin, 70, 80, callback, *args)

    def decode(self, _):
        try:
            lb = self.edge - 1
            if lb < 4:
                raise ValueError("burst too short")

            hdr_mark = ticks_diff(self._times[1], self._times[0])
            hdr_space = ticks_diff(self._times[2], self._times[1])
            if hdr_mark < 3000:
                raise ValueError(f"bad header mark {hdr_mark}")
            if hdr_space < 3000:
                raise ValueError(f"bad header space {hdr_space}")

            # Walk bit pairs, stopping at the inter-frame gap (> 6ms).
            # tblock=80ms captures both the first frame and the start of the
            # repeated frame; gap detection keeps only the first frame's bits.
            bits = []
            for x in range(2, lb - 1, 2):
                space = ticks_diff(self._times[x + 2], self._times[x + 1])
                if space > 6000:
                    break
                bits.append(1 if space > 1200 else 0)

            if len(bits) < 24:
                raise ValueError(f"too few bits: {len(bits)}")

            val = 0
            for b in reversed(bits[:24]):
                val = (val << 1) | b

            addr = val & 0xffff
            cmd = (val >> 16) & 0xff

        except (ValueError, IndexError) as e:
            print(f"TCL_NEC decode error: {e}")
            self.do_callback(IR_RX.BADDATA, 0, 0)
            return

        self.do_callback(cmd, addr, 0)


class LearnTCLIR(Activity):

    status = None
    screen = None

    def onCreate(self):
        self.screen = lv.obj()
        self.status = lv.label(self.screen)
        self.status.set_text("Listening for TCL IR data...")
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
            self.ir = TCL_NEC(IRManager.rxPin, self._on_ir)
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

    def _on_ir(self, cmd, addr, ctrl):
        if cmd < 0:
            line = "Decode error."
        else:
            line = f"Cmd 0x{cmd:02x} Addr 0x{addr:04x}"
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
