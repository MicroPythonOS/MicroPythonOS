import unittest
import _thread
import time

from mpos import App, AppManager, TaskManager

from uaiowebsocket import WebSocketApp

# demo_multiple_ws.py
import asyncio
import aiohttp
from aiohttp import WSMsgType
import logging
import sys
from typing import List



# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


class TestTwoWebsockets(unittest.TestCase):
#class TestTwoWebsockets():

    # ----------------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------------
    # Change these to point to a real echo / chat server you control.
    WS_URLS = [
        "wss://echo.websocket.org",          # public echo service (may be down)
        "wss://echo.websocket.org",          # duplicate on purpose – shows concurrency
        "wss://echo.websocket.org",
        # add more URLs here…
    ]
    
    nr_connected = 0
    
    # How many messages each connection should send before closing gracefully
    MESSAGES_PER_CONNECTION = 2
    STOP_AFTER = 10
    
    # ----------------------------------------------------------------------
    # One connection worker
    # ----------------------------------------------------------------------
    async def ws_worker(self, session: aiohttp.ClientSession, url: str, idx: int) -> None:
        """
        Handles a single WebSocket connection:
        * sends a few messages,
        * echoes back everything it receives,
        * closes when the remote end says "close" or after MESSAGES_PER_CONNECTION.
        """
        try:
            async with session.ws_connect(url) as ws:
                log.info(f"[{idx}] Connected to {url}")
                self.nr_connected += 1
    
                # ------------------------------------------------------------------
                # 1. Send a few starter messages
                # ------------------------------------------------------------------
                for i in range(self.MESSAGES_PER_CONNECTION):
                    payload = f"Hello from client #{idx} – msg {i+1}"
                    await ws.send_str(payload)
                    log.info(f"[{idx}] → {payload}")
    
                    # give the server a moment to reply
                    await asyncio.sleep(0.5)
    
                # ------------------------------------------------------------------
                # 2. Echo-loop – react to incoming messages
                # ------------------------------------------------------------------
                msgcounter = 0
                async for msg in ws:
                    msgcounter += 1
                    if msgcounter > self.STOP_AFTER:
                        print("Max reached, stopping...")
                        await ws.close()
                        break
                    if msg.type == WSMsgType.TEXT:
                        data: str = msg.data
                        log.info(f"[{idx}] ← {data}")
    
                        # Echo back (with a suffix)
                        reply = data + " / answer"
                        await ws.send_str(reply)
                        log.info(f"[{idx}] → {reply}")
    
                        # Close if server asks us to
                        if data.strip().lower() == "close cmd":
                            log.info(f"[{idx}] Server asked to close → closing")
                            await ws.close()
                            break
    
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                        log.info(f"[{idx}] Connection closed by remote")
                        break
    
                    elif msg.type == WSMsgType.ERROR:
                        log.error(f"[{idx}] WebSocket error: {ws.exception()}")
                        break
    
        except asyncio.CancelledError:
            log.info(f"[{idx}] Task cancelled")
            raise
        except Exception as exc:
            log.exception(f"[{idx}] Unexpected error on {url}: {exc}")
        finally:
            log.info(f"[{idx}] Worker finished for {url}")
    
    # ----------------------------------------------------------------------
    # Main entry point – creates a single ClientSession + many tasks
    # ----------------------------------------------------------------------
    async def main(self) -> None:
        async with aiohttp.ClientSession() as session:
            # Create one task per URL (they all run concurrently)
            tasks = [
                asyncio.create_task(self.ws_worker(session, url, idx))
                for idx, url in enumerate(self.WS_URLS)
            ]
    
            log.info(f"Starting {len(tasks)} concurrent WebSocket connections…")
            # Wait for *all* of them to finish (or be cancelled)
            await asyncio.gather(*tasks, return_exceptions=True)
            log.info(f"All tasks stopped successfully!")
            self.assertTrue(self.nr_connected, len(self.WS_URLS))

    def newthread(self):
        asyncio.run(self.main())

    def test_it(self):
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(self.newthread, ())
        time.sleep(10)




