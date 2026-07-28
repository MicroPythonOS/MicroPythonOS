This dataset of small data files are here to validate MicroPythonOS' file format support.

Audio:
=====

audio/O-O.wav			RIFF (little-endian) data, WAVE audio, mono at 8000 Hz, 8-bit unsigned PCM
audio/type.wav			RIFF (little-endian) data, WAVE audio, mono at 11025 Hz, 16-bit signed little endian, compressed with ADPCM IMA with adpcm-xq

The RTTTL files are so small (less than 512 bytes each, less than 2 KiB total) so it's not necessary to prune them:

audio/creeps.rtttl
audio/good_bad_ugly.rtttl
audio/jungle_book.rtttl
audio/macarena.rtttl
audio/mario.rtttl
audio/megalovania.rtttl
audio/nokia.rtttl
audio/star_wars.rtttl
audio/take_on_me.rtttl
audio/wilhelm_tell.rtttl

Images:
=======

./images/unicorn.png				PNG image with transparent background
./images/lenna.jpg				basic (non-progressive) JPEG image
./images/visible_light_spectrum_rgb565.bmp	RGB565 BMP image
