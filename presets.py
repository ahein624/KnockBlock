"""Status presets shown on the panel.

Each preset defines the text lines, emoji icon, and colors that matrix.py
renders. `label` and `ui_color` are what the phone UI shows — `ui_color` is
brighter than `bg_color` because the LED panel colors are kept dim to limit
current draw.
"""

PRESETS = {
    "on_a_call": {
        "label": "On a Call",
        "emoji": "\U0001F4DE",  # 📞
        "lines": ["ON A", "CALL"],
        "bg_color": (120, 0, 0),
        "text_color": (255, 255, 255),
        "ui_color": "#e5484d",
    },
    "free": {
        "label": "Free",
        "emoji": "✅",  # ✅
        "lines": ["FREE"],
        "bg_color": (0, 90, 0),
        "text_color": (255, 255, 255),
        "ui_color": "#30a46c",
    },
    "in_a_meeting": {
        "label": "In a Meeting",
        "emoji": "\U0001F465",  # 👥
        "lines": ["IN A", "MEETING"],
        "bg_color": (150, 90, 0),
        "text_color": (255, 255, 255),
        "ui_color": "#e8912d",
    },
    "do_not_disturb": {
        "label": "Do Not Disturb",
        "emoji": "\U0001F6AB",  # 🚫
        "lines": ["DO NOT", "DISTURB"],
        "bg_color": (90, 0, 110),
        "text_color": (255, 255, 255),
        "ui_color": "#8e4ec6",
    },
}

DEFAULT_PRESET = "free"

# Background colors selectable for custom messages. `led` is what the panel
# shows; `ui` is the matching swatch color in the phone UI.
MESSAGE_COLORS = {
    "blue": {"led": (0, 45, 110), "ui": "#3b82f6"},
    "green": {"led": (0, 90, 0), "ui": "#30a46c"},
    "orange": {"led": (150, 90, 0), "ui": "#e8912d"},
    "red": {"led": (120, 0, 0), "ui": "#e5484d"},
    "purple": {"led": (90, 0, 110), "ui": "#8e4ec6"},
}

DEFAULT_MESSAGE_COLOR = "blue"
