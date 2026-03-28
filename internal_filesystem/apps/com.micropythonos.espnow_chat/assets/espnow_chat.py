"""
https://docs.micropython.org/en/latest/library/espnow.html
"""

from collections import deque

import lvgl as lv
import machine
from message_input_activity import MessageInputActivity
from micropython import const
from mpos import Activity, Intent, TaskManager
from mpos.time import localtime

try:
    import aioespnow
except ImportError:
    aioespnow = None

try:
    import network
except ImportError:
    network = None

BROADCAST_MAC = const(b"\xbb\xbb\xbb\xbb\xbb\xbb")


def pformat_mac(mac):
    if mac:
        return ":".join(f"{b:02x}" for b in mac)
    else:
        return "<no mac>"


class EspNowChat(Activity):
    def onCreate(self):
        main_content = lv.obj()

        self.messages = lv.label(main_content)
        self.messages.set_style_text_font(lv.font_montserrat_14, 0)

        self.write_btn = lv.button(main_content)
        write_label = lv.label(self.write_btn)
        write_label.set_text("Send Message")
        self.write_btn.align(lv.ALIGN.BOTTOM_RIGHT, -10, -10)
        self.write_btn.add_event_cb(self.open_message_input, lv.EVENT.CLICKED, None)

        # Buffer to store and display the latest 20 messages:
        self.messages_buffer = deque((), 20)

        self.setContentView(main_content)

        if aioespnow and network:
            print("Initialize WLAN interface...")
            sta = network.WLAN(network.WLAN.IF_STA)
            sta.active(True)

            self.own_id = pformat_mac(machine.unique_id())

            self.info("Initialize ESPNow...")
            self.espnow = aioespnow.AIOESPNow()
            self.espnow.active(True)
            self.espnow.add_peer(BROADCAST_MAC)

            if sta.isconnected():
                self.info(f"Connected to WiFi: {sta.config('essid')}")
            self.info(f"Use WiFi Channel: {sta.config('channel')}")
        else:
            self.own_id = "<no espnow>"
            self.info("ESPNow not available on this platform")

    def info(self, text):
        now = localtime()
        hour, minute, second = now[3], now[4], now[5]
        message = f"{hour:02}:{minute:02}:{second:02} {text}"
        print(message)
        self.messages_buffer.append(message)
        self.messages.set_text("\n".join(self.messages_buffer))

    def open_message_input(self, event):
        intent = Intent(activity_class=MessageInputActivity)
        self.startActivityForResult(intent, self.on_message_input_result)

    def on_message_input_result(self, result: dict):
        print(f"on_message_input_result: {result=}")
        if not result:
            return
        if message := result.get("data"):
            print(f"Create task to send {message=}")
            TaskManager.create_task(self.send_messages(message))

    async def send_messages(self, message):
        self.info(f"Sending: {message} ({self.own_id})")
        try:
            await self.espnow.asend(BROADCAST_MAC, message.encode())
        except OSError as err:
            print(f"Error sending message: {err}")
        else:
            print(f"{message=} sent")

    async def receive_messages(self):
        await self.send_messages(f"{self.own_id} joins ESPNow chat.")
        async for mac, msg in self.espnow:
            if not msg:
                print("Ignore empty message from", pformat_mac(mac))
                continue
            try:
                msg = msg.decode()
            except UnicodeError as err:
                msg = f"<invalid message: {err}>"
            self.info(f"{msg} ({pformat_mac(mac)})")
        raise RuntimeError("ESPNow receive loop exited, which shouldn't happen")

    def onResume(self, screen):
        super().onResume(screen)
        if aioespnow and network:
            TaskManager.create_task(self.receive_messages())

    def onPause(self, screen):
        if aioespnow and network:
            self.espnow.send(
                BROADCAST_MAC, f"{self.own_id} leaves ESPNow chat.".encode()
            )

            print("Stop ESPNow...")
            self.espnow.active(False)
            print("ESPNow deactivated")

        super().onPause(screen)
