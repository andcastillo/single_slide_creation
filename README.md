# single_slide_creation

A small Python library that drives a running LibreOffice Impress instance
(via the UNO API) to build a slide from a list of element definitions --
rectangles, ovals, text boxes, tables, and images/icons, each with position,
size, color, font, and alignment -- and either creates a new `.pptx` deck or
appends the slide to the end of an existing one.

## Why UNO (and not python-pptx)

This is built on top of a real, running LibreOffice process rather than
writing the `.pptx` XML directly, specifically so you can work
interactively: keep LibreOffice open and visible, let the script place
elements, look at the result, tweak it by hand in the GUI, then run the
script again to add more -- all against the same live document. Because
`open_deck()` finds and reuses an already-open document (matched by file
path) instead of reloading from disk, manual edits are never discarded
between script runs.

## Setup

Requires LibreOffice (already installed on this machine: `soffice`,
version 26.2+) and the system Python that can `import uno` -- **not** a
venv/conda interpreter unless you've added LibreOffice's UNO bindings to its
path. On this machine that's `/usr/bin/python3`:

```
/usr/bin/python3 -c "import uno"   # should succeed with no output
```

### 1. Start LibreOffice, listening for UNO connections

Use a dedicated `-env:UserInstallation` profile so this doesn't collide with
(or get blocked by) any LibreOffice window you already have open normally:

```bash
soffice --impress \
    -env:UserInstallation=file:///tmp/lo_automation_profile \
    --accept="socket,host=localhost,port=2002;urp;" \
    --norestore --nologo
```

Leave this running. It opens a visible LibreOffice window -- that's the
window you'll watch/edit interactively.

### 2. Run the example

```bash
/usr/bin/python3 examples/basic_example.py
```

This creates (or reuses) `examples/output_deck.pptx`, adds a slide from the
element list defined in that script, and saves it. Run it again to append
another slide to the same deck.

For a version that uses named styles from `theme.json` and icons from
`icons/`, run `examples/themed_example.py` instead. For a process-flow
diagram (icons connected with arrowed lines), see
`examples/diagram_example.py` and the section below.

## Library usage

```python
from slidebuilder import connect, create_or_append_slide

ctx, desktop = connect()  # connects to the already-running LibreOffice

elements = [
    {
        "type": "rectangle",
        "x": 0.5, "y": 0.4, "width": 12.33, "height": 1.0,
        "fill_color": "#1F4E79",
        "text": "Quarterly Review",
        "font_color": "#FFFFFF",
        "font_size": 32,
        "bold": True,
        "align": "center",
        "valign": "middle",
    },
    {
        "type": "table",
        "x": 0.5, "y": 2.2, "width": 6.0, "height": 2.0,
        "rows": [["Metric", "Q1"], ["Revenue", "$1.2M"]],
        "header_fill_color": "#1F4E79",
        "header_font_color": "#FFFFFF",
    },
]

doc, page = create_or_append_slide(desktop, "/path/to/deck.pptx", elements)
```

`create_or_append_slide` opens the deck (creating it if it doesn't exist yet,
or reusing it if already open), appends a new slide populated with
`elements`, saves, and leaves the document open in the LibreOffice window.

For finer control, use the pieces it wraps directly: `open_deck(desktop,
path)`, `add_slide(doc, elements)`, `save_deck(doc, path)`.

## Element definitions

All positions/sizes are in **inches**, measured from the slide's top-left
corner. Colors are `"#RRGGBB"` strings.

| type        | key fields |
|-------------|------------|
| `rectangle`, `oval` | `x, y, width, height`, `fill_color`, `line_color`, `line_width`, and optionally `text` with `font_size`, `bold`, `italic`, `font_color`, `align`, `valign` |
| `text`      | `x, y, width, height, text`, `font_size`, `bold`, `italic`, `font_color`, `align`, `valign` |
| `table`     | `x, y, width, height`, `rows` (list of lists of strings), `col_widths`/`row_heights` (relative weights), `header_fill_color`, `header_font_color`, `fill_color`, `font_size`, `align` |
| `image`     | `x, y, width, height`, and either `path` to an image file or `icon` naming a predefined icon (see below) |
| `line`      | `x1, y1, x2, y2` (endpoints, not x/y/width/height), `line_color`, `line_width`, `arrow_start`/`arrow_end` (bool), `arrow_size` -- see below |

Every element also accepts an optional `"style": "<name>"` referencing an
entry in a theme's `styles` (see below); explicit fields on the element
still override whatever the style set.

### Text wrapping

Text in `rectangle`, `oval`, and `text` elements always word-wraps within
the given `width`. `height` is a *minimum* -- if the wrapped text needs
more vertical room than that to avoid being cut off, the shape is made
taller automatically (never shorter than what you asked for). This is a
deliberate library behavior, not LibreOffice's own "shrink/grow to fit":
`TextAutoGrowHeight` turns out not to actually recompute a shape's stored
size when driven via a script the way this library does (set text, save,
without ever going through interactive layout) -- see
`_min_height_for_text`'s docstring in `slidebuilder/elements.py` for the
mechanism, based on an approximate (not exact-font-metrics) line-wrap
estimate. Table cell/row heights already auto-grow correctly on their own
(LibreOffice handles that internally), so tables aren't affected by this.

