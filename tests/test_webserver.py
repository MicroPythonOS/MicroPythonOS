"""
Unit tests for the MicroPythonOS webserver.
"""

import _thread
import sys
import time
import unittest

sys.path.insert(0, "../internal_filesystem/lib")

from mpos import TaskManager
from mpos.net.download_manager import DownloadManager
from mpos.webserver.webserver import WebServer


class TestWebServer(unittest.TestCase):
    """Test cases for WebServer."""

    def tearDown(self):
        """Ensure the webserver is stopped after tests."""
        if WebServer.is_started():
            WebServer.stop()
        TaskManager.stop()

    def test_webserver_serves_webrepl_page(self):
        """Webserver should serve the WebREPL HTML page on root."""

        def start_task_manager():
            try:
                TaskManager.enable()
                TaskManager.start()
            except KeyboardInterrupt:
                print("TaskManager got KeyboardInterrupt, falling back to REPL shell...")
            except Exception as exc:
                print(f"TaskManager got exception: {exc}")

        TaskManager.enable()
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(start_task_manager, ())

        startup_timeout = 5.0
        start_time = time.time()
        while TaskManager.keep_running is not True and (time.time() - start_time) < startup_timeout:
            time.sleep(0.05)

        if TaskManager.keep_running is not True:
            self.fail("TaskManager failed to start")

        started = WebServer.start()
        if not started:
            self.fail("WebServer failed to start")

        startup_wait = 3.0
        startup_wait_start = time.time()
        while (time.time() - startup_wait_start) < startup_wait:
            if WebServer.is_started():
                break
            time.sleep(0.05)

        response_state = {"data": None, "error": None, "done": False}

        async def download_task():
            response_bytes = None
            last_error = None
            url_attempts = ["http://localhost:7890/", "http://127.0.0.1:7890/"]
            for url in url_attempts:
                for _ in range(20):
                    try:
                        response_bytes = await DownloadManager.download_url(url)
                        break
                    except Exception as exc:
                        last_error = exc
                        await TaskManager.sleep(0.5)
                if response_bytes is not None:
                    break

            if response_bytes is None:
                response_state["error"] = last_error or RuntimeError(
                    "WebServer did not respond before timeout"
                )
            else:
                response_state["data"] = response_bytes
            response_state["done"] = True

        TaskManager.create_task(download_task())

        timeout_seconds = 30.0
        start_wait = time.time()
        while not response_state["done"] and (time.time() - start_wait) < timeout_seconds:
            time.sleep(0.1)

        if response_state["data"] is None:
            error = response_state["error"]
            self.fail(f"WebServer response unavailable: {error}")

        response_text = response_state["data"].decode("utf-8", "replace")
        self.assertIn("<title>MicroPythonOS WebREPL</title>", response_text)

        WebServer.stop()
        self.assertFalse(WebServer.is_started())
