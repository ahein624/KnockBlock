"""Generate the PWA app icons into static/.

Run once after deploying (any machine with Pillow):
    ./venv/bin/python3 make_icons.py

The icon is a dark rounded square with a 2x2 grid of dots in the four
status colors — a nod to the LED panel itself.
"""
from pathlib import Path

from PIL import Image, ImageDraw

STATIC_DIR = Path(__file__).resolve().parent / "static"
DOT_COLORS = ["#e5484d", "#30a46c", "#e8912d", "#8e4ec6"]
BACKGROUND = "#16181d"


def draw_icon(size, rounded=True):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(size * 0.22) if rounded else 0
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BACKGROUND)

    offset = size * 0.15
    dot_radius = size * 0.105
    centers = [
        (size / 2 - offset, size / 2 - offset),
        (size / 2 + offset, size / 2 - offset),
        (size / 2 - offset, size / 2 + offset),
        (size / 2 + offset, size / 2 + offset),
    ]
    for (cx, cy), color in zip(centers, DOT_COLORS):
        draw.ellipse(
            [cx - dot_radius, cy - dot_radius, cx + dot_radius, cy + dot_radius],
            fill=color,
        )
    return image


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    draw_icon(512).save(STATIC_DIR / "icon-512.png")
    draw_icon(192).save(STATIC_DIR / "icon-192.png")
    # iOS applies its own corner rounding and dislikes transparency.
    draw_icon(180, rounded=False).convert("RGB").save(STATIC_DIR / "apple-touch-icon.png")
    print(f"Icons written to {STATIC_DIR}")


if __name__ == "__main__":
    main()
