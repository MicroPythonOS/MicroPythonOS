import unittest
import _thread
import time

from mpos import App, PackageManager
import mpos.apps

from websocket import WebSocketApp

class TestWebsocket(unittest.TestCase):

    ws = None

    on_open_called = None
    on_message_called = None
    on_ping_called = None
    on_close_called = None

    def on_message(self, wsapp, message: str):
        print(f"on_message received: {message}")
        self.on_message_called = True
        
    def on_open(self, wsapp):
        print(f"on_open called: {wsapp}")
        self.on_open_called = True
        self.ws.send('{"type": "subscribe","product_ids": ["BTC-USD"],"channels": ["ticker_batch"]}')

    def on_ping(wsapp, message):
        print("Got a ping!")
        self.on_ping_called = True

    def on_close(self, wsapp, close_status_code, close_msg):
        print(f"on_close called: {wsapp}")
        self.on_close_called = True

    def websocket_thread(self):
        wsurl = "wss://ws-feed.exchange.coinbase.com"

        self.ws = WebSocketApp(
            wsurl,
            on_open=self.on_open,
            on_close=self.on_close,
            on_message=self.on_message,
            on_ping=self.on_ping
        ) # maybe add other callbacks to reconnect when disconnected etc.
        self.ws.run_forever()

    def wait_for_ping(self):
        self.on_ping_called = False
        for _ in range(60):
            print("Waiting for on_ping to be called...")
            if self.on_ping_called:
                print("yes, it was called!")
                break
            time.sleep(1)
        self.assertTrue(self.on_ping_called)

    def test_it(self):
        on_open_called = False
        _thread.stack_size(mpos.apps.good_stack_size())
        _thread.start_new_thread(self.websocket_thread, ())
        
        self.on_open_called = False
        self.on_message_called = False # message might be received very quickly, before we expect it
        for _ in range(5):
            print("Waiting for on_open to be called...")
            if self.on_open_called:
                print("yes, it was called!")
                break
            time.sleep(1)
        self.assertTrue(self.on_open_called)

        self.on_message_called = False # message might be received very quickly, before we expect it
        for _ in range(5):
            print("Waiting for on_message to be called...")
            if self.on_message_called:
                print("yes, it was called!")
                break
            time.sleep(1)
        self.assertTrue(self.on_message_called)

        # Disabled because not all servers send pings:
        # self.wait_for_ping()

        self.on_close_called = False
        self.ws.close()
        for _ in range(5):
            print("Waiting for on_close to be called...")
            if self.on_close_called:
                print("yes, it was called!")
                break
            time.sleep(1)
        self.assertTrue(self.on_close_called)
