"""Generate the tray icons at runtime so the .exe stays small.

We draw a 64x64 disc with a subtle inner shadow + outer glow into a
PIL Image, parametrised by colour. Same look the web UI uses for the
hero LED bead, so the desktop icon feels like the web app shrunk down.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

SIZE = 64

# (centre colour, edge colour, halo colour). Tuned to read at 16x16 on
# both Windows light/dark taskbars.
_PALETTES = {
    "idle":         ((52, 199, 89),  (30, 130, 70),  (52, 199, 89)),
    "in_call":      ((231, 76, 60),  (160, 50, 40),  (231, 76, 60)),
    "away":         ((108, 139, 189), (70, 100, 150), (108, 139, 189)),
    "warning":      ((245, 158, 11), (180, 110, 0),  (245, 158, 11)),
    "disconnected": ((150, 150, 150), (90, 90, 90),  (150, 150, 150)),
}


def status_icon(name: str, via_usb: bool = False) -> Image.Image:
    """Render the tray icon.

    `via_usb=True` adds a small white badge in the bottom-right corner
    so the user can tell at a glance whether the helper is talking to
    the device over USB (no Wi-Fi dependency) or over the network.
    """
    centre, edge, halo = _PALETTES.get(name, _PALETTES["disconnected"])
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Halo (soft outer glow).
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((4, 4, SIZE - 4, SIZE - 4), fill=halo + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(4))
    base = Image.alpha_composite(base, glow)

    # Core disc with a radial-ish fill: paint edge first, overlay centre.
    draw = ImageDraw.Draw(base)
    draw.ellipse((10, 10, SIZE - 10, SIZE - 10), fill=edge + (255,))
    draw.ellipse((14, 14, SIZE - 14, SIZE - 14), fill=centre + (255,))

    # Tiny specular highlight.
    hl = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hl)
    hdraw.ellipse((20, 18, 34, 26), fill=(255, 255, 255, 150))
    hl = hl.filter(ImageFilter.GaussianBlur(1.5))
    base = Image.alpha_composite(base, hl)

    if via_usb:
        # Small white circle with a thin dark outline in the bottom-right
        # quadrant — reads clearly at 16x16 without overwhelming the LED.
        badge = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(badge)
        # Outline first (slightly larger ellipse in dark)…
        bdraw.ellipse((42, 42, 60, 60), fill=(30, 30, 30, 255))
        # …then white core on top.
        bdraw.ellipse((44, 44, 58, 58), fill=(255, 255, 255, 255))
        base = Image.alpha_composite(base, badge)

    return base
