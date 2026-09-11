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

No `pip install` needed -- everything here (including `generate_slide.py`
and `slidebuilder/llm.py`) uses only `uno` plus the standard library.

### macOS setup

LibreOffice on macOS bundles its own Python interpreter (with `uno`
built in) separately from the system/Homebrew one -- there's no Fedora-style
system-wide `uno.py` to find. Use that bundled interpreter for everything:

```bash
# Install LibreOffice if you haven't: https://www.libreoffice.org/download/
# or: brew install --cask libreoffice

/Applications/LibreOffice.app/Contents/MacOS/python -c "import uno"   # should succeed
```

If that path doesn't exist on your version (it's moved between LibreOffice
releases before), look for `python` or `python3` under
`/Applications/LibreOffice.app/Contents/` -- `Contents/Resources/` is the
other place it's historically lived. Once found, use that interpreter (and
`Contents/MacOS/soffice` for the `soffice` binary below) everywhere this
README says `/usr/bin/python3` or `soffice`. Because the whole pipeline is
dependency-free, there's nothing to `pip install` into it regardless of
whether that bundled interpreter even has pip.

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
taller automatically (never shorter than what you asked for), using an
approximate (not exact-font-metrics) line-wrap estimate -- see
`_min_height_for_text`'s docstring in `slidebuilder/elements.py`. Table
cell/row heights already auto-grow correctly on their own (LibreOffice
handles that internally), so tables aren't affected by this.

