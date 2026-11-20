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
  ~356 KiB. An excerpt (0:11.5-0:17.5) of *Big Buck Bunny*, (c) 2008 Blender
  Foundation, licensed CC BY 3.0 (https://peach.blender.org).

  Measured stream: 48 frames, 6230 B per frame (0.65 bit/pixel), ~399 kb/s
  video plus 64 kb/s audio. The JPEG quantisation tables are byte-for-byte
  ffmpeg's `-q:v 10` tables. The picture is 16:9 letterboxed into the 4:3
  frame (~183 rows of content, ~29 rows of black top and bottom), inherited
  from the 4:3 source rather than added here. The container was written by
  ffmpeg 5.1 (Lavf59.27.100).

  Regenerated from the 33 s 320x240 4:3 Big Buck Bunny extract
  (`Big_Buck_Bunny_extract.ogv`, Theora, 25 fps). This command reproduces the
  previous `-q:v 16` file byte-for-byte and is what produced the current one
  at `-q:v 10`:

  ```bash
  ffmpeg -ss 11.5 -t 6 -i Big_Buck_Bunny_extract.ogv \
         -vf "fps=8" \
         -c:v mjpeg -q:v 10 -pix_fmt yuvj420p \
         -c:a pcm_u8 -ar 8000 -ac 1 \
         -metadata title="Big Buck Bunny - critters (excerpt)" \
         -metadata comment="Big Buck Bunny (c) 2008 Blender Foundation, CC BY 3.0, peach.blender.org" \
         video/big_buck_bunny_critters_320x240.avi
  ```

  `-q:v 10` is the project standard for MJPEG video, here and in the sibling
  `video_samples` corpus. The scale is ffmpeg's MJPEG
  quantiser multiplier: 1-31, **lower is better**, and it is not comparable
  to x264's `-crf` (where 18 is a typical "transparent" value).
  `-q:v 10` sits between "looks clean" and "stays small"; at 320x240 it is
  roughly x264 `CRF 23` for the same picture. Anything in **6-16 is
  acceptable**: 6 for high quality, 16 for low. Measured on this exact
  source, with the audio and frame rate unchanged:

  | `-q:v` | B/frame | bit/pixel | total | vs `-q:v 10` |
  |--------|---------|-----------|-------|--------------|
  | 6 (high quality) | 8456 | 0.88 | 461 KiB | 1.29x |
  | 8 | 7065 | 0.74 | 395 KiB | 1.11x |
  | **10 (standard)** | **6230** | **0.65** | **356 KiB** | **1.00x** |
  | 12 | 5546 | 0.58 | 324 KiB | 0.91x |
  | 14 | 5060 | 0.53 | 301 KiB | 0.85x |
  | 16 (low quality) | 4644 | 0.48 | 282 KiB | 0.79x |

  Two settings differ from the [Media Player](https://docs.micropythonos.com/apps/media-player/#preparing-clips)
  recipe on purpose, because this tree is packed into the vfs partition of
  the 8 MB images:

  - **8 fps, not 15** — 320x240 tops out near 13.5-14 fps on the badge, so 15
    buys at most 1.9x the frames for 1.9x the bytes. At 8 fps the clip stays
    well inside the ceiling and fits the image comfortably (~292 KiB of video
    against ~548 KiB at 15 fps).
  - **`pcm_u8 -ar 8000`, not `pcm_s16le -ar 22050`** — 4 kHz bandwidth with
    8-bit noise instead of 11 kHz at 16-bit.

  At 6230 B per frame the picture costs ~49 kB per second of video. The
  letterbox bars cost only ~4 kB/s of that, because flat black codes to
  almost nothing, but the player still decodes and presents all 240 rows:
  cropping to 320x180 saves ~23 KiB and 25% of the decode and present work,
  at the price of losing the 16:9 framing (the player centres a smaller clip).

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
