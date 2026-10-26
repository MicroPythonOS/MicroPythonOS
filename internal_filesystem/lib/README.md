This /lib folder contains:

- mip.install("aiohttp") # easy websockets

- https://github.com/micropython/micropython-lib/blob/master/micropython/aiorepl/aiorepl.py version 0.2.2 # for asyncio REPL, allowing await expressions

- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/base64/base64.py version 3.3.6 # for nostr
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/binascii/binascii.py version 2.4.1, without its pure-Python b2a_base64/a2b_base64 (they shadowed the much faster C ubinascii ones) # for base64.py
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/logging/logging.py version 0.6.2 # for About app
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/shutil/shutil.py version 0.0.5 # for rmtree()
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/unittest/unittest/__init__.py  version 0.11.0, with one local change to keep when updating: _run_suite() records exceptions from setUp, tearDown, cleanups, setUpClass and tearDownClass as errors or skips instead of letting them abort the run (#328) # for testing (also on-device)
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/pathlib/pathlib.py version 0.0.1 # for Path()
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/os-path/os/path.py version 0.2.0 # for os.path (monkeypatched)
