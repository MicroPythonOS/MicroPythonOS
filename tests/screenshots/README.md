# Test Screenshots

This directory contains screenshots captured during graphical tests.

## File Format

Screenshots are saved as raw binary data in RGB565 format:
- 2 bytes per pixel
- For 320x240 screen: 153,600 bytes per file
- Filename format: `{test_name}_{hardware_id}.raw`

## Converting to PNG

### Quick Method (Recommended)

Use the provided convenience script to convert all screenshots:

```bash
cd tests/screenshots
./convert_to_png.sh
```

For custom dimensions:
```bash
./convert_to_png.sh 296 240
```

### Manual Conversion

To view individual screenshots, convert them to PNG using ffmpeg:

```bash
# For 320x240 screenshots (default)
ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 320x240 -i screenshot.raw screenshot.png

# For other sizes (e.g., 296x240 for some hardware)
ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 296x240 -i screenshot.raw screenshot.png
```

## Visual Regression Testing

Screenshots can be used for visual regression testing by:
1. Capturing a "golden" reference screenshot
2. Comparing new screenshots against the reference
3. Detecting visual changes

For pixel-by-pixel comparison, you can use ImageMagick:

```bash
# Convert both to PNG first
ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 320x240 -i reference.raw reference.png
ffmpeg -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s 320x240 -i current.raw current.png

# Compare
compare -metric AE reference.png current.png diff.png
```

## .gitignore

Screenshot files (.raw and .png) are ignored by git to avoid bloating the repository.
Reference/golden screenshots should be stored separately or documented clearly.
