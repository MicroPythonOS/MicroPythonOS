#!/usr/bin/env python3
from PIL import Image, ImageDraw

# Create 64x64 icon
img = Image.new('RGB', (64, 64), color=(52, 73, 94))
draw = ImageDraw.Draw(img)

# Draw blue board
draw.rectangle([4, 4, 60, 60], fill=(52, 152, 219))

# Draw grid of circles with a pattern
colors = [(231, 76, 60), (241, 196, 15), (44, 62, 80)]  # Red, Yellow, Empty

pattern = [
    [2, 2, 2, 2, 2, 2, 2],
    [2, 2, 2, 2, 2, 2, 2],
    [2, 2, 0, 0, 2, 2, 2],
    [2, 0, 0, 1, 2, 2, 2],
    [0, 1, 0, 1, 0, 2, 2],
    [0, 1, 1, 0, 0, 1, 2],
]

cell_size = 8
start_x = 8
start_y = 8

for row in range(6):
    for col in range(7):
        x = start_x + col * cell_size
        y = start_y + row * cell_size
        draw.ellipse([x, y, x + 6, y + 6], fill=colors[pattern[row][col]])

img.save('res/mipmap-mdpi/icon_64x64.png')
print("Icon created: res/mipmap-mdpi/icon_64x64.png")