# This demonstrates a crash when doing asyncio using different threads:
#class TestCrashingSeparateThreads(unittest.TestCase):
class TestCrashingSeparateThreads(): # Disabled

    # ----------------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------------
    # Change these to point to a real echo / chat server you control.
    WS_URLS = [
        "wss://echo.websocket.org",          # public echo service (may be down)
        "wss://echo.websocket.org",          # duplicate on purpose – shows concurrency
        "wss://echo.websocket.org",
        # add more URLs here…
    ]
    
    # How many messages each connection should send before closing gracefully
    MESSAGES_PER_CONNECTION = 2
    STOP_AFTER = 10
    
    # ----------------------------------------------------------------------
    # One connection worker
    # ----------------------------------------------------------------------
    async def ws_worker(self, session: aiohttp.ClientSession, url: str, idx: int) -> None:
        """
        Handles a single WebSocket connection:
        * sends a few messages,
        * echoes back everything it receives,
        * closes when the remote end says "close" or after MESSAGES_PER_CONNECTION.
        """
        try:
            async with session.ws_connect(url) as ws:
                log.info(f"[{idx}] Connected to {url}")
    
                # ------------------------------------------------------------------
                # 1. Send a few starter messages
                # ------------------------------------------------------------------
                for i in range(self.MESSAGES_PER_CONNECTION):
                    payload = f"Hello from client #{idx} – msg {i+1}"
                    await ws.send_str(payload)
                    log.info(f"[{idx}] → {payload}")
    
                    # give the server a moment to reply
                    await asyncio.sleep(0.5)
    
                # ------------------------------------------------------------------
                # 2. Echo-loop – react to incoming messages
                # ------------------------------------------------------------------
                msgcounter = 0
                async for msg in ws:
                    msgcounter += 1
                    if msgcounter > self.STOP_AFTER:
                        print("Max reached, stopping...")
                        await ws.close()
                        break
                    if msg.type == WSMsgType.TEXT:
                        data: str = msg.data
                        log.info(f"[{idx}] ← {data}")
    
                        # Echo back (with a suffix)
                        reply = data + " / answer"
                        await ws.send_str(reply)
                        log.info(f"[{idx}] → {reply}")
    
                        # Close if server asks us to
                        if data.strip().lower() == "close cmd":
                            log.info(f"[{idx}] Server asked to close → closing")
                            await ws.close()
                            break
    
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                        log.info(f"[{idx}] Connection closed by remote")
                        break
    
                    elif msg.type == WSMsgType.ERROR:
                        log.error(f"[{idx}] WebSocket error: {ws.exception()}")
                        break
    
        except asyncio.CancelledError:
            log.info(f"[{idx}] Task cancelled")
            raise
        except Exception as exc:
            log.exception(f"[{idx}] Unexpected error on {url}: {exc}")
        finally:
            log.info(f"[{idx}] Worker finished for {url}")
    
    # ----------------------------------------------------------------------
    # Main entry point – creates a single ClientSession + many tasks
    # ----------------------------------------------------------------------
    async def main(self) -> None:
        async with aiohttp.ClientSession() as session:
            # Create one task per URL (they all run concurrently)
            tasks = [
                asyncio.create_task(self.ws_worker(session, url, idx))
                for idx, url in enumerate(self.WS_URLS)
            ]
    
            log.info(f"Starting {len(tasks)} concurrent WebSocket connections…")
            # Wait for *all* of them to finish (or be cancelled)
            await asyncio.gather(*tasks, return_exceptions=True)

    async def almostmain(self, url):
        async with aiohttp.ClientSession() as session:
            asyncio.create_task(self.ws_worker(session, url, idx))
    
    def newthread(self, url):
        asyncio.run(self.main())

    def test_it(self):
        for url in self.WS_URLS:
            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self.newthread, (url,))
        time.sleep(15)