See the docstring at the top of `slidebuilder/elements.py` for the full
field list and defaults.

## Predefined icons (`icons/`)

`{"type": "image", "icon": "person", ...}` looks up `icons/person.svg` (or
`.png`/`.jpg`) instead of needing a literal `path`. Currently included:
`person`, `document`, `computer`, `cloud`, `chat_icon`, `chatbot` -- generic
flat-style placeholders. To use your own set (e.g. official Cisco icons),
just drop files with the matching names into `icons/`; nothing in code
needs to change. See `icons/README.md`.

## Process-flow diagrams (connector lines)

`examples/diagram_example.py` builds this -- two input documents feeding a
process step that produces one output document, drawn with `line` elements:

```python
{"type": "line", "style": "connector",
 "x1": 1.8, "y1": 2.1, "x2": 3.6, "y2": 3.75}
```

A `line` is defined by its two endpoints (`x1, y1` to `x2, y2`), typically
one shape's edge to another's, rather than `x, y, width, height` -- and
unlike the other element types, direction matters: `arrow_end: true` draws
an arrowhead at `(x2, y2)`, `arrow_start: true` at `(x1, y1)`. The included
`"connector"` style in `theme.json` sets a consistent line color/width and
`arrow_end: true`, so most diagram lines only need to state their
endpoints.

(Implementation note: a UNO `LineShape` normally always draws from its
bounding box's top-left corner to its bottom-right corner regardless of
which endpoint you call "start" -- which would put the arrowhead on the
wrong end for a line going up-and-left or down-and-left. `_create_line` in
`slidebuilder/elements.py` sets the shape's `PolyPolygon` (its actual point
list) directly instead, so `(x1,y1) -> (x2,y2)` order -- and therefore
arrow placement -- is always preserved.)

## Style / theme definitions (`theme.json`)

`theme.json` is the "brand compliance" file: a plain JSON config (not CSS --
see *Why JSON, not CSS* below) with a shared color palette and named style
presets (`title`, `subtitle`, `body`, `caption`, `callout`, `table`,
`process`, `connector`, ...), each bundling font family/size/weight/color/
alignment (or, for `connector`, line) defaults. Elements
opt in with `"style": "<name>"`:

```python
from slidebuilder import load_theme

theme = load_theme("theme.json")
elements = [
    {"type": "rectangle", "style": "title",
     "x": 0.5, "y": 0.4, "width": 12.33, "height": 1.0,
     "text": "Platform Overview"},   # position/text always given per-element
]
doc, page = create_or_append_slide(desktop, "deck.pptx", elements, theme=theme)
```

A style's fields are just defaults -- any field the element sets itself
wins, so you can reuse a style and still tweak one slide's instance. Colors
written as `"$name"` (e.g. `"font_color": "$primary"`) resolve against
`theme["colors"]["name"]`, so every styled element stays in sync if you
change the palette in one place.

**The color hex codes and font name in `theme.json` are unverified
placeholders** -- replace them with your actual approved Cisco brand values
before using this for real decks.

### Why JSON, not CSS

A real stylesheet needs selectors and cascade rules to decide which of many
possibly-matching rules wins for a given element; here there's no DOM to
select against, only a flat list of element dicts you write yourself. So a
style is really just a named, reusable default -- `theme["styles"]["title"]`
is a partial element dict merged underneath the element you already wrote,
with the element's own fields winning. That's the entire mechanism
(`slidebuilder/theme.py`, ~30 lines): no selector/cascade engine to write,
and the file stays plain data any teammate can read or edit by hand.

## Layout

- `examples/basic_example.py` -- runnable demo covering every element type.
- `examples/themed_example.py` -- same, but using `theme.json` styles and
  `icons/` icons.
- `examples/diagram_example.py` -- process-flow diagram with arrowed
  connector lines between icons and a process box.
- `slidebuilder/connection.py` -- connect to (or launch) a LibreOffice
  instance over its UNO socket.
- `slidebuilder/builder.py` -- open/create a deck, append a slide, save.
- `slidebuilder/elements.py` -- turns one element dict into a UNO shape on
  the slide.
- `slidebuilder/theme.py` -- loads `theme.json` and merges named styles /
  resolves `"$color"` tokens into an element dict.
- `slidebuilder/icons.py` -- resolves an icon name to a file in `icons/`.
- `slidebuilder/units.py` -- inches/cm to the API's native 1/100 mm units,
  and hex color parsing.
- `icons/` -- predefined icon image files, looked up by name.
- `theme.json` -- the style/brand definition (colors, fonts, named presets).

## Notes / current limitations

- `save_deck` picks the export filter from the file extension: `.pptx`,
  `.ppt`, or `.odp`.
- `connection.launch()` exists for starting LibreOffice from Python too, but
  the interactive workflow above (starting it yourself once, in a terminal)
  is the intended way to work with it.
- Icons/theme are plain files with no validation tooling yet (e.g. nothing
  checks a theme.json against a schema) -- a typo in a style or color name
  surfaces as a clear `KeyError`/`FileNotFoundError` at slide-build time.
