This /lib folder contains:

- mip.install('github:jonnor/micropython-zipfile')
- mip.install("aiohttp") # easy websockets

- https://github.com/micropython/micropython-lib/blob/master/micropython/aiorepl/aiorepl.py version 0.2.2 # for asyncio REPL, allowing await expressions

- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/base64/base64.py version 3.3.6 # for nostr
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/binascii/binascii.py version 2.4.1 # for base64.py
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/logging/logging.py version 0.6.2 # for About app
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/shutil/shutil.py version 0.0.5 # for rmtree()
- https://github.com/micropython/micropython-lib/blob/master/python-stdlib/unittest/unittest/__init__.py  version 0.10.4 # for testing (also on-device)
