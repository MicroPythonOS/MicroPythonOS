try:
    simulation_mode = False
    from machine import Pin, SPI
except Exception as e:
    print(f"Activating simulation mode because could not import Pin, SPI from machine: {e}")
    simulation_mode = True

from drivers.lora.sx1262 import SX1262

from mpos import Activity, MposKeyboard, TaskManager, LoRaManager

class LoRaChat(Activity):

    alltext = ""
    lora_device = None

    # Widgets:
    messages = None

    @staticmethod
    def _format_bytes_python_hex(message):
        parts = []
        for byte in message:
            if 32 <= byte <= 126 and byte not in (34, 92):
                parts.append(chr(byte))
            else:
                parts.append("\\x%02x" % byte)
        return "b\"" + "".join(parts) + "\""

    @staticmethod
    def _ellipsize_center(text, head=8, tail=20):
        if len(text) <= head + tail + 3:
            return text
        return text[:head] + "..." + text[-tail:]

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
        LoRaManager.radioChip.sleep(retainConfig=False)

    def send_callback(self, event):
        message = self.input_textarea.get_text()
        if not message:
            print("Ignore empty input")
            return

        self.input_textarea.set_text("")
        self.alltext += "Sent: " + message + "\n"
        lv.async_call(lambda _: self.messages.set_text(self.alltext), None)

        if isinstance(message, (bytes, bytearray)):
            to_send = bytes(message)
        else:
            to_send = str(message).encode("utf8")
        print(f"Sending {to_send} (type={type(to_send)}, len={len(to_send)})")

        if simulation_mode:
            print("Not actually sending because simulation mode")
            return

        _, result = self.lora_device.send(to_send)
        print(f"send result {result}: {SX1262.STATUS[result]}")

        if result == 0:
            # The callback for TX_DONE is never called and the device gets stuck in TX mode unless
            # startReceive is set here. Maybe it should even be unconditional, or at least retried?
            try:
                import time
                time.sleep_ms(200)
                if self.lora_device.getIrqStatus() & SX1262.TX_DONE:
                    self.lora_device.clearIrqStatus()
                    self.lora_device.startReceive()
            except Exception:
                pass

    def receive_callback(self, events):
        print(f"receive_callback for events: {events}")
        print(f"getRSSI: {self.lora_device.getRSSI()}")
        print(f"getSNR: {self.lora_device.getSNR()}")
        print(f"getStatus: {self.lora_device.getStatus()}")
        print(f"getPacketStatus: {self.lora_device.getPacketStatus()}")
        if events & SX1262.TX_DONE:
            print('TX done.')
        elif events & SX1262.RX_DONE:
            print('RX done.')
            try:
                print("self.lora_device.recv")
                msg, err = self.lora_device.recv()
                status = SX1262.STATUS[err]
                print(f"after self.lora_device.recv, status: {status}")
                if len(msg) > 0:
                    print(msg)
                    print(
                        "msg type:",
                        type(msg),
                        "len:",
                        len(msg),
                        "hex:",
                        msg.hex() if isinstance(msg, (bytes, bytearray)) else "(not bytes)",
                    )
                    if isinstance(msg, bytes):
                        try:
                            decoded_msg = msg.decode("utf8")
                        except UnicodeError as e:
                            #print("decode failed, using hex:", repr(e))
                            decoded_msg = self._format_bytes_python_hex(msg)
                            decoded_msg = self._ellipsize_center(decoded_msg, head=10, tail=20)
                    else:
                        decoded_msg = str(msg)
                    print("decoded_msg repr:", repr(decoded_msg))
                    self.alltext += "Received: " + decoded_msg + "\n"
                    lv.async_call(lambda _: self.messages.set_text(self.alltext), None)
                else:
                    print("len(msg) was 0")
            except Exception as e:
                print("receive_callback got exception:", repr(e), "type:", type(e))

    def receive_thread(self):
        print("starting lora in 1 second")
        import time
        time.sleep(1)

        if simulation_mode:
            print("Not starting LoRa because simulation mode")
            return

        # fri3d_2026 doesn't have a reset pin, instead it has RF_SW
        from mpos import DeviceInfo
        if DeviceInfo.hardware_id == "fri3d_2026":
            rf_sw = Pin(46, Pin.OUT)
            rf_sw.value(1) ; print("RF_SW set to HIGH") # Logic high level means enable receiver mode

        self.lora_device = LoRaManager.radioChip

        # MeshCore settings:
        self.lora_device.begin(freq=869.618, bw=62.5, sf=8, cr=8, syncWord=0x12, preambleLength=8, implicit=False, crcOn=True, tcxoVoltage=3.0, useRegulatorLDO=False, blocking=True, currentLimit=140.0, power=22)
        # Meshtastic settings for Europe (868Mhz) at default LongFast profile (untested)
        # https://meshtastic.org/docs/configuration/radio/lora/
        #self.lora_device.begin(freq=869.525, bw=250, sf=12, cr=8, syncWord=0x2B, preambleLength=16, implicit=False, crcOn=True, tcxoVoltage=3.0, useRegulatorLDO=False, blocking=True, currentLimit=140.0, power=22)
        self.lora_device.setBlockingCallback(False, self.receive_callback)

        if DeviceInfo.hardware_id == "fri3d_2026":
            self.lora_device.setDio2AsRfSwitch(False)
            rf_sw.value(1) ; print("RF_SW set to HIGH")

        print("lora started")

