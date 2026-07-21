"""Panel display themes: how preset statuses render on the LED matrix.

"classic" is the flat color card from matrix.compose_preset. The others
re-dress the same status (lines + colors) in a scene — all original,
procedurally-drawn art. Themes apply to preset statuses only; custom
messages, the clock, focus, and media keep their own rendering.
"""
import random

from PIL import Image, ImageDraw

from matrix import PANEL_COLS, PANEL_ROWS, _fit_font, compose_preset

PANEL_THEMES = ("classic", "nameplate", "terminal", "eightbit")


def compose(preset, theme, key=None):
    if theme == "nameplate":
        return _nameplate(preset)
    if theme == "terminal":
        return _terminal(preset)
    if theme == "eightbit":
        return _eightbit(preset, key)
    return compose_preset(preset)


def _nameplate(preset):
    """Skeuomorphic: a brushed-metal shop plate — beveled edges, corner
    screws, the status engraved into the metal, and a glowing indicator
    lamp in the status color."""
    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    pixels = image.load()

    # Brushed metal: horizontal grain, deterministic per-row jitter.
    rng = random.Random(64)
    for y in range(PANEL_ROWS):
        base = 88 + rng.randrange(-6, 7)
        for x in range(PANEL_COLS):
            v = base + rng.randrange(-3, 4)
            pixels[x, y] = (v, v, v + 4)

    # Bevel: lit from the top-left.
    for x in range(PANEL_COLS):
        pixels[x, 0] = (190, 190, 196)
        pixels[x, PANEL_ROWS - 1] = (34, 34, 40)
    for y in range(PANEL_ROWS):
        pixels[0, y] = (170, 170, 176)
        pixels[PANEL_COLS - 1, y] = (40, 40, 46)

    # Corner screws: dark head, light slot.
    for cx, cy in ((3, 3), (PANEL_COLS - 5, 3), (3, PANEL_ROWS - 5),
                   (PANEL_COLS - 5, PANEL_ROWS - 5)):
        draw.ellipse([cx - 1, cy - 1, cx + 2, cy + 2], fill=(52, 52, 58))
        pixels[cx, cy] = (150, 150, 156)
        pixels[cx + 1, cy + 1] = (150, 150, 156)

    # The indicator lamp: a glowing dome in the status color.
    accent = _brighten(preset.get("bg_color", (90, 90, 90)), 1.9)
    dim = tuple(int(c * 0.45) for c in accent)
    lamp_x, lamp_y = 11, PANEL_ROWS // 2
    draw.ellipse([lamp_x - 5, lamp_y - 5, lamp_x + 5, lamp_y + 5], fill=(30, 30, 34))
    draw.ellipse([lamp_x - 4, lamp_y - 4, lamp_x + 4, lamp_y + 4], fill=dim)
    draw.ellipse([lamp_x - 2, lamp_y - 2, lamp_x + 2, lamp_y + 2], fill=accent)
    pixels[lamp_x - 2, lamp_y - 3] = (255, 255, 255)  # specular glint

    # Engraved text: light catch below, dark cut on top.
    lines = [line for line in (preset.get("lines") or []) if line]
    area_x = lamp_x + 8
    area_w = PANEL_COLS - area_x - 4
    font, line_h = _eb_fit(draw, lines, area_w, PANEL_ROWS - 6)
    y = (PANEL_ROWS - line_h * len(lines)) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = area_x + max(0, (area_w - (bbox[2] - bbox[0])) // 2) - bbox[0]
        draw.text((x, y - bbox[1] + 1), line, font=font, fill=(165, 165, 172))
        draw.text((x, y - bbox[1]), line, font=font, fill=(28, 28, 34))
        y += line_h
    return image


def _terminal(preset):
    """Green-phosphor console: a prompt, the status in its own color,
    a block cursor, and scanlines."""
    lines = [line for line in (preset.get("lines") or []) if line]
    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), (0, 7, 0))
    draw = ImageDraw.Draw(image)

    bg = preset.get("bg_color", (0, 90, 0))
    color = tuple(min(255, int(c * 2.2)) for c in bg)
    if max(color) < 60:
        color = (0, 200, 0)
    prompt = (0, 150, 0)

    font, _, line_h = _fit_font(draw, ["> " + lines[0]] + lines[1:], PANEL_COLS - 8, PANEL_ROWS - 8)
    y = (PANEL_ROWS - line_h * len(lines)) // 2
    last_end = 4
    for index, line in enumerate(lines):
        x = 4
        if index == 0:
            draw.text((x, y), ">", font=font, fill=prompt)
            x += int(draw.textlength("> ", font=font))
        draw.text((x, y), line, font=font, fill=color)
        last_end = x + int(draw.textlength(line, font=font))
        y += line_h
    # Block cursor after the final line.
    cursor_y = y - line_h + 1
    draw.rectangle([last_end + 2, cursor_y, last_end + 5, cursor_y + line_h - 3], fill=prompt)

    # Scanlines: dim every other row.
    pixels = image.load()
    for row in range(0, PANEL_ROWS, 2):
        for col in range(PANEL_COLS):
            r, g, b = pixels[col, row]
            pixels[col, row] = (int(r * 0.55), int(g * 0.55), int(b * 0.55))
    return image


