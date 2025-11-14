#!/bin/bash

# Convert raw RGB565 screenshots to PNG format
# This script converts all .raw files in the current directory to PNG using ffmpeg

# Default dimensions (can be overridden with arguments)
WIDTH=320
HEIGHT=240

# Parse command line arguments
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [width] [height]"
    echo
    echo "Convert all .raw screenshot files to PNG format."
    echo
    echo "Arguments:"
    echo "  width   Screen width in pixels (default: 320)"
    echo "  height  Screen height in pixels (default: 240)"
    echo
    echo "Examples:"
    echo "  $0              # Convert with default 320x240"
    echo "  $0 296 240      # Convert with custom dimensions"
    echo
    exit 0
fi

if [ -n "$1" ]; then
    WIDTH="$1"
fi

if [ -n "$2" ]; then
    HEIGHT="$2"
fi

# Check if ffmpeg is available
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: ffmpeg is not installed or not in PATH"
    echo "Please install ffmpeg to convert screenshots"
    exit 1
fi

# Count .raw files
raw_count=$(find . -maxdepth 1 -name "*.raw" | wc -l)

if [ $raw_count -eq 0 ]; then
    echo "No .raw files found in current directory"
    exit 0
fi

echo "Converting $raw_count screenshot(s) from RGB565 to PNG..."
echo "Dimensions: ${WIDTH}x${HEIGHT}"
echo

converted=0
failed=0

# Convert each .raw file to .png
for raw_file in *.raw; do
    [ -e "$raw_file" ] || continue  # Skip if no .raw files exist

    png_file="${raw_file%.raw}.png"

    echo -n "Converting $raw_file -> $png_file ... "

    if ffmpeg -y -v quiet -vcodec rawvideo -f rawvideo -pix_fmt rgb565 -s ${WIDTH}x${HEIGHT} -i "$raw_file" "$png_file" 2>/dev/null; then
        echo "✓"
        converted=$((converted + 1))
    else
        echo "✗ FAILED"
        failed=$((failed + 1))
    fi
done

echo
echo "Conversion complete: $converted succeeded, $failed failed"

if [ $converted -gt 0 ]; then
    echo
    echo "PNG files created:"
    ls -lh *.png 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
fi
