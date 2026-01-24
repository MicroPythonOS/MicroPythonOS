import asyncio
import unittest
import _thread
import time

from mpos import App, AppManager
from mpos import TaskManager

from websocket import WebSocketApp

class TestMutlipleWebsocketsAsyncio(unittest.TestCase):

    max_allowed_connections = 3 # max that echo.websocket.org allows

    #relays = ["wss://echo.websocket.org" ]
    #relays = ["wss://echo.websocket.org", "wss://echo.websocket.org"]
    #relays = ["wss://echo.websocket.org", "wss://echo.websocket.org", "wss://echo.websocket.org" ] # more gives "too many requests" error
    relays = ["wss://echo.websocket.org", "wss://echo.websocket.org", "wss://echo.websocket.org", "wss://echo.websocket.org", "wss://echo.websocket.org" ] # more might give "too many requests" error
    wslist = []

    on_open_called = 0
    on_message_called = 0
    on_ping_called = 0
    on_close_called = 0
    on_error_called = 0

    def on_message(self, wsapp, message: str):
        print(f"on_message received: {message}")
        self.on_message_called = True
        
    def on_open(self, wsapp):
        print(f"on_open called: {wsapp}")
        self.on_open_called += 1
        #wsapp.send('{"type": "subscribe","product_ids": ["BTC-USD"],"channels": ["ticker_batch"]}')

    def on_ping(wsapp, message):
        print("Got a ping!")
        self.on_ping_called = True

    def on_close(self, wsapp, close_status_code, close_msg):
        print(f"on_close called: {wsapp}")
        self.on_close_called += 1

    def on_error(self, wsapp, arg1):
        print(f"on_error called: {wsapp}, {arg1}")
        self.on_error_called += 1

    async def closeall(self):
        await asyncio.sleep(1)

        self.on_close_called = 0
        print("disconnecting...")
        for ws in self.wslist:
            await ws.close()

    async def run_main(self) -> None:
        tasks = []
        self.wslist = []
        for idx, wsurl in enumerate(self.relays):
            print(f"creating WebSocketApp for {wsurl}")
            ws = WebSocketApp(
                wsurl,
                on_open=self.on_open,
                on_close=self.on_close,
                on_message=self.on_message,
                on_ping=self.on_ping,
                on_error=self.on_error
            )
            print(f"creating task for {wsurl}")
            tasks.append(asyncio.create_task(ws.run_forever(),))
            print(f"created task for {wsurl}")
            self.wslist.append(ws)

        print(f"Starting {len(tasks)} concurrent WebSocket connections…")
        await asyncio.sleep(2)
        await self.closeall()

        for _ in range(10):
            print(f"self.on_open_called: {self.on_open_called} so waiting for on_open to be called...")
            if self.on_open_called == min(len(self.relays),self.max_allowed_connections):
                print("yes, it was called!")
                break
            await asyncio.sleep(1)
        self.assertTrue(self.on_open_called == min(len(self.relays),self.max_allowed_connections))

        for _ in range(10):
            print(f"self.on_close_called: {self.on_close_called} so waiting for on_close to be called...")
            if self.on_close_called >= min(len(self.relays),self.max_allowed_connections):
                print("yes, it was called!")
                break
            await asyncio.sleep(1)
        self.assertGreaterEqual(self.on_close_called, min(len(self.relays),self.max_allowed_connections), "on_close was called for less than allowed connections")

        self.assertEqual(self.on_error_called, max(0, len(self.relays) - self.max_allowed_connections), "expecting one error per failed connection")

        # Wait for *all* of them to finish (or be cancelled)
        # If this hangs, it's also a failure:
        print(f"doing gather of tasks: {tasks}")
        for index, task in enumerate(tasks): print(f"task {index}: ph_key:{task.ph_key} done:{task.done()} running {task.coro}")
        await asyncio.gather(*tasks, return_exceptions=True)

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
        asyncio.run(self.run_main())
