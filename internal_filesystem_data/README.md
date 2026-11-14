This dataset of small data files are here to validate MicroPythonOS' file format support.

The web build ships it as `/.bundled_data` and copies it to `/data` on first
boot; the ESP32-family full images pack the same tree into their internal
filesystem, so a fresh install already has sample media to open.

# Images

- `images/unicorn.png`				PNG image with transparent background
- `images/lenna.jpg`				JPEG image, basic (= non-progressive) profile ([history](https://en.wikipedia.org/wiki/Lenna))
- `images/visible_light_spectrum_rgb565.bmp`	BMP image (RGB565 instead of RGB888 to reduce filesize)

# Video

- `video/big_buck_bunny_critters_320x240.avi`
  320x240 MJPEG at 8 fps with 8000 Hz mono 8-bit PCM audio, 6 seconds,
  ~282 KiB. An excerpt (0:11.5-0:17.5) of *Big Buck Bunny*, (c) 2008 Blender
  Foundation, licensed CC BY 3.0 (https://peach.blender.org).

# Audio

## MP3 files

- `audio/sailors_chant_22k_mono.mp3`
  22050 Hz mono 32 kbps MP3, 18 seconds, ~71 KiB. An excerpt of
  *A sailor's chant* by Thimras (https://opengameart.org/content/a-sailors-chant),
  dedicated to the public domain (CC0 1.0). A sea shanty with harpsichord,
  flutes and voice.

## WAV files

- `audio/O-O.wav`			RIFF (little-endian) data, WAVE audio, mono, 8000 Hz, 8-bit unsigned PCM
- `audio/type.wav`			RIFF (little-endian) data, WAVE audio, mono, 11025 Hz, 16-bit signed little endian, compressed to ADPCM IMA with adpcm-xq

## RTTTL files

- audio/creeps.rtttl
- audio/good_bad_ugly.rtttl
- audio/jungle_book.rtttl
- audio/macarena.rtttl
- audio/mario.rtttl
- audio/megalovania.rtttl
- audio/nokia.rtttl
- audio/star_wars.rtttl
- audio/take_on_me.rtttl
- audio/wilhelm_tell.rtttl

None of the RTTTL files were pruned since they are so tiny; less than 512 bytes each, less than 2 KiB total.
