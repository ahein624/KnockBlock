"""Renders status presets to the Waveshare 64x32 HUB75 panel.

Image composition (compose_preset, build_message_preset) works anywhere
Pillow is installed, so screens can be previewed as PNGs without hardware.
Only MatrixDisplay needs the `rgbmatrix` C extension built from
hzeller/rpi-rgb-led-matrix — see README.md.
"""
import os
import re
import threading

from PIL import Image, ImageDraw, ImageFont

from presets import DEFAULT_MESSAGE_COLOR, MESSAGE_COLORS

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
except ImportError:
    RGBMatrix = None

PANEL_ROWS = 32
PANEL_COLS = 64
CHAIN_LENGTH = 1
PARALLEL = 1

# Generic HUB75 adapter board wired straight to the 40-pin header (no HAT
# level-shifter IC). Verified working on this panel: slowdown 4 fixes the
# "two white lines" garble, RBG fixes green rendering as blue.
HARDWARE_MAPPING = "regular"
GPIO_SLOWDOWN = 4
LED_RGB_SEQUENCE = "RBG"
DEFAULT_BRIGHTNESS = 70

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
EMOJI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
]
# Noto Color Emoji is a bitmap (CBDT) font whose strikes only exist at one
# size; FreeType requires opening it at exactly 109px, then we scale down.
EMOJI_FONT_SIZE = 109

ICON_PX_SINGLE = 22  # emoji size next to one line of text
ICON_PX_MULTI = 16  # emoji size next to two+ lines
MIN_TEXT_SIZE_WITH_ICON = 7  # below this, drop the emoji and use full width

_FONT_CACHE = {}
_EMOJI_CACHE = {}

# Leading emoji in a custom message becomes the icon; the rest is the text.
_EMOJI_RE = re.compile(
    "^(?P<emoji>(?:[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF"
    "☀-➿⬀-⯿️‍])+)\\s*(?P<rest>.*)$",
    re.DOTALL,
)


def _font(size):
    if size not in _FONT_CACHE:
        font = None
        for path in FONT_CANDIDATES:
            if os.path.exists(path):
                font = ImageFont.truetype(path, size)
                break
        _FONT_CACHE[size] = font or ImageFont.load_default()
    return _FONT_CACHE[size]


def _emoji_image(emoji, px):
    """Render an emoji to an RGBA image px tall, or None if unavailable."""
    key = (emoji, px)
    if key in _EMOJI_CACHE:
        return _EMOJI_CACHE[key]

    result = None
    for path in EMOJI_FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            font = ImageFont.truetype(path, EMOJI_FONT_SIZE)
            canvas = Image.new("RGBA", (EMOJI_FONT_SIZE * 2, EMOJI_FONT_SIZE * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((8, 8), emoji, font=font, embedded_color=True)
            bbox = canvas.getbbox()
            if bbox is None:
                break
            cropped = canvas.crop(bbox)
            scale = px / max(cropped.width, cropped.height)
            result = cropped.resize(
                (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))),
                Image.LANCZOS,
            )
        except (OSError, ValueError):
            result = None
        break

    _EMOJI_CACHE[key] = result
    return result


def _fit_font(draw, lines, max_w, max_h):
    """Largest font size where every line fits max_w and the block fits max_h."""
    for size in range(14, 5, -1):
        line_h = size + 2
        if line_h * len(lines) > max_h:
            continue
        font = _font(size)
        if all(draw.textlength(line, font=font) <= max_w for line in lines):
            return font, size, line_h
    return _font(6), 6, 8


