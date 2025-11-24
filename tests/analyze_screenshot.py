#!/usr/bin/env python3
"""
Analyze RGB565 screenshots for color correctness.

Usage:
    python3 analyze_screenshot.py screenshot.raw [width] [height]

Checks:
- Color channel distribution (detect pale/washed out colors)
- Histogram analysis
- Average brightness
- Color saturation levels
"""

import sys
import struct
from pathlib import Path

def rgb565_to_rgb888(pixel):
    """Convert RGB565 pixel to RGB888."""
    r5 = (pixel >> 11) & 0x1F
    g6 = (pixel >> 5) & 0x3F
    b5 = pixel & 0x1F

    r8 = (r5 << 3) | (r5 >> 2)
    g8 = (g6 << 2) | (g6 >> 4)
    b8 = (b5 << 3) | (b5 >> 2)

    return r8, g8, b8

def analyze_screenshot(filepath, width=320, height=240):
    """Analyze RGB565 screenshot file."""
    print(f"Analyzing: {filepath}")
    print(f"Dimensions: {width}x{height}")

    # Read raw data
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        return

    expected_size = width * height * 2
    if len(data) != expected_size:
        print(f"ERROR: File size mismatch. Expected {expected_size}, got {len(data)}")
        print(f"  Note: Expected size is for {width}x{height} RGB565 format")
        return

    # Parse RGB565 pixels
    pixels = []
    for i in range(0, len(data), 2):
        # Little-endian RGB565
        pixel = struct.unpack('<H', data[i:i+2])[0]
        r, g, b = rgb565_to_rgb888(pixel)
        pixels.append((r, g, b))

    # Convert to simple list of lists for statistics
    red_values = [p[0] for p in pixels]
    green_values = [p[1] for p in pixels]
    blue_values = [p[2] for p in pixels]

    # Statistics
    print(f"\nColor Channel Statistics:")
    print(f"  Red   - min: {min(red_values):3d}, max: {max(red_values):3d}, avg: {sum(red_values)/len(red_values):.1f}")
    print(f"  Green - min: {min(green_values):3d}, max: {max(green_values):3d}, avg: {sum(green_values)/len(green_values):.1f}")
    print(f"  Blue  - min: {min(blue_values):3d}, max: {max(blue_values):3d}, avg: {sum(blue_values)/len(blue_values):.1f}")

    # Check for pale colors (low saturation)
    avg_brightness = (sum(red_values) + sum(green_values) + sum(blue_values)) / (len(pixels) * 3)

    # Calculate average saturation (max channel - min channel for each pixel)
    saturations = []
    for r, g, b in pixels:
        max_channel = max(r, g, b)
        min_channel = min(r, g, b)
        saturations.append(max_channel - min_channel)

    max_channel_diff = sum(saturations) / len(saturations)

    print(f"\nQuality Metrics:")
    print(f"  Average brightness: {avg_brightness:.1f}")
    print(f"  Average saturation: {max_channel_diff:.1f}")

    if max_channel_diff < 30:
        print("  ⚠ WARNING: Low saturation detected (colors may appear pale/washed out)")

    if avg_brightness > 200:
        print("  ⚠ WARNING: Very high brightness (overexposed)")
    elif avg_brightness < 40:
        print("  ⚠ WARNING: Very low brightness (underexposed)")

    # Simple histogram (10 bins)
    print(f"\nChannel Histograms:")
    for channel_name, channel_values in [('Red', red_values), ('Green', green_values), ('Blue', blue_values)]:
        print(f"  {channel_name}:")

        # Create 10 bins
        bins = [0] * 10
        for val in channel_values:
            bin_idx = min(9, val // 26)  # 256 / 10 ≈ 26
            bins[bin_idx] += 1

        for i, count in enumerate(bins):
            bar_length = int((count / len(channel_values)) * 50)
            bar = '█' * bar_length
            bin_start = i * 26
            bin_end = (i + 1) * 26 - 1
            print(f"    {bin_start:3d}-{bin_end:3d}: {bar} ({count})")

    # Detect common YUV conversion issues
    print(f"\nYUV Conversion Checks:")

    # Check if colors are clamped (many pixels at 0 or 255)
    clamped_count = sum(1 for r, g, b in pixels if r == 0 or r == 255 or g == 0 or g == 255 or b == 0 or b == 255)
    total_pixels = len(pixels)
    clamp_percent = (clamped_count / total_pixels) * 100
    print(f"  Clamped pixels: {clamp_percent:.1f}%")
    if clamp_percent > 5:
        print("  ⚠ WARNING: High clamp rate suggests color conversion overflow")

    # Check for green tint (common YUYV issue)
    avg_red = sum(red_values) / len(red_values)
    avg_green = sum(green_values) / len(green_values)
    avg_blue = sum(blue_values) / len(blue_values)

    green_dominance = avg_green - ((avg_red + avg_blue) / 2)
    if green_dominance > 20:
        print(f"  ⚠ WARNING: Green channel dominance ({green_dominance:.1f}) - possible YUYV U/V swap")

    # Sample pixels for visual inspection
    print(f"\nSample Pixels (first 10):")
    for i in range(min(10, len(pixels))):
        r, g, b = pixels[i]
        print(f"  Pixel {i}: RGB({r:3d}, {g:3d}, {b:3d})")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_screenshot.py <screenshot.raw> [width] [height]")
        print("")
        print("Examples:")
        print("  python3 analyze_screenshot.py camera_capture.raw")
        print("  python3 analyze_screenshot.py camera_640x480.raw 640 480")
        sys.exit(1)

    filepath = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 320
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 240

    analyze_screenshot(filepath, width, height)