# ---- 8-bit --------------------------------------------------------------
# One cohesive pixel-art language for every screen: a dialog-box frame in
# the status accent, a chunky icon, and fitted text. Clock and focus get
# the same treatment (see eightbit_clock / eightbit_focus).

_EB_BG = (4, 4, 10)
_EB_TEXT = (235, 235, 235)

_EB_ICONS = {
    # per-status pixel art; letters index into the palette below
    "on_a_call": (
        ".AAAAAA.",
        "AA....AA",
        "A......A",
        "A......A",
        "AA....AA",
        "BB....BB",
        "BB....BB",
        "......BB",
        "....BBBB",
    ),
    "free": (
        "B..A..B.",
        ".AAAAA..",
        "AAAAAAA.",
        "AAAAAAAB",
        "AAAAAAA.",
        ".AAAAA..",
        "B..A..B.",
    ),
    "in_a_meeting": (
        ".A..B.",
        ".A..B.",
        "AAA.BB",
        "AAABBB",
        "AAABBB",
    ),
    "do_not_disturb": (
        ".AAAA.",
        "AAAAAA",
        "ABBBBA",
        "ABBBBA",
        "AAAAAA",
        ".AAAA.",
    ),
}


def _brighten(color, factor=1.7):
    return tuple(min(255, int(c * factor)) for c in color)


def _eb_fit(draw, lines, max_w, max_h):
    """Like matrix._fit_font but measured with textbbox — textlength
    under-reports a couple of pixels at tiny sizes, and these cards have
    a frame to respect."""
    from matrix import _font

    for size in range(13, 5, -1):
        line_h = size + 2
        if line_h * len(lines) > max_h:
            continue
        font = _font(size)
        widths = [draw.textbbox((0, 0), line, font=font) for line in lines]
        if all(bbox[2] - bbox[0] <= max_w for bbox in widths):
            return font, line_h
    return _font(6), 8


def _stamp(pixels, art, palette, x0, y0, scale=2):
    for row, line in enumerate(art):
        for col, ch in enumerate(line):
            if ch == ".":
                continue
            color = palette[ch]
            for dy in range(scale):
                for dx in range(scale):
                    x, y = x0 + col * scale + dx, y0 + row * scale + dy
                    if 0 <= x < PANEL_COLS and 0 <= y < PANEL_ROWS:
                        pixels[x, y] = color


def _eb_frame(draw, pixels, accent):
    draw.rectangle([0, 0, PANEL_COLS - 1, PANEL_ROWS - 1], outline=accent)
    for cx, cy in ((0, 0), (PANEL_COLS - 2, 0), (0, PANEL_ROWS - 2),
                   (PANEL_COLS - 2, PANEL_ROWS - 2)):
        for dx in range(2):
            for dy in range(2):
                pixels[cx + dx, cy + dy] = accent


