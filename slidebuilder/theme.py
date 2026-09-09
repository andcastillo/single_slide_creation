"""
Theme / style definitions: a simple JSON file playing the role a CSS
stylesheet or slide master template would -- named styles (title, subtitle,
body, table, ...) that bundle font, size, color, and alignment defaults, plus
a shared color palette, so slides built from many small element lists still
come out visually consistent and on-brand.

A theme is plain JSON (see theme.json at the repo root for the example/
starting-point one) shaped like:

    {
      "colors": {
        "primary": "#1F4E79",
        "light": "#FFFFFF",
        ...
      },
      "styles": {
        "title":   {"font_size": 32, "bold": true, "font_color": "$light",
                     "fill_color": "$primary", "align": "center"},
        "subtitle": {"font_size": 20, "bold": true, "font_color": "$primary"},
        ...
      }
    }

Any element in a slide definition can reference a style by name:

    {"type": "rectangle", "style": "title", "x": 0.5, "y": 0.4,
     "width": 12, "height": 1, "text": "Quarterly Review"}

apply_theme() merges that style's fields in as defaults, then the element's
own fields (besides "style") on top -- so any field can still be overridden
per-element. A string field value written as "$name" (e.g. "font_color":
"$primary") is resolved against theme["colors"]["name"]; this works whether
the value came from the style or directly from the element. That's the whole
mechanism -- no cascading/selectors like real CSS, just named presets plus
color tokens, which is enough to keep a deck on-brand without extra
complexity.
"""

import json


def load_theme(path: str) -> dict:
    """Load a theme JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_value(theme: dict, value):
    if isinstance(value, str) and value.startswith("$"):
        token = value[1:]
        colors = theme.get("colors", {})
        if token not in colors:
            raise KeyError(f"Theme color token '${token}' not found in theme['colors']")
        return colors[token]
    return value


def apply_theme(theme: dict, el: dict) -> dict:
    """Return a new element dict with el['style'] (if present) merged in as
    defaults -- el's own fields win -- and any "$token" string values
    resolved against theme['colors'].
    """
    style_name = el.get("style")
    merged = {}
    if style_name is not None:
        style = theme.get("styles", {}).get(style_name)
        if style is None:
            raise KeyError(f"No style named {style_name!r} in theme['styles']")
        merged.update(style)
    merged.update({k: v for k, v in el.items() if k != "style"})
    return {k: _resolve_value(theme, v) for k, v in merged.items()}
