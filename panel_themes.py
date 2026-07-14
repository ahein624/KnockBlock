"""Panel display themes: how preset statuses render on the LED matrix.

"classic" is the flat color card from matrix.compose_preset. The others
re-dress the same status (lines + colors) in a scene — all original,
procedurally-drawn art. Themes apply to preset statuses only; custom
messages, the clock, focus, and media keep their own rendering.
"""
from PIL import Image, ImageDraw

import media
from matrix import PANEL_COLS, PANEL_ROWS, _fit_font, compose_preset

PANEL_THEMES = ("classic", "overworld", "terminal")


def compose(preset, theme):
    if theme == "overworld":
        return _overworld(preset)
    if theme == "terminal":
        return _terminal(preset)
    return compose_preset(preset)


def _overworld(preset):
    """The status on a floating block over the arcade world.

    Each status picks a deterministic frame of the loop, so ON A CALL and
    FREE hang over different stretches of the level (and the runner and
    coins come along for free)."""
    lines = [line for line in (preset.get("lines") or []) if line]
    seed = sum(ord(c) for c in "".join(lines)) % media.ARCADE_FRAME_COUNT
    image = media.arcade_frames()[seed][0].copy()
    draw = ImageDraw.Draw(image)

    font, _, line_h = _fit_font(draw, lines, PANEL_COLS - 16, 18)
    text_w = max(draw.textlength(line, font=font) for line in lines)
    box_w = int(text_w) + 9
    box_h = line_h * len(lines) + 5
    x0 = (PANEL_COLS - box_w) // 2
    y0 = 2
    # The floating block: status color fill, pale face like a coin block.
    draw.rectangle([x0, y0, x0 + box_w, y0 + box_h],
                   fill=tuple(preset.get("bg_color", (0, 0, 0))),
                   outline=(235, 225, 200))
    text_color = tuple(preset.get("text_color", (255, 255, 255)))
    y = y0 + 3
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = x0 + (box_w - (bbox[2] - bbox[0])) // 2 - bbox[0]
        draw.text((x, y - bbox[1]), line, font=font, fill=text_color)
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
