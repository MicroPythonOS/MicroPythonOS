"""Minimal in-memory Nostr relay for MicroPython unit tests.

Implements just enough of the Nostr WebSocket protocol to let
NostrManager publish and subscribe on a local loopback address.
"""

import asyncio
import json
import time

try:
    import hashlib
except ImportError:
    import uhashlib as hashlib  # type: ignore

try:
    import binascii
except ImportError:
    import ubinascii as binascii  # type: ignore


class _Filter:
    """Tiny filter matcher used by the local relay."""

    def __init__(self, data):
        self.kinds = data.get("kinds", [])
        self.authors = data.get("authors", [])
        self.pubkey_refs = data.get("#p", [])
        self.event_refs = data.get("#e", [])

    def match(self, event):
        if self.kinds and event.get("kind") not in self.kinds:
            return False
        if self.authors and event.get("pubkey") not in self.authors:
            return False
        tags = event.get("tags", [])
        if self.pubkey_refs:
            tag_values = [t[1] for t in tags if isinstance(t, (list, tuple)) and len(t) >= 2 and t[0] == "p"]
            if not any(v in self.pubkey_refs for v in tag_values):
                return False
        if self.event_refs:
            tag_values = [t[1] for t in tags if isinstance(t, (list, tuple)) and len(t) >= 2 and t[0] == "e"]
            if not any(v in self.event_refs for v in tag_values):
                return False
        return True


class LocalNostrRelay:
    """A single-client local Nostr relay for regression tests."""

    _GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self):
        self.url = None
        self._server = None
        self._writer = None
        self._reader = None
        self._subscriptions = {}
        self._running = False
        self._received_events = []

    async def start(self, host="127.0.0.1", port=8765):
        self.url = "ws://{}:{}".format(host, port)
        self._server = await asyncio.start_server(self._handle_client, host, port)
        return self.url

    async def stop(self):
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

    async def send_ping(self):
        """Send a WebSocket ping frame and wait a short while for a pong."""
        if self._writer:
            await self._send_frame(0x09, b"")
            await asyncio.sleep(0.1)

    async def _handle_client(self, reader, writer):
        self._reader = reader
        self._writer = writer
        await self._handshake()
        self._running = True
        try:
            while self._running:
                opcode, payload = await self._recv_frame()
                if opcode == 0x08:
                    break
                if opcode == 0x09:
                    # ping -> pong
                    await self._send_frame(0x0A, payload)
                    continue
                if opcode != 0x01:
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except Exception:
                    continue
                await self._handle_message(msg)
        except Exception:
            pass
        finally:
            self._running = False

    async def _handshake(self):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = await self._reader.read(1)
            if not chunk:
                break
            data += chunk
        lines = data.split(b"\r\n")
        key = None
        for line in lines:
            if line.lower().startswith(b"sec-websocket-key:"):
                key = line.split(b":", 1)[1].strip()
                break
        if key is None:
            raise RuntimeError("Missing Sec-WebSocket-Key")
        accept = self._accept_hash(key)
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: {}\r\n"
            "\r\n".format(accept)
        )
        self._writer.write(response.encode("utf-8"))
        await self._writer.drain()

    def _accept_hash(self, key):
        digest = hashlib.sha1(key + self._GUID.encode("utf-8")).digest()
        return binascii.b2a_base64(digest).decode("ascii").strip()

    async def _recv_frame(self):
        header = await self._reader.read(2)
        if not header or len(header) < 2:
            raise RuntimeError("Connection closed")
        byte1, byte2 = header[0], header[1]
        opcode = byte1 & 0x0F
        masked = bool(byte2 & 0x80)
        length = byte2 & 0x7F
        if length == 126:
            length = int.from_bytes(await self._reader.read(2), "big")
        elif length == 127:
            length = int.from_bytes(await self._reader.read(8), "big")
        if masked:
            mask = await self._reader.read(4)
        payload = await self._reader.read(length)
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    async def _send_frame(self, opcode, payload):
        frame = bytearray()
        frame.append(0x80 | opcode)
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))
        self._writer.write(frame)
        self._writer.write(payload)
        await self._writer.drain()

    async def _send_text(self, text):
        await self._send_frame(0x01, text.encode("utf-8"))

    async def _handle_message(self, msg):
        if not msg:
            return
        verb = msg[0]
        if verb == "REQ":
            sub_id = msg[1]
            filters = msg[2] if len(msg) > 2 else {}
            self._subscriptions[sub_id] = _Filter(filters)
        elif verb == "CLOSE":
            self._subscriptions.pop(msg[1], None)
        elif verb == "EVENT":
            event = msg[1]
            self._received_events.append(event)
            await self._broadcast(event)

    async def _broadcast(self, event):
        for sub_id, filt in self._subscriptions.items():
            if filt.match(event):
                await self._send_text(json.dumps(["EVENT", sub_id, event]))
