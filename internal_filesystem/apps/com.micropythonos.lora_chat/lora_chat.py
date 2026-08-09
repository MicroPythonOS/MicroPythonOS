try:
    simulation_mode = False
    from machine import Pin
except Exception as e:
    print(f"Activating simulation mode because could not import Pin, SPI from machine: {e}")
    simulation_mode = True

from mpos.polled_sx126x import PolledSX126x
import lvgl as lv

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
        self.input_textarea.set_text_selection(True)
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
        if not simulation_mode:
            if not LoRaManager.acquire(self.appFullName):
                print("LoRa in use by", LoRaManager.holder)
                return
        import _thread
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(self.receive_thread, ())

    def onPause(self, screen):
        super().onPause(screen)
        print("LoRa Chat backgrounded, releasing LoRa lock")
        if not simulation_mode:
            LoRaManager.release(self.appFullName)

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
        print(f"send result {result}: {PolledSX126x.STATUS[result]}")

    def receive_callback(self, events):
        print(f"receive_callback for events: {events}")
        print(f"getRSSI: {self.lora_device.rssi}")
        print(f"getSNR: {self.lora_device.snr}")
        print(f"getStatus: {self.lora_device.get_status()}")
        print(f"getPacketStatus: {self.lora_device.get_packet_status()}")
        if events & PolledSX126x.TX_DONE:
            print('TX done.')
        elif events & PolledSX126x.RX_DONE:
            print('RX done.')
            try:
                print("self.lora_device.recv")
                msg, err = self.lora_device.recv()
                status = PolledSX126x.STATUS[err]
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

        # SPI bus race workaround: stop the watchdog and suspend the
        # DIO1 ISR during configure/calibrate to prevent SPI bus
        # collisions from concurrent thread access.
        #LoRaManager.stop_watchdog()
        self.lora_device.suspend()

        # Custom LoRa Chat settings to avoid overlap with Meshtastic and MeshCore:
        # syncWord 0x12 is for peer-to-peer
        # sf=10 for longer range but also longer transmission time
        # cr=8 is 4/8: maximal error correction, but slower
        self.lora_device.radio.configure({ "freq_khz": 869450, "bw": 62.5, "sf": 10, "coding_rate": 8, "syncword": 0x12, "preamble_len": 8, "output_power": 22 })
        self.lora_device.radio.calibrate_image()
        # Meshtastic settings for Europe (868Mhz) at default LongFast profile (untested)
        # https://meshtastic.org/docs/configuration/radio/lora/
        # self.lora_device.radio.configure({"freq_khz": 869525, "bw": 250, "sf": 12, "coding_rate": 8, "syncword": 0x2B, "preamble_len": 16, "output_power": 22})

        # MeshCore settings:
        # self.lora_device.radio.configure({"freq_khz": 869618, "bw": 62.5, "sf": 8, "coding_rate": 8, "syncword": 0x12, "preamble_len": 8, "output_power": 22})
        self.lora_device.set_callback(self.receive_callback)

        self.lora_device.resume()

        if DeviceInfo.hardware_id == "fri3d_2026":
            rf_sw.value(1) ; print("RF_SW set to HIGH")

        print("lora started")
