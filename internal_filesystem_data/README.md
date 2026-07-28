This dataset of small data files are here to validate MicroPythonOS' file format support.


# Images

- `images/unicorn.png`				PNG image with transparent background
- `images/lenna.jpg`				JPEG image, basic (= non-progressive) profile ([history](https://en.wikipedia.org/wiki/Lenna))
- `images/visible_light_spectrum_rgb565.bmp`	BMP image (RGB565 instead of RGB888 to reduce filesize)

# Audio

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
