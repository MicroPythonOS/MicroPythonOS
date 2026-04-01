from mpos import Activity, TaskManager

import mpos

class LoRaChat(Activity):

    alltext = ""

    # Widgets:
    messages = None

    def onCreate(self):
        screen = lv.obj()
        self.messages = lv.label(screen)
        self.messages.set_text('Messages should appear here!')
        self.messages.center()
        self.messages.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.messages.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        print("LoRa Chat foregrounded, starting receive_thread")
        import _thread
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(self.receive_thread, ())

    def onPause(self, screen):
        super().onPause(screen)
        print("LoRa Chat backgrounded, putting LoRa to sleep")
        mpos.sx.sleep(retainConfig=False)

    def receive_thread(self):
        print("starting lora in 3 seconds")
        import time
        time.sleep(5)
        # test LoRa
        from drivers.lora.sx1262 import SX1262
        from machine import Pin, SPI
        rf_sw = Pin(46, Pin.OUT)
        rf_sw.value(1) ; print("RF_SW set to HIGH") # Logic high level means enable receiver mode

        sx =  mpos.sx

        sx.begin(freq=869.618, bw=62.5, sf=8, cr=8, syncWord=0x12, preambleLength=8, implicit=False, crcOn=True, tcxoVoltage=3.0, useRegulatorLDO=False, blocking=True)

        rf_sw.value(1) ; print("RF_SW set to HIGH")

        sx.setDio2AsRfSwitch(False)

        rf_sw.value(1) ; print("RF_SW set to HIGH")

        import time
        while self.has_foreground():
            try:
                print("sx.recv")
                msg, err = sx.recv()
                #msg, err = sx.recv(timeout_en=True, timeout_ms=1000)
                print("after sx.recv")
                if len(msg) > 0:
                    print(msg)
                    self.alltext += "Message: " + msg.hex() + "\n"
                    lv.async_call(lambda _: self.messages.set_text(self.alltext), None)
                else:
                    print("len(msg) was 0")
                status = SX1262.STATUS[err]
                print(f"status: {status}")
                print(f"getRSSI: {sx.getRSSI()}")
                print(f"getSNR: {sx.getSNR()}")
                print(f"getStatus: {sx.getStatus()}")
                print(f"getPacketStatus: {sx.getPacketStatus()}")

                print("Sending...")
                result = sx.send(b"BLAAAA")
                print(f"send result: {result}")
            except Exception as e:
                print(f"receive_thread got exception: {e}")
        
        print("receive_thread stopped")
