"""
Builds the system prompt handed to the local LLM that turns a natural-
language slide description into slidebuilder element definitions.

The prompt is assembled, not hand-maintained as static text, specifically
so it can't silently drift from the actual theme/icons on disk: the style
names, their fields, the color palette, and the icon list are all read live
from `theme.json` and `icons/` every time build_system_prompt() runs. Only
the element-type schema itself (rectangle/oval/line/text/table/image) is
hand-written prose -- that part changes rarely and benefits from being
written for an LLM to read rather than dumped from elements.py's docstring.
If you add fields to an element type in slidebuilder/elements.py, update
the schema text below to match.
"""

import json
import os

from .elements import _VALID_SHAPE_PRESETS
from .units import DEFAULT_SLIDE_HEIGHT_IN, DEFAULT_SLIDE_WIDTH_IN

# Re-exported for existing importers of this module -- the canonical
# definition now lives in units.py, since builder.open_deck() needs it too
# (to give a new deck this same size), not just this module.
__all__ = ["DEFAULT_SLIDE_WIDTH_IN", "DEFAULT_SLIDE_HEIGHT_IN", "build_system_prompt"]

# Short, human-written hints for icons this repo ships with, used only to
# give the model a one-line sense of each -- purely cosmetic. An icon file
# present on disk but missing here still gets listed (by name only), so a
# newly added icon works immediately without needing an update here.
_ICON_HINTS = {
    "person": "a single person/user silhouette",
    "document": "a page/file with a folded corner and text lines",
    "computer": "a desktop monitor",
    "cloud": "a cloud (cloud service/storage)",
    "chat_icon": "a speech bubble with dots (a chat message)",
    "chatbot": "a small robot head (an AI/chatbot)",
    "computer_monitor": "a plain monitor/screen outline (Cisco AIW style)",
    "table_grid": "a 3x3 spreadsheet/grid outline (Cisco AIW style)",
    "code_window": "a browser-chrome window containing </> (Cisco AIW style)",
    "lock": "a padlock, filled (Cisco AIW style)",
    "cloud_sync": "a monitor with two curved arrows syncing to a cloud (Cisco AIW style)",
    "cursor": "a filled mouse-pointer arrow (Cisco AIW style)",
    "puzzle": "four interlocking puzzle pieces (Cisco AIW style)",
    "wheel": "a ship's steering wheel -- used for 'control'/'process' (Cisco AIW style)",
    "clipboard_check": "a clipboard listing a mix of checkmarks and X's (Cisco AIW style)",
    "warning": "an amber/orange triangle with an exclamation mark (Cisco AIW style)",
    "check_mark": "a bold standalone checkmark, no circle/box around it (Cisco AIW style)",
    "x_mark": "a bold standalone X, no circle/box around it (Cisco AIW style)",
    "file_outline": "a plain page/file outline with a folded corner, no fill, no background circle (Cisco AIW style) -- use this, not 'document', when compositing onto a colored badge circle yourself",
}

