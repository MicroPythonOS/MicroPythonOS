#!/usr/bin/env python3
"""
Generate a 64x64 PNG icon with transparent background for the "ShowFonts" app.
The icon features a stylized bold 'F' with a subtle font preview overlay,
using modern flat design with vibrant colors.
"""

import cairo
from pathlib import Path

def create_showfonts_icon(output_path: str = "ShowFonts_icon.png"):
    # Icon dimensions
    WIDTH, HEIGHT = 64, 64
    RADIUS = 12  # Corner radius for rounded square background
    
    # Create surface with alpha channel
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    ctx = cairo.Context(surface)
    
    # Fully transparent background
    ctx.set_source_rgba(0, 0, 0, 0)
    ctx.paint()
    
    # === Draw subtle rounded background (optional soft glow base) ===
    ctx.save()
    rounded_rect(ctx, 4, 4, 56, 56, RADIUS)
    ctx.set_source_rgba(0.1, 0.1, 0.1, 0.15)  # Very subtle dark overlay
    ctx.fill()
    ctx.restore()
    
    # === Main colorful gradient background ===
    ctx.save()
    rounded_rect(ctx, 6, 6, 52, 52, RADIUS - 2)
    
    # Create radial gradient for depth
    grad = cairo.RadialGradient(32, 20, 5, 32, 32, 30)
    grad.add_color_stop_rgb(0, 0.25, 0.6, 1.0)      # Bright blue center
    grad.add_color_stop_rgb(0.7, 0.1, 0.4, 0.9)      # Mid tone
    grad.add_color_stop_rgb(1, 0.05, 0.25, 0.7)     # Deep blue edge
    ctx.set_source(grad)
    ctx.fill()
    ctx.restore()
    
    # === Draw bold stylized 'F' ===
    ctx.save()
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(38)
    
    # Position 'F' centered
    x_bearing, y_bearing, text_width, text_height = ctx.text_extents("F")[:4]
    x = 32 - text_width / 2 - x_bearing
    y = 38 - text_height / 2 - y_bearing
    
    ctx.move_to(x, y)
    ctx.set_source_rgb(1.0, 1.0, 1.0)  # Pure white
    ctx.show_text("F")
    ctx.restore()
    
    # === Add small font preview overlay (Aa) ===
    ctx.save()
    ctx.select_font_face("Serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(11)
    
    extents = ctx.text_extents("Aa")
    x = 32 - extents.width / 2 - extents.x_bearing
    y = 50 - extents.height / 2 - extents.y_bearing
    
    # Shadow for depth
    ctx.move_to(x + 0.5, y + 0.5)
    ctx.set_source_rgba(0, 0, 0, 0.3)
    ctx.show_text("Aa")
    
    # Main text
    ctx.move_to(x, y)
    ctx.set_source_rgb(1.0, 1.0, 0.7)  # Light yellow
    ctx.show_text("Aa")
    ctx.restore()
    
    # === Add subtle highlight on 'F' ===
    ctx.save()
    ctx.set_line_width(1.5)
    ctx.set_source_rgba(1, 1, 1, 0.4)
    
    # Top bar highlight
    ctx.move_to(14, 20)
    ctx.line_to(26, 20)
    ctx.stroke()
    
    # Middle bar highlight
    ctx.move_to(14, 29)
    ctx.line_to(23, 29)
    ctx.stroke()
    ctx.restore()
    
    # Save to PNG
    surface.write_to_png(output_path)
    print(f"Icon saved to: {Path(output_path).resolve()}")

def rounded_rect(ctx, x, y, width, height, radius):
    """Draw a rounded rectangle path"""
    from math import pi
    ctx.move_to(x + radius, y)
    ctx.arc(x + width - radius, y + radius, radius, pi * 1.5, pi * 2)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, pi * 0.5)
    ctx.arc(x + radius, y + height - radius, radius, pi * 0.5, pi)
    ctx.arc(x + radius, y + radius, radius, pi, pi * 1.5)
    ctx.close_path()

if __name__ == "__main__":
    create_showfonts_icon()
