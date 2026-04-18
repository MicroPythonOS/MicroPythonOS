import lvgl as lv

from mpos import Activity, IRManager

try:
    from machine import Pin
    from ir.ir_rx.nec import SAMSUNG

    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/SAMSUNG: {e}")
    simulation_mode = True
    Pin = None
    SAMSUNG = None

class LearnNECIR(Activity):

    status = None
    screen = None

    check_timer = None

    def onCreate(self):
        print("learn_ir.py")
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
            # not 16 bit has more failure possibility and 'samsung' variant has a smaller "leader" (otherwise it refuses)
            # so NEC_16 is the most generic:
            self.ir = NEC_16(IRManager.rxPin, self._on_ir)
        except Exception as e:
            print(f"Failed to init IR receiver: {e}")
            self.ir = None
        #self.check_timer = lv.timer_create(self.check_data, 1000, None)

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
        mpos.ui.change_task_handler() # back to default

    def check_data(self, args):
        if self.ir.data is not None:
            print(self.ir.data)
            self.add_data(self.ir.data)
            self.ir.data = None

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
    