_ELEMENT_SCHEMA = """\
## Element types

Every element is a JSON object with a "type" field. Positions/sizes are
plain numbers in inches, origin (0,0) at the slide's top-left corner.

### "rectangle" / "oval"
A filled/outlined shape, optionally with text centered or aligned inside it.
  x, y, width, height   required, inches
  text                  optional string
  font_family           optional, e.g. "Arial"
  font_size             optional, points (default 18)
  bold, italic           optional booleans
  font_color            optional "#RRGGBB" or "$colorToken" (default black)
  align                 optional "left" | "center" | "right" (default "left")
  valign                optional "top" | "middle" | "bottom" (default "middle")
  fill_color            optional "#RRGGBB"/"$token", or null for no fill
  line_color            optional "#RRGGBB"/"$token", or null for no outline
  line_width            optional, outline width in points (default 1)
Text always word-wraps and the box grows taller (never shorter) than given
if needed to fit -- never manually shrink text or truncate it instead.

### "shape"
Any shape beyond a plain rectangle/oval -- a star, an arrow, a diamond, a
heart, and more (see the Shape presets list below for the exact set).
Takes exactly the same fields as "rectangle"/"oval" above (x, y, width,
height, text, font_*, align, valign, fill_color, line_color, line_width),
PLUS:
  preset                required: one of the exact names in the Shape
                         presets list below -- nothing else. Do not guess
                         or invent a preset name (e.g. a plausible-looking
                         "star6" or "triangle") even if it seems like it
                         should exist -- an unrecognized name silently
                         renders as a plain rectangle instead of erroring,
                         which is worse than obviously wrong. If the
                         description asks for a shape not in the list,
                         use the closest listed one instead of a made-up
                         name.

### "text"
A plain text label/caption with no fill or outline (use "rectangle" instead
if you want a filled/outlined box around the text).
  x, y, width, height, text   required
  font_family, font_size, bold, italic, font_color, align, valign   optional, same meaning as above

### "table"
  x, y, width, height   required
  rows                  required: list of rows, each a list of SEPARATE cell
                         strings -- one column = one string. Every row must
                         have the same number of strings in it. The first
                         row is treated as the header row.

                         Correct, for a 3-column table with a header:
                           "rows": [["id", "name", "program_id"],
                                    ["1", "Ada", "P1"],
                                    ["2", "Grace", "P2"]]

                         WRONG -- do not do this, even though it looks like
                         a normal markdown table: joining a row into one
                         pipe-separated string, or putting it in a
                         single-element list, produces a broken one-column
                         table, not a 3-column one:
                           "rows": [["id | name | program_id"],
                                    ["1 | Ada | P1"],
                                    ["2 | Grace | P2"]]
  col_widths            optional list of relative column widths, e.g. [2, 1, 1]
                         (defaults to equal-width columns)
  row_heights            optional list of relative row heights (defaults to equal)
  header_fill_color, header_font_color   optional, first row only
  fill_color             optional, all other rows
  font_size, font_family, align   optional, applied to every cell

### "image"
A picture, or one of the predefined icons listed below.
  x, y, width, height   required
  icon                  name of a predefined icon (see the Icons list below) --
                         use this for any person/document/computer/cloud/chat/
                         robot pictogram instead of drawing one out of shapes
  path                  (alternative to icon) a literal image file path --
                         do not invent a path; only use "icon" unless the
                         description names a real file

### "line"
A straight connector between two points -- e.g. an arrow from one shape's
edge to another's, for a flow/process diagram. NOTE: unlike every other
type, this uses endpoints (x1,y1)->(x2,y2), not x/y/width/height.
  x1, y1, x2, y2   required, inches -- the start and end points
  line_color       optional "#RRGGBB"/"$token" (default black)
  line_width       optional, points (default 1)
  arrow_start      optional bool: arrowhead at (x1,y1) (default false)
  arrow_end        optional bool: arrowhead at (x2,y2) (default false) --
                    set true for a directional flow arrow
  arrow_size       optional, inches (default 0.12)

## Styles

Any element (of any type) may include a "style" field naming one of the
presets below. A style just supplies default values for that element's
fields -- any field you also set explicitly on the element overrides the
style's value for that field. Use a style whenever one clearly fits, so the
slide stays visually consistent; still set x/y/width/height/text/rows
yourself, since styles never include those.
"""


def _format_styles(theme: dict) -> str:
    lines = []
    for name, fields in theme.get("styles", {}).items():
        field_str = ", ".join(f"{k}={v!r}" for k, v in fields.items())
        lines.append(f'  "{name}": {field_str}')
    return "\n".join(lines)


def _format_colors(theme: dict) -> str:
    lines = []
    for name, value in theme.get("colors", {}).items():
        if name.startswith("_") or isinstance(value, list):
            continue
        lines.append(f'  ${name} = {value}')
    return "\n".join(lines)


def _format_icons(icons_dir: str) -> str:
    if not os.path.isdir(icons_dir):
        return "  (none available)"
    exts = (".svg", ".png", ".jpg", ".jpeg")
    names = sorted(
        {os.path.splitext(f)[0] for f in os.listdir(icons_dir) if os.path.splitext(f)[1].lower() in exts}
    )
    lines = []
    for name in names:
        hint = _ICON_HINTS.get(name)
        lines.append(f'  "{name}"' + (f" -- {hint}" if hint else ""))
    return "\n".join(lines) if lines else "  (none available)"


