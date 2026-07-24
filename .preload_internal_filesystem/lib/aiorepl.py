# Web (Emscripten) REPL bridge for MicroPythonOS — drop-in aiorepl replacement.
#
# The browser has no readable stdin, so the upstream aiorepl (which reads
# sys.stdin via asyncio.StreamReader) fails with EIO. This version reads input
# from the `_webterm` native bridge (fed by the JS host) and yields to the
# asyncio loop between polls, so the LVGL/UI task handler keeps running while a
# host drives the REPL. Output uses sys.stdout, which the web build mirrors to
# the host (Module.__webterm.onOutput) via a C-level stdout hook.
#
# The raw REPL (Ctrl-A) and raw-paste (Ctrl-E A) protocol matches mpremote, so
# external tools that speak the standard MicroPython raw REPL work unchanged.

import micropython
from micropython import const
import sys
import asyncio
import _webterm

_webterm.init()

CHAR_CTRL_A = const(1)
CHAR_CTRL_B = const(2)
CHAR_CTRL_C = const(3)
CHAR_CTRL_D = const(4)
CHAR_CTRL_E = const(5)


class _WebStdin:
    # Async, non-blocking stdin backed by the _webterm input queue. read()
    # waits (yielding to asyncio) until at least one byte is available, then
    # returns up to n bytes as a str (one char per byte), matching how the
    # upstream StreamReader(sys.stdin) reads are consumed by this REPL.
    async def read(self, n=1):
        while _webterm.any() == 0:
            await asyncio.sleep_ms(10)
        out = ""
        while len(out) < n:
            c = _webterm.rx()
            if c < 0:
                break
            out += chr(c)
        return out


async def execute(code, g, s):
    if not code.strip():
        return
    try:
        if "await " in code:
            # Execute the snippet in an async context.
            code = "async def __code():\n    {}\n".format(
                code.replace("\n", "\n    ")
            )
            l = {}
            exec(code, g, l)
            return await l["__code"]()
        else:
            try:
                return eval(code, g)
            except SyntaxError:
                return exec(code, g)
    except Exception as err:
        sys.print_exception(err, sys.stdout)


async def raw_paste(s, window=512):
    sys.stdout.write("R\x01")  # supported
    sys.stdout.write(bytearray([window & 0xFF, window >> 8, 0x01]).decode())
    eof = False
    idx = 0
    buff = bytearray(window)
    file = b""
    while not eof:
        for idx in range(window):
            b = await s.read(1)
            c = ord(b)
            if c == CHAR_CTRL_C or c == CHAR_CTRL_D:
                sys.stdout.write(chr(CHAR_CTRL_D))
                if c == CHAR_CTRL_C:
                    raise KeyboardInterrupt
                file += buff[:idx]
                eof = True
                break
            buff[idx] = c
        if not eof:
            file += buff
            sys.stdout.write("\x01")  # window available
    return file


async def raw_repl(s, g):
    heading = "raw REPL; CTRL-B to exit\n"
    line = ""
    sys.stdout.write(heading)
    while True:
        line = ""
        sys.stdout.write(">")
        while True:
            b = await s.read(1)
            if not b:
                continue
            c = ord(b)
            if c == CHAR_CTRL_A:
                rline = line
                line = ""
                if len(rline) == 2 and ord(rline[0]) == CHAR_CTRL_E:
                    if rline[1] == "A":
                        line = await raw_paste(s)
                        break
                else:
                    # reset raw REPL
                    sys.stdout.write(heading)
                    sys.stdout.write(">")
                continue
            elif c == CHAR_CTRL_B:
                sys.stdout.write("\n")
                return 0
            elif c == CHAR_CTRL_C:
                line = ""
            elif c == CHAR_CTRL_D:
                sys.stdout.write("OK")
                break
            else:
                # any other raw 8-bit value
                line += b
        if isinstance(line, str) and len(line) == 0:
            sys.stdout.write("Ignored: soft reboot\n")
            sys.stdout.write(heading)
        try:
            result = exec(line, g)
            if result is not None:
                sys.stdout.write(repr(result))
            sys.stdout.write(chr(CHAR_CTRL_D))
        except KeyboardInterrupt:
            sys.stdout.write(chr(CHAR_CTRL_D))
        except Exception as ex:
            sys.stdout.write(chr(CHAR_CTRL_D))
            sys.print_exception(ex, sys.stdout)
        sys.stdout.write(chr(CHAR_CTRL_D))


# REPL task. Signature matches upstream aiorepl.task() so AIOReplService can
# call it unchanged: aiorepl.task(g={...}, prompt=">>> ").
async def task(g=None, prompt=">>> "):
    print("Starting web asyncio REPL (input via _webterm)...")
    if g is None:
        g = __import__("__main__").__dict__
    micropython.kbd_intr(-1)
    s = _WebStdin()
    # Only reprint the prompt after an interaction that actually produced
    # visible activity. Hosts probing with bare CRs during boot (to detect
    # REPL readiness) would otherwise spam ">>> " into the console log.
    # (Hosts can also skip probing entirely: Module.__webterm.ready is set
    # once _webterm.init() has run.)
    show_prompt = True
    while True:
        if show_prompt:
            sys.stdout.write(prompt)
        show_prompt = True
        cmd = ""
        paste = False
        while True:
            b = await s.read(1)
            if not b:
                continue
            c = ord(b)
            if c == CHAR_CTRL_A:
                await raw_repl(s, g)
                break
            elif c == CHAR_CTRL_B:
                continue
            elif c == CHAR_CTRL_C:
                sys.stdout.write("\n")
                break
            elif c == CHAR_CTRL_D:
                if paste:
                    result = await execute(cmd, g, s)
                    if result is not None:
                        sys.stdout.write(repr(result))
                        sys.stdout.write("\n")
                    break
                # In the browser there is no process to exit; just refresh.
                sys.stdout.write("\n")
                break
            elif c == CHAR_CTRL_E:
                sys.stdout.write("paste mode; Ctrl-C to cancel, Ctrl-D to finish\n===\n")
                paste = True
            elif c == 0x0A or c == 0x0D:
                if paste:
                    sys.stdout.write("\n")
                    cmd += "\n"
                    continue
                if not cmd:
                    # Bare CR/LF with nothing typed: don't echo a newline or a
                    # fresh prompt (avoids prompt spam from readiness probes).
                    show_prompt = False
                    break
                sys.stdout.write("\n")
                result = await execute(cmd, g, s)
                if result is not None:
                    sys.stdout.write(repr(result))
                    sys.stdout.write("\n")
                break
            elif c == 0x08 or c == 0x7F:
                if cmd:
                    cmd = cmd[:-1]
                    sys.stdout.write("\x08 \x08")
            elif 0x20 <= c <= 0x7E:
                cmd += b
                sys.stdout.write(b)
            # other control characters are ignored
