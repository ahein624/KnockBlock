"""Static test screen for isolating hardware issues before running the web app.

Run directly on the Pi with sudo (the matrix library needs raw GPIO access):
    sudo python3 hello_matrix.py

Press Ctrl+C to clear the panel and exit.
"""
import time

from matrix import MatrixDisplay

TEST_PRESET = {
    "lines": ["HELLO"],
    "emoji": "👋",
    "bg_color": (0, 0, 0),
    "text_color": (0, 255, 0),
}


def main():
    display = MatrixDisplay()
    display.render_preset(TEST_PRESET)
    print("Test screen sent to panel. Press Ctrl+C to clear and exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        display.clear()


if __name__ == "__main__":
    main()
