"""Tray-icon renderer — thin wrapper around `bead.render_bead`.

The tray icon is just the LED bead at 64x64 plus, optionally, a
small white USB badge in the bottom-right corner so the user can
tell at a glance whether the helper is talking to the device over
the cable or over Wi-Fi.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from .bead import render_bead

SIZE = 64

# Tray status name → bead palette key.
_TRAY_TO_BEAD = {
    "idle":         "available",
    "in_call":      "in_call",
    "away":         "away",
    "warning":      "wifi_error",
    "disconnected": "disconnected",
}


def status_icon(name: str, via_usb: bool = False) -> Image.Image:
    bead_key = _TRAY_TO_BEAD.get(name, "disconnected")
    base = render_bead(bead_key, SIZE).copy()

    if via_usb:
        # Small white circle with a thin dark outline in the
        # bottom-right quadrant — reads clearly at 16x16 without
        # overwhelming the LED.
        badge = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        bd.ellipse((42, 42, 60, 60), fill=(30, 30, 30, 255))
        bd.ellipse((44, 44, 58, 58), fill=(255, 255, 255, 255))
        base = Image.alpha_composite(base, badge)

    return base
