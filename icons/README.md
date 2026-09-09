# icons/

Predefined icons available to the `image` element type via `"icon": "<name>"`
instead of a literal `path`. `slidebuilder.icons.resolve_icon("person")` looks
for `person.svg`, then `.png`, `.jpg`, `.jpeg` in this folder.

Currently included (generic placeholders, single flat color, transparent
background, 64x64 viewBox):

- `person`
- `computer`
- `cloud`
- `chat_icon`
- `chatbot`

## Adding your own / replacing with official brand assets

Drop a file named `<icon_name>.svg` (or `.png`) in this folder and it's
immediately usable as `{"type": "image", "icon": "<icon_name>", ...}` --
no code changes needed. SVG is preferred: it stays crisp at any size and
LibreOffice renders it natively. This is also the mechanism for swapping in
an approved Cisco icon set later: replace these files (same names, or add
new ones) and every slide definition that references them by name picks up
the change automatically.
