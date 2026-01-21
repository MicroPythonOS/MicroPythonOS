This /lib folder contains:
- https://github.com/echo-lalia/qmi8658-micropython/blob/main/qmi8685.py but given the correct name "qmi8658.py"
- traceback.mpy from https://github.com/micropython/micropython-lib
- mip.install('github:jonnor/micropython-zipfile')
- mip.install("shutil") for shutil.rmtree('/apps/com.example.files') # for rmtree()
- mip.install("aiohttp") # easy websockets
- mip.install("base64") # for nostr etc
- mip.install("collections") # used by aiohttp
- mip.install("unittest")
- mip.install("logging")
- mip.install("aiorepl")

