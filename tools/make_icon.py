#!/usr/bin/env python3
"""
Generate images/AppIcon.png — the pyExamKit app icon (a filled bubble-answer grid).

After editing, regenerate the shipped .icns/.ico from the new PNG:

    uv run python tools/make_icon.py
    tools/build_icon_formats.sh
"""
from pathlib import Path

from PIL import Image, ImageDraw

SCALE = 4
BASE = 1024
SIZE = BASE * SCALE

TOP = (58, 110, 165)      # #3A6EA5
BOTTOM = (24, 52, 78)      # #18344E

FILLED = {(0, 1), (1, 3), (2, 0), (2, 2)}
COLS, ROWS = 4, 3

OUT_PATH = Path(__file__).resolve().parent.parent / "images" / "AppIcon.png"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    grad_col = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        grad_col.putpixel((0, y), lerp(TOP, BOTTOM, y / (SIZE - 1)))
    grad = grad_col.resize((SIZE, SIZE))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, SIZE - 1, SIZE - 1], radius=int(0.205 * SIZE), fill=255
    )
    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)
    circle_d = int(0.137 * SIZE)
    gap = int(0.049 * SIZE)
    grid_w = COLS * circle_d + (COLS - 1) * gap
    grid_h = ROWS * circle_d + (ROWS - 1) * gap
    start_x = (SIZE - grid_w) // 2
    start_y = (SIZE - grid_h) // 2
    stroke_w = max(2, int(circle_d * 0.065))

    for r in range(ROWS):
        for c in range(COLS):
            x0 = start_x + c * (circle_d + gap)
            y0 = start_y + r * (circle_d + gap)
            x1, y1 = x0 + circle_d, y0 + circle_d
            if (r, c) in FILLED:
                draw.ellipse([x0, y0, x1, y1], fill=(255, 255, 255, 255))
            else:
                draw.ellipse([x0, y0, x1, y1], outline=(255, 255, 255, 255), width=stroke_w)

    return img.resize((BASE, BASE), Image.LANCZOS)


if __name__ == "__main__":
    render().save(OUT_PATH)
    print(f"wrote {OUT_PATH}")
