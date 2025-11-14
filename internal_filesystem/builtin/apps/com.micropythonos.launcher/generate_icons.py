#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont

def create_trashcan_icon():
    """Create a 64x64 trashcan icon"""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw trash can lid
    draw.rectangle([(16, 18), (48, 22)], fill='#E74C3C', outline='#C0392B', width=2)

    # Draw trash can body (trapezoid shape)
    draw.polygon([(20, 24), (44, 24), (46, 54), (18, 54)], fill='#E74C3C', outline='#C0392B')

    # Draw vertical lines on trash can body
    draw.line([(26, 28), (24, 50)], fill='#C0392B', width=2)
    draw.line([(32, 28), (32, 50)], fill='#C0392B', width=2)
    draw.line([(38, 28), (40, 50)], fill='#C0392B', width=2)

    # Draw lid handle
    draw.arc([(26, 12), (38, 20)], start=0, end=180, fill='#C0392B', width=2)

    # Save to res/mipmap-mdpi directory
    img.save('res/mipmap-mdpi/trashcan_icon.png', 'PNG', optimize=True)
    print("Trashcan icon saved as res/mipmap-mdpi/trashcan_icon.png")

def create_exit_icon():
    """Create a 64x64 exit/close icon"""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw circle background
    draw.ellipse([(12, 12), (52, 52)], fill='#3498DB', outline='#2980B9', width=2)

    # Draw X (two diagonal lines)
    draw.line([(24, 24), (40, 40)], fill='#FFFFFF', width=4)
    draw.line([(40, 24), (24, 40)], fill='#FFFFFF', width=4)

    # Save to res/mipmap-mdpi directory
    img.save('res/mipmap-mdpi/exit_icon.png', 'PNG', optimize=True)
    print("Exit icon saved as res/mipmap-mdpi/exit_icon.png")

if __name__ == '__main__':
    create_trashcan_icon()
    create_exit_icon()
    print("All icons generated successfully!")
