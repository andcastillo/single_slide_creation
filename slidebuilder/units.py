"""
Unit and color conversion helpers.

Element definitions use inches for position/size (matching how PowerPoint
decks are normally authored) and point sizes for fonts, both converted to
the 1/100 mm integer units the UNO Draw/Impress API expects internally.
"""

INCH_TO_100MM = 2540  # 1 inch = 25.4 mm = 2540 (1/100 mm)
CM_TO_100MM = 100

# Standard slide canvas size (the classic 4:3 PowerPoint default), used by
# builder.open_deck() to give a freshly-created presentation an explicit,
# known size rather than leaving it at whatever LibreOffice's own internal
# default happens to be -- confirmed on this machine to NOT be 10x7.5in as
# might be assumed (it was 11.02x6.20in, an unusual, non-standard value),
# which matters because slidebuilder.prompt tells an LLM the canvas is this
# size and slidebuilder.llm.clamp_to_canvas enforces it -- both would be
# wrong for a deck whose actual page size doesn't match.
DEFAULT_SLIDE_WIDTH_IN = 10.0
DEFAULT_SLIDE_HEIGHT_IN = 7.5


def inches(value: float) -> int:
    """Convert inches to 1/100 mm (int), as used by shape Position/Size."""
    return round(value * INCH_TO_100MM)


def to_inches(hundredths_mm: float) -> float:
    """Convert 1/100 mm (a UNO Size/Position value, e.g. a DrawPage's
    Width/Height) back to inches -- the inverse of inches()."""
    return hundredths_mm / INCH_TO_100MM


def cm(value: float) -> int:
    """Convert centimeters to 1/100 mm (int)."""
    return round(value * CM_TO_100MM)


def hex_to_color(hex_str: str) -> int:
    """Convert '#RRGGBB' (or 'RRGGBB') to the 0xRRGGBB int UNO color APIs use."""
    s = hex_str.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Expected a 6-digit hex color like '#RRGGBB', got {hex_str!r}")
    return int(s, 16)
