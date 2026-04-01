from drivers.lora.sx1262 import SX1262
from machine import Pin, SPI

from mpos import Activity, TaskManager

import mpos

class LoRaChat(Activity):

    alltext = ""
    lora_device = None

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

    def receive_callback(self, events):
        if events & SX1262.RX_DONE:
            try:
                print("self.lora_device.recv")
                msg, err = self.lora_device.recv()
                print("after self.lora_device.recv")
                if len(msg) > 0:
                    print(msg)
                    self.alltext += "Message: " + msg.hex() + "\n"
                    lv.async_call(lambda _: self.messages.set_text(self.alltext), None)
                else:
                    print("len(msg) was 0")
                status = SX1262.STATUS[err]
                print(f"status: {status}")
                print(f"getRSSI: {self.lora_device.getRSSI()}")
                print(f"getSNR: {self.lora_device.getSNR()}")
                print(f"getStatus: {self.lora_device.getStatus()}")
                print(f"getPacketStatus: {self.lora_device.getPacketStatus()}")

                #print("Sending...")
                #result = sx.send(b"BLAAAA")
                #print(f"send result: {result}")
            except Exception as e:
                print(f"receive_thread got exception: {e}")

    def receive_thread(self):
        print("starting lora in 3 seconds")
        import time
        time.sleep(5)

        rf_sw = Pin(46, Pin.OUT)
        rf_sw.value(1) ; print("RF_SW set to HIGH") # Logic high level means enable receiver mode

        self.lora_device = mpos.sx

        self.lora_device.begin(freq=869.618, bw=62.5, sf=8, cr=8, syncWord=0x12, preambleLength=8, implicit=False, crcOn=True, tcxoVoltage=3.0, useRegulatorLDO=False, blocking=True)
        self.lora_device.setBlockingCallback(False, self.receive_callback)
        self.lora_device.setDio2AsRfSwitch(False)

        rf_sw.value(1) ; print("RF_SW set to HIGH")

