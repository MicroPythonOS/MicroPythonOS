try:
    simulation_mode = False
    from machine import Pin, SPI
except Exception as e:
    print(f"Activating simulation mode because could not import Pin, SPI from machine: {e}")
    simulation_mode = True

from drivers.lora.sx1262 import SX1262

from mpos import Activity, MposKeyboard, TaskManager

import mpos

class LoRaChat(Activity):

    alltext = ""
    lora_device = None

    # Widgets:
    messages = None

    def onCreate(self):
        main_content = lv.obj()
        main_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        main_content.set_style_pad_gap(10, 0)

        self.input_textarea = lv.textarea(main_content)
        self.input_textarea.set_placeholder_text("Message input...")
        self.input_textarea.set_one_line(True)
        self.input_textarea.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        self.input_textarea.set_width(lv.pct(100))
        #self.input_textarea.add_event_cb(self.show_keyboard, lv.EVENT.CLICKED, None)

        self.keyboard = MposKeyboard(main_content)
        self.keyboard.set_textarea(self.input_textarea)
        #self.keyboard.add_event_cb(self.keyboard_cb, lv.EVENT.READY, None)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        self.send_button = lv.button(main_content)
        self.send_button.add_event_cb(self.send_callback, lv.EVENT.CLICKED, None)
        send_label = lv.label(self.send_button)
        send_label.set_text("Send It!")

        self.messages = lv.label(main_content)
        self.messages.set_text('Waiting for messages...')
        self.messages.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.messages.set_style_text_font(lv.font_montserrat_14, 0)

        self.setContentView(main_content)

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

    def send_callback(self, event):
        message = self.input_textarea.get_text()
        if not message:
            print("Ignore empty input")
            return

        self.input_textarea.set_text("")
        self.alltext += "Sent: " + message + "\n"
        lv.async_call(lambda _: self.messages.set_text(self.alltext), None)

        to_send = message.encode('utf8')
        print(f"Sending {to_send}")

        if simulation_mode:
            print("Not actually sending because simulation mode")
            return

        _, result = self.lora_device.send(to_send)
        print(f"send result {result}: {SX1262.STATUS[result]}")

    def receive_callback(self, events):
        if events & SX1262.TX_DONE:
            print('TX done.')
        elif events & SX1262.RX_DONE:
            print('RX done.')
            try:
                print("self.lora_device.recv")
                msg, err = self.lora_device.recv()
                print("after self.lora_device.recv")
                if len(msg) > 0:
                    print(msg)
                    self.alltext += "Received: " + msg.hex() + "\n"
                    lv.async_call(lambda _: self.messages.set_text(self.alltext), None)
                else:
                    print("len(msg) was 0")
                status = SX1262.STATUS[err]
                print(f"status: {status}")
                print(f"getRSSI: {self.lora_device.getRSSI()}")
                print(f"getSNR: {self.lora_device.getSNR()}")
                print(f"getStatus: {self.lora_device.getStatus()}")
                print(f"getPacketStatus: {self.lora_device.getPacketStatus()}")
            except Exception as e:
                print(f"receive_thread got exception: {e}")

    def receive_thread(self):
        print("starting lora in 1 second")
        import time
        time.sleep(1)

        if simulation_mode:
            print("Not starting LoRa because simulation mode")
            return

        rf_sw = Pin(46, Pin.OUT)
        rf_sw.value(1) ; print("RF_SW set to HIGH") # Logic high level means enable receiver mode

        self.lora_device = mpos.sx

        self.lora_device.begin(freq=869.618, bw=62.5, sf=8, cr=8, syncWord=0x12, preambleLength=8, implicit=False, crcOn=True, tcxoVoltage=3.0, useRegulatorLDO=False, blocking=True)
        self.lora_device.setBlockingCallback(False, self.receive_callback)
        self.lora_device.setDio2AsRfSwitch(False)

        rf_sw.value(1) ; print("RF_SW set to HIGH")

