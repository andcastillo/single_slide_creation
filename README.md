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
| `rectangle`, `oval`, `line` | `x, y, width, height`, `fill_color`, `line_color`, `line_width`, and optionally `text` with `font_size`, `bold`, `italic`, `font_color`, `align`, `valign` |
| `text`      | `x, y, width, height, text`, `font_size`, `bold`, `italic`, `font_color`, `align`, `valign` |
| `table`     | `x, y, width, height`, `rows` (list of lists of strings), `col_widths`/`row_heights` (relative weights), `header_fill_color`, `header_font_color`, `fill_color`, `font_size`, `align` |
| `image`     | `x, y, width, height`, `path` to an image file -- also how predefined icons work: point `path` at an icon image |

See the docstring at the top of `slidebuilder/elements.py` for the full
field list and defaults.

## Layout

- `examples/basic_example.py` -- runnable demo covering every element type.
- `slidebuilder/connection.py` -- connect to (or launch) a LibreOffice
  instance over its UNO socket.
- `slidebuilder/builder.py` -- open/create a deck, append a slide, save.
- `slidebuilder/elements.py` -- turns one element dict into a UNO shape on
  the slide.
- `slidebuilder/units.py` -- inches/cm to the API's native 1/100 mm units,
  and hex color parsing.

## Notes / current limitations

- Icons are just images (`type: "image"`); there's no bundled icon set yet.
  Point `path` at whatever icon files you have.
- `save_deck` picks the export filter from the file extension: `.pptx`,
  `.ppt`, or `.odp`.
- `connection.launch()` exists for starting LibreOffice from Python too, but
  the interactive workflow above (starting it yourself once, in a terminal)
  is the intended way to work with it.