`rectangle`/`oval` are built as a `com.sun.star.drawing.CustomShape`
(the same underlying shape type Impress's own toolbar creates), not the
simpler `RectangleShape`/`EllipseShape` services, which turned out to
matter for more than geometry: a shape built with those legacy services
doesn't hook into LibreOffice's live text-layout engine the same way, so
typing new text into one by hand afterward (in the LibreOffice window)
just doesn't wrap -- confirmed directly (its Size never changed after a
scripted `setString()` either, even with `TextAutoGrowHeight` on, while a
`CustomShape`'s does, immediately). `CustomShape`'s own default also
auto-*shrinks* the box to hug short text, same as a hand-drawn shape --
turned off here (`TextAutoGrowHeight = False`) so a shape's size stays
exactly what this library computed, which matters whenever something else
(e.g. a connector `line`) is positioned relative to it.

There's a second, separate wrinkle `save_deck` also works around: when
LibreOffice exports a `.pptx`, it leaves the `wrap="square"` attribute off
every text body's XML (`<a:bodyPr>`), relying on that being the OOXML spec
default rather than stating it -- and that was observed, directly, not to
be interpreted consistently: the same file rendered word-wrapped via one
LibreOffice profile/session but showed unwrapped, overflowing text when
freshly opened in another. `save_deck` patches every `<a:bodyPr>` in the
saved file to state `wrap="square"` explicitly so it can't be read either
way; this happens automatically on every `.pptx` save, nothing to opt into.

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

## Natural-language slides (`generate_slide.py`)

Describe a slide in plain English in a text file, and have a local LLM
turn that into an element list, which then gets built the same way as
everything above. This is a first pass at that pipeline -- one slide per
run, no retry loop yet if the model's output doesn't validate.

### Setup

Uses [LM Studio](https://lmstudio.ai)'s local server (an OpenAI-compatible
`/v1/chat/completions` API), not any cloud service:

```bash
lms server start
lms load qwen/qwen3.5-9b --context-length 16384
```

The `--context-length 16384` matters: the system prompt (schema + theme +
icons, built fresh each run) is already close to 2000 tokens on its own,
and a reasoning-capable local model like this one can easily spend another
1000+ tokens on hidden chain-of-thought before it ever writes the answer --
the default 4096 context isn't enough headroom for both. On CPU-only
hardware (no GPU), expect a single slide to take **several minutes** to
generate; this is inherent to running an LLM locally without GPU
acceleration, not something the script controls.

`--base-url` doesn't have to point at this machine -- `generate_slide.py`
works identically against LM Studio running on another computer on your
network (e.g. one with more RAM/a GPU for a bigger model): start its
server with `lms server start --bind 0.0.0.0` (the default, `127.0.0.1`,
only accepts connections from that same machine) and make sure its
firewall allows the port, then pass `--base-url http://<that-ip>:1234/v1
--model <its-model-id>` here.

#### Reasoning ("thinking") models and latency

A reasoning-capable model (Qwen3-family ones, notably) can spend far more
tokens on hidden chain-of-thought than on the actual answer -- for one
trivial request, 1192 reasoning tokens versus 12 content tokens, confirmed
via the response's separate `reasoning_content` field. `--no-think` asks
the backend for less of that (via the OpenAI-compatible
`chat_template_kwargs: {"enable_thinking": false}` field, which
llama.cpp-based servers including LM Studio forward into the model's own
chat template) -- but confirmed live, it's a soft hint: on a real,
non-trivial slide description it cut runtime only marginally (282s). What
actually worked was disabling thinking in LM Studio's own per-model
settings (**Enable thinking** / **Preserve thinking**, both off, model
reloaded after) -- same request, same `--no-think` flag, **82s**, a real
~3.4x speedup, with no drop in output quality on that test. If latency
matters to you, disable thinking at the model level in LM Studio first;
treat `--no-think` as a minor supplement, not the main lever.

### Using a cloud API instead

`--base-url`/`--model`/`--api-key` aren't LM-Studio-specific -- anything
served over an OpenAI-compatible `/chat/completions` endpoint works,
including a cloud provider. Gemini exposes exactly that:

```bash
export LLM_API_KEY="your-gemini-api-key"   # don't pass it as --api-key directly -- shell history/process listings can leak it

/usr/bin/python3 generate_slide.py examples/sample_instructions.txt \
    --base-url https://generativelanguage.googleapis.com/v1beta/openai \
    --model gemini-2.0-flash
```

(`--api-key` also exists directly, and takes priority over `LLM_API_KEY`
if both are set, but the environment variable is the safer default.)
`--model` needs an exact current Gemini model id, which Google updates
over time -- check https://ai.google.dev/gemini-api/docs/models for
what's currently available rather than trusting the example above to
still be current when you read this. This path is unverified here (no
API key available to test against) -- the mechanism (an
OpenAI-compatible endpoint, Bearer auth) is confirmed correct at the code
level (`slidebuilder/llm.py`), but the actual request/response round-trip
against Gemini specifically hasn't been.

A cloud call is a paid API request, unlike everything else in this
pipeline -- nothing here estimates cost, so know your provider's pricing
before turning a natural-language description into a slide this way at
any volume.

### Usage

```bash
# examples/sample_instructions.txt is a plain-text description, e.g.:
#   Create a slide titled "Team Status Update". Below the title on the
#   left, add a table with columns "Task"/"Status" listing... On the
#   right, add a green circular callout with the text "On Track".

/usr/bin/python3 generate_slide.py examples/sample_instructions.txt
```

This builds the system prompt (see below), sends it plus your instructions
to the model, validates the JSON it returns against the element schema,
and -- if that passes -- adds the slide to `examples/generated_deck.pptx`
(or `--deck <path>`) in the LibreOffice session already running, exactly
like `create_or_append_slide()` elsewhere in this README.

Useful flags: `--dry-run` prints the generated elements as JSON without
touching LibreOffice (good for checking the model's output, or for
iterating without needing LibreOffice open at all); `--show-prompt` prints
the assembled system prompt and exits, without calling the LLM at all
(good for checking what the model is actually being told, or for pasting
into a different chat UI to test another model by hand); `--model`,
`--base-url`, `--max-tokens`, `--timeout` tune the LLM call itself -- see
`generate_slide.py --help`.

### How the prompt is built

`slidebuilder/prompt.py`'s `build_system_prompt()` assembles the prompt
from two things kept in sync with the actual library, not hand-copied text
that can drift out of date:

- the **style names, their fields, and the color palette** -- read live
  from `theme.json` every run, so a style or color you add there shows up
  in the very next prompt with no code change;
  the **icon list** -- read live from whatever files are in `icons/`, same
  reasoning: add an icon file, it's usable by the model immediately.
- the **element-type schema** (rectangle/oval/line/text/table/image and
  their fields) is hand-written prose in `prompt.py`, not extracted from
  `elements.py`'s docstring -- schema fields change rarely, and writing it
  directly for an LLM to read (with the "line uses endpoints, not a
  bounding box" gotcha called out explicitly, for instance) works better
  than dumping a docstring meant for a human reading source code. If you
  add/change a field in `slidebuilder/elements.py`, update this text too.

If the model's response can't be parsed as JSON, or the parsed elements
fail schema validation (missing required fields, unknown `type`, wrong
value types, an invalid `align`/`valign`, an unresolvable icon name, a
table whose rows don't all have the same number of cells or whose
`col_widths`/`row_heights` length doesn't match, ...),
`generate_slide.py` prints exactly what's wrong and the raw output, and
exits without touching LibreOffice or the deck file. That table check
specifically was added after a real failure: a model produced a table
with uneven row lengths, which `validate_elements()` at the time didn't
catch, so it passed validation and then crashed deep inside
`_create_table` -- after several other elements had already been added to
the live slide. `validate_elements()` now mirrors every condition
`slidebuilder/elements.py`'s shape-building functions themselves enforce,
specifically so a bad response fails validation up front instead of
leaving a half-built slide in your document.

## Layout

- `examples/basic_example.py` -- runnable demo covering every element type.
- `examples/themed_example.py` -- same, but using `theme.json` styles and
  `icons/` icons.
- `examples/diagram_example.py` -- process-flow diagram with arrowed
  connector lines between icons and a process box.
- `examples/sample_instructions.txt` -- example natural-language slide
  description for `generate_slide.py`.
- `generate_slide.py` -- CLI: instructions file -> local LLM -> validated
  elements -> slide in the running LibreOffice session.
- `slidebuilder/prompt.py` -- builds the system prompt for
  `generate_slide.py` from the schema, `theme.json`, and `icons/`.
- `slidebuilder/llm.py` -- talks to the local LLM's OpenAI-compatible API,
  parses/validates its response.
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