def _wrap_greedy(words, font, draw, max_w):
    """Greedy word wrap; None if any single word can't fit at this size."""
    lines = []
    current = ""
    for word in words:
        if draw.textlength(word, font=font) > max_w:
            return None
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wrap_text(text, max_w=PANEL_COLS - 4, max_lines=3):
    words = text.split()
    if not words:
        return []
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(13, 5, -1):
        font = _font(size)
        lines = _wrap_greedy(words, font, draw, max_w)
        if (
            lines is not None
            and len(lines) <= max_lines
            and (size + 2) * len(lines) <= PANEL_ROWS - 2
        ):
            return lines

    # Nothing fits by word-wrapping alone: hard-break by characters at the
    # smallest size and ellipsize the overflow.
    font = _font(6)
    text = " ".join(words)
    lines = []
    current = ""
    for i, ch in enumerate(text):
        if draw.textlength(current + ch, font=font) <= max_w:
            current += ch
        else:
            lines.append(current)
            current = ch
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and current:
        lines.append(current)
    elif current:
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def compose_preset(preset):
    """Compose a preset dict into a 64x32 RGB image."""
    bg = tuple(preset.get("bg_color", (0, 0, 0)))
    text_color = tuple(preset.get("text_color", (255, 255, 255)))
    lines = [line for line in (preset.get("lines") or []) if line]
    emoji = preset.get("emoji")

    image = Image.new("RGB", (PANEL_COLS, PANEL_ROWS), bg)
    draw = ImageDraw.Draw(image)

    icon = None
    if emoji:
        if not lines:
            icon = _emoji_image(emoji, PANEL_ROWS - 6)
        else:
            icon = _emoji_image(emoji, ICON_PX_SINGLE if len(lines) == 1 else ICON_PX_MULTI)

    if not lines:
        if icon:
            image.paste(
                icon,
                ((PANEL_COLS - icon.width) // 2, (PANEL_ROWS - icon.height) // 2),
                icon,
            )
        return image

    if icon:
        area_x = 2 + icon.width + 3
        area_w = PANEL_COLS - area_x - 2
        font, size, line_h = _fit_font(draw, lines, area_w, PANEL_ROWS - 2)
        if size < MIN_TEXT_SIZE_WITH_ICON:
            icon = None
        else:
            image.paste(icon, (2, (PANEL_ROWS - icon.height) // 2), icon)
    if not icon:
        area_x = 2
        area_w = PANEL_COLS - 4
        font, size, line_h = _fit_font(draw, lines, area_w, PANEL_ROWS - 2)

    y = (PANEL_ROWS - line_h * len(lines)) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = area_x + max(0, (area_w - text_w) // 2) - bbox[0]
        text_y = y + (line_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((x, text_y), line, font=font, fill=text_color)
        y += line_h
    return image


def build_message_preset(text, color_name):
    """Turn a custom message into a renderable preset dict.

    A leading emoji becomes the icon; the remainder is wrapped to fit.
    """
    colors = MESSAGE_COLORS.get(color_name) or MESSAGE_COLORS[DEFAULT_MESSAGE_COLOR]
    emoji = None
    match = _EMOJI_RE.match(text.strip())
    if match and match.group("emoji"):
        if _emoji_image(match.group("emoji"), ICON_PX_SINGLE) is not None:
            emoji = match.group("emoji")
            text = match.group("rest").strip()
    return {
        "lines": _wrap_text(text),
        "bg_color": tuple(colors["led"]),
        "text_color": (255, 255, 255),
        "emoji": emoji,
    }


def _build_options(brightness):
    options = RGBMatrixOptions()
    options.rows = PANEL_ROWS
    options.cols = PANEL_COLS
    options.chain_length = CHAIN_LENGTH
    options.parallel = PARALLEL
    options.hardware_mapping = HARDWARE_MAPPING
    options.gpio_slowdown = GPIO_SLOWDOWN
    options.led_rgb_sequence = LED_RGB_SEQUENCE
    options.brightness = brightness
    options.disable_hardware_pulsing = True
    # The library normally drops from root to the 'daemon' user once the
    # matrix initializes. Since /home/<user> isn't world-readable, that drop
    # leaves the process unable to read package metadata (or anything else)
    # under the venv. We already require root system-wide for GPIO access,
    # so keep running as root instead.
    options.drop_privileges = False
    return options


class MatrixDisplay:
    def __init__(self, brightness=DEFAULT_BRIGHTNESS):
        if RGBMatrix is None:
            raise RuntimeError(
                "rgbmatrix module not available — install hzeller/rpi-rgb-led-matrix (see README.md)"
            )
        self.matrix = RGBMatrix(options=_build_options(brightness))
        self._last_image = None
        # The C library isn't documented as thread-safe; every SetImage goes
        # through this lock so the animation thread and web handlers can't
        # write the panel simultaneously.
        self._panel_lock = threading.Lock()
        self._anim_stop = None
        self._anim_thread = None

    def _stop_animation(self):
        if self._anim_stop is not None:
            self._anim_stop.set()
        if self._anim_thread is not None and self._anim_thread.is_alive():
            self._anim_thread.join(timeout=2)
        self._anim_stop = None
        self._anim_thread = None

    def _set_image(self, image):
        with self._panel_lock:
            self._last_image = image
            self.matrix.SetImage(image)

    def render_preset(self, preset):
        self._stop_animation()
        self._set_image(compose_preset(preset))

    def play_frames(self, frames):
        """Loop a [(RGB image, duration_seconds), ...] sequence until the
        next render replaces it. A single frame is just shown."""
        self._stop_animation()
        if not frames:
            return
        if len(frames) == 1:
            self._set_image(frames[0][0])
            return
        stop = threading.Event()

        def run():
            while not stop.is_set():
                for image, duration in frames:
                    if stop.is_set():
                        return
                    self._set_image(image)
                    stop.wait(duration)

        self._anim_stop = stop
        self._anim_thread = threading.Thread(target=run, daemon=True)
        self._anim_thread.start()

    def set_brightness(self, value):
        # Brightness applies as pixels are written, so re-push the current
        # screen for it to take effect immediately.
        with self._panel_lock:
            self.matrix.brightness = value
            if self._last_image is not None:
                self.matrix.SetImage(self._last_image)

    def snapshot(self):
        """Copy of what the panel currently shows, or None if it's off."""
        with self._panel_lock:
            return self._last_image.copy() if self._last_image is not None else None

    def clear(self):
        self._stop_animation()
        with self._panel_lock:
            self._last_image = None
            self.matrix.Clear()
