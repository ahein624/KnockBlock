"""Generate the PWA app icons into static/.

Run once after deploying (any machine with Pillow):
    ./venv/bin/python3 make_icons.py

The icon is the AH. monogram over a row of dots — a nod to the LED panel
itself, in AH Field System materials (the hi-vis dot is the view's one
allowed orange).
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STATIC_DIR = Path(__file__).resolve().parent / "static"
DOT_COLORS = ["#57543E", "#B3A180", "#E4DDC9", "#FF5C1C"]
BACKGROUND = "#191710"
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_icon(size, rounded=True):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(size * 0.22) if rounded else 0
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BACKGROUND)

    # "AH." monogram, slightly above center.
    font = _font(int(size * 0.34))
    bbox = draw.textbbox((0, 0), "AH.", font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - text_w) / 2 - bbox[0], size * 0.42 - text_h / 2 - bbox[1]),
        "AH.",
        font=font,
        fill="#B3A180",
    )

    # Status-color dots underneath, like a lit pixel row.
    dot_radius = size * 0.052
    spacing = size * 0.16
    start_x = size / 2 - spacing * 1.5
    cy = size * 0.70
    for i, color in enumerate(DOT_COLORS):
        cx = start_x + spacing * i
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
