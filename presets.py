"""Status presets shown on the panel.

Each preset defines the text lines, emoji icon, and colors that matrix.py
renders. `label` and `ui_color` are what the phone UI shows — `ui_color` is
brighter than `bg_color` because the LED panel colors are kept dim to limit
current draw.
"""

PRESETS = {
    "on_a_call": {
        "label": "On a call",
        "emoji": "\U0001F4DE",  # 📞
        "lines": ["ON A", "CALL"],
        "bg_color": (184, 0,  7),
        "text_color": (255, 255, 255),
        "ui_color": "#5F935D",
    },
    "free": {
        "label": "Free",
        "emoji": "🎉",  # 🎉
        "lines": ["FREE"],
        "bg_color": (77, 149, 87),
        "text_color": (255, 255, 255),
        "ui_color": "#30a46c",
    },
    "in_a_meeting": {
        "label": "In a meeting",
        "emoji": "\U0001F4C5",  # 📅
        "lines": ["IN A", "MEETING"],
        "bg_color": (150, 90, 0),
        "text_color": (255, 255, 255),
        "ui_color": "#274B9B",
    },
    "do_not_disturb": {
        "label": "Do not disturb",
        "emoji": "☢️",  # ☢️
        "lines": ["DO NOT", "DISTURB"],
        "bg_color": (142, 31, 123),
        "text_color": (255, 255, 255),
        "ui_color": "#A81919",
    },
}

DEFAULT_PRESET = "free"

# Shown while a focus timer runs; matrix.py appends the MM:SS countdown line.
# Not in PRESETS: it can't be picked directly, only via a focus timer.
FOCUS_STATUS = {
    "label": "Focus",
    "emoji": "\U0001F3AF",  # 🎯
    "bg_color": (26, 76, 161),
    "text_color": (255, 255, 255),
    "ui_color": "#6366f1",
}

# Background colors selectable for custom messages. `led` is what the panel
# shows; `ui` is the matching swatch color in the phone UI.
MESSAGE_COLORS = {
    "blue": {"led": (26, 76, 161), "ui": "#274B9B"},
    "green": {"led": (77, 149, 87), "ui": "#5F935D"},
    "orange": {"led": (150, 90, 0), "ui": "#e8912d"},
    "red": {"led": (184, 0,  7), "ui": "#A81919"},
    "purple": {"led": (142, 31, 123), "ui": "#8e4ec6"},
}

DEFAULT_MESSAGE_COLOR = "blue"