def _eb_card(icon_art, palette, accent, lines):
    """Shared 8-bit layout: frame, icon on the left, text on the right."""
    from PIL import ImageDraw

    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), _EB_BG)
    draw = ImageDraw.Draw(image)
    pixels = image.load()
    _eb_frame(draw, pixels, accent)

    icon_w = max(len(line) for line in icon_art) * 2
    icon_h = len(icon_art) * 2
    _stamp(pixels, icon_art, palette, 4, (PANEL_ROWS - icon_h) // 2)

    area_x = 4 + icon_w + 3
    area_w = PANEL_COLS - area_x - 3
    font, line_h = _eb_fit(draw, lines, area_w, PANEL_ROWS - 6)
    y = (PANEL_ROWS - line_h * len(lines)) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = area_x + max(0, (area_w - (bbox[2] - bbox[0])) // 2) - bbox[0]
        draw.text((x, y - bbox[1]), line, font=font, fill=_EB_TEXT)
        y += line_h
    return image


def _eightbit(preset, key):
    accent = _brighten(preset.get("bg_color", (60, 60, 60)))
    lines = [line for line in (preset.get("lines") or []) if line]
    icon = _EB_ICONS.get(key)
    if icon is None:
        # No bespoke icon (shouldn't happen for presets): frame + text only.
        from PIL import ImageDraw
        image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), _EB_BG)
        draw = ImageDraw.Draw(image)
        _eb_frame(draw, image.load(), accent)
        font, line_h = _eb_fit(draw, lines, PANEL_COLS - 8, PANEL_ROWS - 6)
        y = (PANEL_ROWS - line_h * len(lines)) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (PANEL_COLS - (bbox[2] - bbox[0])) // 2 - bbox[0]
            draw.text((x, y - bbox[1]), line, font=font, fill=_EB_TEXT)
            y += line_h
        return image
    palettes = {
        "on_a_call": {"A": accent, "B": (200, 200, 210)},
        "free": {"A": (230, 200, 40), "B": (230, 200, 40)},
        "in_a_meeting": {"A": accent, "B": (210, 160, 60)},
        "do_not_disturb": {"A": accent, "B": (235, 235, 235)},
    }
    return _eb_card(icon, palettes.get(key, {"A": accent, "B": accent}), accent, lines)


_EB_SUN = (
    "B..A..B",
    ".AAAAA.",
    "AAAAAAA",
    ".AAAAA.",
    "B..A..B",
)
_EB_MOON = (
    "..AAA.",
    ".AA...",
    "AA....",
    "AA....",
    ".AA...",
    "..AAA.",
)
_EB_HOURGLASS = (
    "AAAAAA",
    ".BBBB.",
    "..BB..",
    "...B..",
    "..B...",
    "..BB..",
    ".BBBB.",
    "AAAAAA",
)


def eightbit_clock(weather_data, now):
    """The clock & weather screen, 8-bit style: sun or moon by hour,
    big time, and the temperature when known."""
    from PIL import ImageDraw

    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), _EB_BG)
    draw = ImageDraw.Draw(image)
    pixels = image.load()
    accent = (70, 110, 220)
    _eb_frame(draw, pixels, accent)

    daytime = 6 <= now.hour < 19
    icon = _EB_SUN if daytime else _EB_MOON
    palette = {"A": (230, 200, 40) if daytime else (200, 200, 120),
               "B": (230, 200, 40)}
    icon_h = len(icon) * 2
    _stamp(pixels, icon, palette, 4, (PANEL_ROWS - icon_h) // 2)

    time_str = now.strftime("%-I:%M")
    lines = [time_str]
    if weather_data:
        lines.append(f"{round(weather_data['temp'])}°")
    area_x = 4 + max(len(r) for r in icon) * 2 + 3
    area_w = PANEL_COLS - area_x - 3
    font, line_h = _eb_fit(draw, lines, area_w, PANEL_ROWS - 6)
    y = (PANEL_ROWS - line_h * len(lines)) // 2
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = area_x + max(0, (area_w - (bbox[2] - bbox[0])) // 2) - bbox[0]
        color = _EB_TEXT if index == 0 else (150, 160, 190)
        draw.text((x, y - bbox[1]), line, font=font, fill=color)
        y += line_h
    return image


def eightbit_focus(countdown):
    """The focus screen, 8-bit style: hourglass and the ticking clock."""
    return _eb_card(
        _EB_HOURGLASS,
        {"A": (140, 130, 240), "B": (230, 200, 40)},
        (110, 100, 230),
        ["FOCUS", countdown],
    )
