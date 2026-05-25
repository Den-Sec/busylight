"""Pillow renderer for the LED bead.

Same visual language as the web UI: a solid core in the state colour,
a softer concentric outer ring, and a radial halo outside. Pure
Pillow so we can scale it for anything from a 16x16 tray icon up to
a 200 px dashboard hero without dragging in a vector lib.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

# Shared with the web UI / tray icons. (Centre + edge for the inner
# depth shadow; halo is the same hue as the centre.)
_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "available":    ((52, 199, 89),   (30, 130, 70)),
    "busy":         ((231, 76, 60),   (160, 50, 40)),
    "in_call":      ((245, 158, 11),  (180, 110, 0)),
    "away":         ((108, 139, 189), (70, 100, 150)),
    "off":          ((148, 152, 159), (90, 95, 102)),
    "wifi_error":   ((161, 98, 7),    (110, 65, 0)),
    "disconnected": ((150, 150, 150), (90, 90, 90)),
}


# Map firmware / API state names to palette keys.
STATE_TO_PALETTE = {
    "AVAILABLE":   "available",
    "BUSY":        "busy",
    "IN_CALL":     "in_call",
    "AWAY":        "away",
    "OFF":         "off",
    "WIFI_ERROR":  "wifi_error",
}


def render_bead(state: str, size: int = 200) -> Image.Image:
    """Return an RGBA image of the bead.

    Use a palette key (lower-case, see `_PALETTES`) or a firmware
    state name like "AVAILABLE". Falls back to "disconnected" if the
    key is unknown — that way the dashboard always has something to
    show.
    """
    key = STATE_TO_PALETTE.get(state, state.lower())
    centre, edge = _PALETTES.get(key, _PALETTES["disconnected"])

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 1. Outer halo (soft radial pulse). Drawn first so the disc sits
    #    on top of it. The blur radius scales with size so the halo
    #    looks the same across resolutions.
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    halo_inset = int(size * 0.06)
    hd.ellipse(
        (halo_inset, halo_inset, size - halo_inset, size - halo_inset),
        fill=centre + (90,),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(size / 14))
    base = Image.alpha_composite(base, halo)

    # 2. Core disc — edge ring first, then centre on top to fake a
    #    very subtle inner gradient without doing real gradient maths.
    draw = ImageDraw.Draw(base)
    core_outer = int(size * 0.18)
    core_inner = int(size * 0.22)
    draw.ellipse(
        (core_outer, core_outer, size - core_outer, size - core_outer),
        fill=edge + (255,),
    )
    draw.ellipse(
        (core_inner, core_inner, size - core_inner, size - core_inner),
        fill=centre + (255,),
    )

    # 3. Concentric inner ring — mirrors the `.hero-bead-shine`
    #    border in the web CSS. 1.5px scales nicely up to ~64 then
    #    we bump it.
    ring_inset = int(size * 0.25)
    ring_width = max(1, size // 60)
    draw.ellipse(
        (ring_inset, ring_inset, size - ring_inset, size - ring_inset),
        outline=centre + (170,),
        width=ring_width,
    )

    # 4. Specular highlight — a very small, very blurred white spot
    #    in the upper-third. Adds depth without making it look like
    #    a sticker.
    hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hl_x = int(size * 0.34)
    hl_y = int(size * 0.32)
    hl_w = int(size * 0.20)
    hl_h = int(size * 0.12)
    hd.ellipse(
        (hl_x, hl_y, hl_x + hl_w, hl_y + hl_h),
        fill=(255, 255, 255, 150),
    )
    hl = hl.filter(ImageFilter.GaussianBlur(max(1.0, size / 50)))
    base = Image.alpha_composite(base, hl)

    return base
