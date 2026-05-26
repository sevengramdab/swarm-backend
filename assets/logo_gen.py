#!/usr/bin/env python3
"""Generate SimplePod Swarm logo and icon."""
from PIL import Image, ImageDraw, ImageFont
import math

SIZE = 512
CENTER = SIZE // 2

img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Background circle with gradient-like fill (simulated with concentric circles)
for r in range(240, 0, -2):
    ratio = r / 240
    # Blue to purple gradient
    r_col = int(30 + (80 - 30) * ratio)
    g_col = int(60 + (40 - 60) * ratio)
    b_col = int(140 + (200 - 140) * ratio)
    draw.ellipse(
        [CENTER - r, CENTER - r, CENTER + r, CENTER + r],
        fill=(r_col, g_col, b_col, 255)
    )

# Central hexagon (the "pod")
hex_radius = 70
hex_points = []
for i in range(6):
    angle = math.pi / 3 * i - math.pi / 6
    x = CENTER + hex_radius * math.cos(angle)
    y = CENTER + hex_radius * math.sin(angle)
    hex_points.append((x, y))
draw.polygon(hex_points, fill=(255, 255, 255, 230), outline=(200, 220, 255, 255), width=3)

# Orbiting nodes (the "swarm") — 6 small circles around the hexagon
node_radius = 22
orbit_radius = 140
for i in range(6):
    angle = math.pi / 3 * i
    nx = CENTER + orbit_radius * math.cos(angle)
    ny = CENTER + orbit_radius * math.sin(angle)
    # Node body
    draw.ellipse(
        [nx - node_radius, ny - node_radius, nx + node_radius, ny + node_radius],
        fill=(100, 200, 255, 220),
        outline=(255, 255, 255, 200),
        width=2
    )
    # Connection line to center
    draw.line([(CENTER, CENTER), (nx, ny)], fill=(150, 180, 255, 120), width=2)

# Outer glow ring
draw.ellipse(
    [CENTER - 248, CENTER - 248, CENTER + 248, CENTER + 248],
    outline=(120, 160, 255, 80),
    width=3
)

# Save PNG
img.save('assets/simplepod_logo.png')

# Save ICO (multi-resolution)
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
icons = []
for w, h in icon_sizes:
    icon = img.resize((w, h), Image.Resampling.LANCZOS)
    icons.append(icon)

icons[0].save(
    'assets/simplepod_logo.ico',
    format='ICO',
    sizes=[(i.width, i.height) for i in icons],
    append_images=icons[1:]
)

print("Logo generated:")
print("  PNG: assets/simplepod_logo.png")
print("  ICO: assets/simplepod_logo.ico")
