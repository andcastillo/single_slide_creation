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

**Cisco Networking Academy style (added 2026-09, 96x96 viewBox, mostly
single-color flat glyphs, no baked-in background circle — unlike the
placeholders above, compose a colored `ellipse`/`roundRect` behind one of
these if you want a badge look, the same way the source deck does it):**
extracted from `AIW_Prompt_L02_clean_workflow.pptx` (Eddy's "Prompt like an
engineer" course deck), kept to the icons that actually recur across many of
that deck's 30 slides (i.e. its real reusable icon set, not one-off
illustration art) plus two (`warning`, `check_mark`/`x_mark`) pulled in
despite lower recurrence there because they're directly useful for this
course's DEBUG/VERIFY beats:

- `computer_monitor` — a plain monitor/screen (12 uses in the source deck)
- `table_grid` — a spreadsheet/grid (10 uses)
- `code_window` — a browser-chrome window with `</>` (10 uses)
- `lock` — a padlock (10 uses)
- `cloud_sync` — a monitor syncing to a cloud, two curved arrows (10 uses)
- `cursor` — a mouse-pointer arrow (10 uses)
- `puzzle` — four interlocking puzzle pieces (8 uses)
- `wheel` — a ship's steering wheel, used in the source deck for
  "control"/"process" concepts (8 uses)
- `clipboard_check` — a clipboard with a mix of checkmarks and X's (7 uses)
- `warning` — an amber triangle with "!" (4 uses in the source deck)
- `check_mark` — a bold standalone checkmark (2 uses)
- `x_mark` — a bold standalone X (2 uses)
- `file_outline` — a plain page-with-folded-corner outline, no fill, no
  baked-in circle (used once in the source deck; added anyway because the
  existing `document` placeholder above bakes in its own navy circle,
  which double-badges if you compose it into a colored `badge_*` circle
  the way this icon set otherwise expects)

The source deck also uses `star`, a document outline, a bar chart, a brain
silhouette, a pencil, a plant, two shield variants, and a target/bullseye
icon, each only once or twice — left out here as one-off illustration
choices rather than part of the recurring set; pull the matching file from
`AIW_Prompt_L02_clean_workflow.pptx`'s `ppt/media/` (it's a zip) the same
way if a specific slide needs one of those.

## Adding your own / replacing with official brand assets

Drop a file named `<icon_name>.svg` (or `.png`) in this folder and it's
immediately usable as `{"type": "image", "icon": "<icon_name>", ...}` --
no code changes needed. SVG is preferred: it stays crisp at any size and
LibreOffice renders it natively. This is also the mechanism for swapping in
an approved Cisco icon set later: replace these files (same names, or add
new ones) and every slide definition that references them by name picks up
the change automatically.
