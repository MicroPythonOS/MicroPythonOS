from pdm_mic import PDM_Mic
import time

# Adjust pins according to your LilyGo board / hardware
# Typical for many LilyGo S3 watches: CLK on GPIO 0 or 47, DATA on GPIO 1 or 48
mic = PDM_Mic(clk=44, data=47, rate=16000, bufsize=4096)

mic.start()

buf = bytearray(4096)   # or larger for less overhead

print("Recording 5 seconds of PDM audio...")

with open("/record.pcm", "wb") as f:
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < 5000:
        n = mic.readinto(buf)
        if n > 0:
            f.write(buf[:n])

mic.stop()
mic.deinit()

print("Done. Saved as record.pcm (16-bit mono 16kHz)")
