"""
Unit and color conversion helpers.

Element definitions use inches for position/size (matching how PowerPoint
decks are normally authored) and point sizes for fonts, both converted to
the 1/100 mm integer units the UNO Draw/Impress API expects internally.
"""

INCH_TO_100MM = 2540  # 1 inch = 25.4 mm = 2540 (1/100 mm)
CM_TO_100MM = 100


def inches(value: float) -> int:
    """Convert inches to 1/100 mm (int), as used by shape Position/Size."""
    return round(value * INCH_TO_100MM)


def cm(value: float) -> int:
    """Convert centimeters to 1/100 mm (int)."""
    return round(value * CM_TO_100MM)


def hex_to_color(hex_str: str) -> int:
    """Convert '#RRGGBB' (or 'RRGGBB') to the 0xRRGGBB int UNO color APIs use."""
    s = hex_str.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"Expected a 6-digit hex color like '#RRGGBB', got {hex_str!r}")
    return int(s, 16)
