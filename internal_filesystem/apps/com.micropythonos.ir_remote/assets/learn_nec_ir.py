import lvgl as lv

from mpos import Activity, IRManager
from learn_blaster_ir import LearnBlasterIR  # noqa: F401
from learn_tcl_ir import LearnTCLIR  # noqa: F401

try:
    from machine import Pin
    from ir.ir_rx.nec import NEC_16

    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/NEC_16: {e}")
    simulation_mode = True
    Pin = None
    NEC_16 = None


class LearnNECIR(Activity):

    status = None
    screen = None

    def onCreate(self):
        self.screen = lv.obj()
        self.status = lv.label(self.screen)
        self.status.set_text("Listening for NEC IR data...")
        self.setContentView(self.screen)

    def onResume(self, screen):
        super().onResume(screen)
        import mpos.ui
        mpos.ui.change_task_handler(100) # needed for accurate timings
        if simulation_mode:
            print("IR receiver not available; running in simulation mode.")
            self.ir = None
            return
        try:
            # NEC_16 is most generic: supports extended 16-bit addresses and
            # has a smaller leader threshold than SAMSUNG so fewer false rejects
            self.ir = NEC_16(IRManager.rxPin, self._on_ir)
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
        mpos.ui.change_task_handler() # back to default

    def _on_ir(self, data, addr, ctrl):
        if data < 0:
            line = "Repeat code."
        else:
            line = f"Data 0x{data:02x} Addr 0x{addr:04x} Ctrl 0x{ctrl:02x}"
        print(line)
        self.add_data(line)

    def add_data(self, line):
        current = self.status.get_text() if self.status else ""
        if current:
            current = f"{current}\n{line}"
        else:
            current = line
        if self.status:
            self.status.set_text(current)
    