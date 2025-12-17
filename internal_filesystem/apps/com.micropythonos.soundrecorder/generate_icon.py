#!/usr/bin/env python3
"""
Generate a 64x64 icon for the Sound Recorder app.
Creates a microphone icon with transparent background.

Run this script to generate the icon:
    python3 generate_icon.py

The icon will be saved to res/mipmap-mdpi/icon_64x64.png
"""

import os
from PIL import Image, ImageDraw

def generate_icon():
    # Create a 64x64 image with transparent background
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Colors
    mic_color = (220, 50, 50, 255)  # Red microphone
    mic_dark = (180, 40, 40, 255)   # Darker red for shading
    stand_color = (80, 80, 80, 255)  # Gray stand
    highlight = (255, 100, 100, 255)  # Light red highlight
    
    # Microphone head (rounded rectangle / ellipse)
    mic_top = 8
    mic_bottom = 36
    mic_left = 20
    mic_right = 44
    
    # Draw microphone body (rounded top)
    draw.ellipse([mic_left, mic_top, mic_right, mic_top + 16], fill=mic_color)
    draw.rectangle([mic_left, mic_top + 8, mic_right, mic_bottom], fill=mic_color)
    draw.ellipse([mic_left, mic_bottom - 8, mic_right, mic_bottom + 8], fill=mic_color)
    
    # Microphone grille lines (horizontal lines on mic head)
    for y in range(mic_top + 6, mic_bottom - 4, 4):
        draw.line([(mic_left + 4, y), (mic_right - 4, y)], fill=mic_dark, width=1)
    
    # Highlight on left side of mic
    draw.arc([mic_left + 2, mic_top + 2, mic_left + 10, mic_top + 18], 
             start=120, end=240, fill=highlight, width=2)
    
    # Microphone stand (curved arc under the mic)
    stand_top = mic_bottom + 4
    stand_width = 8
    
    # Vertical stem from mic
    stem_x = size // 2
    draw.rectangle([stem_x - 2, mic_bottom, stem_x + 2, stand_top + 8], fill=stand_color)
    
    # Curved holder around mic bottom
    draw.arc([mic_left - 4, mic_bottom - 8, mic_right + 4, mic_bottom + 16], 
             start=0, end=180, fill=stand_color, width=3)
    
    # Stand base
    base_y = 54
    draw.rectangle([stem_x - 2, stand_top + 8, stem_x + 2, base_y], fill=stand_color)
    draw.ellipse([stem_x - 12, base_y - 2, stem_x + 12, base_y + 6], fill=stand_color)
    
    # Recording indicator (red dot with glow effect)
    dot_x, dot_y = 52, 12
    dot_radius = 5
    
    # Glow effect
    for r in range(dot_radius + 3, dot_radius, -1):
        alpha = int(100 * (dot_radius + 3 - r) / 3)
        glow_color = (255, 0, 0, alpha)
        draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=glow_color)
    
    # Solid red dot
    draw.ellipse([dot_x - dot_radius, dot_y - dot_radius, 
                  dot_x + dot_radius, dot_y + dot_radius], 
                 fill=(255, 50, 50, 255))
    
    # White highlight on dot
    draw.ellipse([dot_x - 2, dot_y - 2, dot_x, dot_y], fill=(255, 200, 200, 255))
    
    # Ensure output directory exists
    output_dir = 'res/mipmap-mdpi'
    os.makedirs(output_dir, exist_ok=True)
    
    # Save the icon
    output_path = os.path.join(output_dir, 'icon_64x64.png')
    img.save(output_path, 'PNG')
    print(f"Icon saved to {output_path}")
    
    return img

if __name__ == '__main__':
    generate_icon()