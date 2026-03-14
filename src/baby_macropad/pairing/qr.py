"""QR code generation for pairing flow.

Generates a small QR code as a PIL Image sized to fit in a single
macropad cell (~72x60px visible area).
"""

from __future__ import annotations

import qrcode
from PIL import Image


def generate_qr_image(data: str, box_size: int = 2, border: int = 1) -> Image.Image:
    """Generate a QR code as a PIL Image.

    White-on-black to match the dark UI theme. QR scanners handle
    inverted codes fine.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="white", back_color="black").convert("RGB")
