"""Stub of the `rgbmatrix` C extension for hardware-free development.

dev_server.py puts this directory first on sys.path so matrix.MatrixDisplay
initializes without a panel. SetImage is a no-op — the app's own
`_last_image` bookkeeping is what feeds /preview.png.
"""


class RGBMatrixOptions:
    """Accepts any attribute assignment, like the real options struct."""


class RGBMatrix:
    def __init__(self, options=None):
        self.brightness = getattr(options, "brightness", 100)

    def SetImage(self, image):
        pass

    def Clear(self):
        pass