def _format_shape_presets() -> str:
    return "\n".join(f'  "{name}" -- {hint}' for name, hint in sorted(_VALID_SHAPE_PRESETS.items()))


def build_system_prompt(
    theme: dict,
    icons_dir: str,
    slide_width_in: float = DEFAULT_SLIDE_WIDTH_IN,
    slide_height_in: float = DEFAULT_SLIDE_HEIGHT_IN,
) -> str:
    """Assemble the full system prompt from the element schema (static,
    hand-written) plus the live theme styles/colors and icons list (read
    from `theme` and `icons_dir`)."""
    example = {
        "elements": [
            {
                "type": "rectangle", "style": "title",
                "x": 0.5, "y": 0.4, "width": slide_width_in - 1.0, "height": 1.0,
                "text": "Document Summarization Pipeline",
            },
            {
                "type": "image", "icon": "document",
                "x": 0.8, "y": 1.6, "width": 1.0, "height": 1.0,
            },
            {
                "type": "text", "style": "caption",
                "x": 0.5, "y": 2.65, "width": 1.6, "height": 0.3,
                "text": "Document A", "align": "center",
            },
            {
                "type": "line", "style": "connector",
                "x1": 1.8, "y1": 2.1, "x2": 3.6, "y2": 3.75,
            },
            {
                "type": "rectangle", "style": "process",
                "x": 3.6, "y": 3.0, "width": 3.0, "height": 1.5,
                "text": "Summarization and Comprehension",
            },
        ]
    }

    return f"""You are a slide-layout generator. You turn a natural-language
description of ONE slide into the element definitions a Python library
(slidebuilder) uses to actually draw it in LibreOffice Impress.

## Output format (critical -- read carefully)

Output ONLY a single JSON object -- nothing else. No markdown code fences,
no explanation, no text before or after the JSON. The object has exactly
one key, "elements", whose value is a JSON array of element objects (the
schema is below). If your response contains anything other than that one
JSON object, it cannot be used.

## Canvas

- The slide is {slide_width_in} x {slide_height_in} inches, origin (0,0) at the top-left corner, x increasing rightward and y increasing downward.
- All position/size numbers (x, y, width, height, x1, y1, x2, y2) are plain
  numbers in inches, not strings.
- Keep every element within the canvas bounds, with a margin of roughly
  0.5in from each edge unless the description clearly wants an edge-to-edge
  element (e.g. a full-width title bar).
- Don't let elements overlap unless the description clearly wants that
  (e.g. text centered inside a shape is fine and expected).

{_ELEMENT_SCHEMA}
{_format_styles(theme)}

## Shape presets

For a "shape" element's "preset" field, one of these exact names (not
"star", not "triangle" -- see the "shape" entry above for why):

{_format_shape_presets()}

## Colors

fill_color, line_color, font_color, header_fill_color, and header_font_color
accept either a literal "#RRGGBB" hex string, or one of this theme's named
color tokens, written as "$name":

{_format_colors(theme)}

Prefer a "$token" over inventing a hex color, so the slide stays on-brand.

## Icons

For any "image" element, set "icon" to one of these exact names (not
"path") to place a predefined pictogram:

{_format_icons(icons_dir)}

## Worked example

A description like "two documents feed into a process box labeled
'Summarization and Comprehension', connected with an arrow" should produce
something shaped like this (abbreviated -- a real response would include
all the elements the description implies, e.g. both input documents, their
labels, and the arrow into the box, following the same pattern):

{json.dumps(example, indent=2)}

## Final checklist before you answer

- Valid JSON, one top-level object, key "elements" only.
- Field names exactly as specified above (case-sensitive).
- "line" uses x1/y1/x2/y2 -- every other type uses x/y/width/height.
- Every number is a plain JSON number, not a quoted string.
- Colors are "#RRGGBB" or "$token" strings, never a CSS name like "blue".
- A "shape" element's "preset" is copied exactly from the Shape presets
  list, never guessed.
"""
