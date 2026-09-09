"""
Renders individual element definitions (dicts) onto a DrawPage (an Impress
slide) via the UNO API.

Each element is a plain dict:

    type          "rectangle" | "oval" | "line" | "text" | "table" | "image"

Every type except "line" (see below) takes:
    x, y          position of the top-left corner, in inches
    width, height size, in inches

Shape types ("rectangle", "oval") and "text" additionally accept:
    text          string to place inside
    font_family   font name, e.g. "Arial" (default: LibreOffice's default)
    font_size     points (default 18)
    bold          bool (default False)
    italic        bool (default False)
    font_color    "#RRGGBB" (default black)
    align         "left" | "center" | "right" (default "left")
    valign        "top" | "middle" | "bottom" (default "top")
    fill_color    "#RRGGBB", or None for no fill (shapes only, default None)
    line_color    "#RRGGBB", or None for no outline (default "#000000")
    line_width    outline width in points (default 1)

Text always word-wraps within `width`, and `height` is treated as a
minimum: if the text needs more vertical room to wrap without being cut
off, the shape is made taller automatically (see _min_height_for_text) --
it never shrinks below what you asked for, only grows past it if needed.

"table" additionally accepts:
    rows          list of rows, each a list of cell strings, e.g.
                  [["Header 1", "Header 2"], ["a", "b"]]
    font_family, font_size, font_color, align, valign   same meaning, applied to every cell
    header_fill_color   fill color for the first row (default None)
    header_font_color   text color for the first row (default: font_color)
    fill_color          fill color for all other rows (default None)
    col_widths          optional list of relative column widths (e.g. [2, 1, 1]);
                         defaults to equal-width columns
    row_heights         optional list of relative row heights; defaults to
                        equal-height rows

"image" additionally accepts one of:
    path          filesystem path to an image file (png, jpg, svg, ...)
    icon          name of a predefined icon from the icons/ folder (e.g.
                  "person", "document", "chatbot", "computer", "cloud",
                  "chat_icon") -- see slidebuilder/icons.py and
                  icons/README.md

"line" is a straight connector between two explicit points (e.g. from one
shape's edge to another's) rather than x/y/width/height, and accepts:
    x1, y1, x2, y2   start and end points, in inches
    line_color       "#RRGGBB", or None for no line (default "#000000")
    line_width       in points (default 1)
    arrow_start      bool: draw an arrowhead at (x1, y1) (default False)
    arrow_end        bool: draw an arrowhead at (x2, y2) (default False)
    arrow_size       arrowhead length, in inches (default 0.12)

Every element type also accepts an optional "style" key naming an entry in
a theme's ["styles"] dict, whose fields become defaults for that element
(explicit fields on the element still win). See slidebuilder/theme.py. This
only has an effect when elements are created via add_slide(..., theme=...);
create_element() itself just renders whatever plain-dict fields it's given.
"""

import os

import uno
from com.sun.star.awt import Point, Size
from com.sun.star.style.ParagraphAdjust import LEFT as PA_LEFT, CENTER as PA_CENTER, RIGHT as PA_RIGHT
from com.sun.star.drawing.TextVerticalAdjust import (
    TOP as TVA_TOP,
    CENTER as TVA_CENTER,
    BOTTOM as TVA_BOTTOM,
)

from .units import inches, hex_to_color
from .icons import resolve_icon

_HORIZ_ADJUST = {"left": "LEFT", "center": "CENTER", "right": "RIGHT"}
_PARA_ADJUST = {"left": PA_LEFT, "center": PA_CENTER, "right": PA_RIGHT}
_VERT_ADJUST = {"top": TVA_TOP, "middle": TVA_CENTER, "bottom": TVA_BOTTOM}

_SHAPE_SERVICE = {
    "rectangle": "com.sun.star.drawing.RectangleShape",
    "oval": "com.sun.star.drawing.EllipseShape",
}


def create_element(doc, page, el: dict):
    """Create the element described by `el` on `page`. Returns the shape."""
    el_type = el.get("type")
    if el_type in _SHAPE_SERVICE:
        return _create_basic_shape(doc, page, el)
    if el_type == "text":
        return _create_text(doc, page, el)
    if el_type == "table":
        return _create_table(doc, page, el)
    if el_type == "image":
        return _create_image(doc, page, el)
    if el_type == "line":
        return _create_line(doc, page, el)
    raise ValueError(
        f"Unknown element type {el_type!r}. Expected one of: "
        "rectangle, oval, line, text, table, image."
    )


def _estimate_wrapped_line_count(text: str, chars_per_line: int) -> int:
    """Rough greedy word-wrap simulation: how many lines `text` needs if no
    line may exceed `chars_per_line` characters. Honors explicit "\\n"
    breaks as separate paragraphs."""
    chars_per_line = max(chars_per_line, 1)
    total_lines = 0
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            total_lines += 1
            continue
        line_len = 0
        lines_in_paragraph = 1
        for word in words:
            added = len(word) if line_len == 0 else len(word) + 1  # +1 for the space
            if line_len + added > chars_per_line:
                lines_in_paragraph += 1
                line_len = len(word)
            else:
                line_len += added
        total_lines += lines_in_paragraph
    return max(total_lines, 1)


def _min_height_for_text(text: str, font_size_pt: float, width_inches: float) -> float:
    """Approximate the height (in inches) needed to word-wrap `text` inside
    `width_inches` at `font_size_pt`, so a shape/text box's height can be
    auto-expanded to actually contain it.

    This is a heuristic (average glyph width, not real font metrics) --
    LibreOffice's own TextAutoGrowHeight looks like the "proper" way to get
    this for free, but it turns out not to recompute a shape's Size when
    driven via UNO the way this library does (set text, then save without
    ever going through interactive layout); the stored Size -- and
    therefore what gets exported -- stays whatever was set, and wrapped
    text that doesn't fit is simply painted past it instead. Estimating
    and expanding the height ourselves avoids that regardless of layout
    timing.
    """
    h_padding_in = 0.15  # approx. left+right internal text margins
    usable_width_in = max(width_inches - h_padding_in, 0.3)
    avg_char_width_in = (font_size_pt * 0.52) / 72.0  # rough average glyph width
    chars_per_line = max(1, int(usable_width_in / avg_char_width_in))
    n_lines = _estimate_wrapped_line_count(text, chars_per_line)
    line_height_in = (font_size_pt * 1.2) / 72.0
    v_padding_in = 0.12  # approx. top+bottom internal text margins
    return n_lines * line_height_in + v_padding_in


def _position_and_size(shape, el):
    width, height = el["width"], el["height"]
    text = el.get("text")
    if text:
        # An ellipse's usable text width narrows away from its vertical
        # center, unlike a rectangle's -- treat it as if it only had ~72%
        # of its bounding width to wrap into, so the height estimate below
        # compensates with extra room instead of undershooting.
        wrap_width = width * 0.72 if el.get("type") == "oval" else width
        # The given height is a minimum: grow (never shrink) so wrapped
        # text doesn't visually spill past the shape -- see
        # _min_height_for_text's docstring for why this can't just be left
        # to TextAutoGrowHeight.
        height = max(height, _min_height_for_text(text, el.get("font_size", 18), wrap_width))
    shape.Position = Point(inches(el["x"]), inches(el["y"]))
    shape.Size = Size(inches(width), inches(height))


def _apply_text_formatting(text_range_cursor, el):
    cursor = text_range_cursor
    cursor.gotoStart(False)
    cursor.gotoEnd(True)
    if el.get("font_family"):
        cursor.CharFontName = el["font_family"]
    cursor.CharHeight = el.get("font_size", 18)
    cursor.CharWeight = 150.0 if el.get("bold") else 100.0
    cursor.CharPosture = uno.Enum(
        "com.sun.star.awt.FontSlant", "ITALIC" if el.get("italic") else "NONE"
    )
    cursor.CharColor = hex_to_color(el.get("font_color", "#000000"))
    align = el.get("align", "left")
    if align not in _PARA_ADJUST:
        raise ValueError(f"align must be one of {list(_PARA_ADJUST)}, got {align!r}")
    cursor.ParaAdjust = _PARA_ADJUST[align]


def _create_basic_shape(doc, page, el):
    shape = doc.createInstance(_SHAPE_SERVICE[el["type"]])
    page.add(shape)
    _position_and_size(shape, el)

    fill_color = el.get("fill_color")
    if fill_color:
        shape.FillStyle = uno.Enum("com.sun.star.drawing.FillStyle", "SOLID")
        shape.FillColor = hex_to_color(fill_color)
    else:
        shape.FillStyle = uno.Enum("com.sun.star.drawing.FillStyle", "NONE")

    line_color = el.get("line_color", "#000000")
    if line_color:
        shape.LineStyle = uno.Enum("com.sun.star.drawing.LineStyle", "SOLID")
        shape.LineColor = hex_to_color(line_color)
        shape.LineWidth = round(el.get("line_width", 1) * 35.28)  # pt -> 1/100mm
    else:
        shape.LineStyle = uno.Enum("com.sun.star.drawing.LineStyle", "NONE")

    text = el.get("text")
    if text:
        shape.TextWordWrap = True
        shape.setString(text)
        valign = el.get("valign", "middle")
        if valign not in _VERT_ADJUST:
            raise ValueError(f"valign must be one of {list(_VERT_ADJUST)}, got {valign!r}")
        shape.TextVerticalAdjust = _VERT_ADJUST[valign]
        _apply_text_formatting(shape.Text.createTextCursor(), el)

    return shape


def _create_line(doc, page, el):
    for key in ("x1", "y1", "x2", "y2"):
        if key not in el:
            raise ValueError(f"line element requires '{key}' (in inches)")

    p1 = Point(inches(el["x1"]), inches(el["y1"]))
    p2 = Point(inches(el["x2"]), inches(el["y2"]))

    shape = doc.createInstance("com.sun.star.drawing.LineShape")
    page.add(shape)
    # A LineShape's Position/Size (a bounding-box rectangle) always draws
    # from that box's top-left to its bottom-right corner, which silently
    # flips the direction -- and therefore which end any arrowhead lands
    # on -- for a line whose start is right-of/below its end. Setting
    # PolyPolygon directly (the shape's actual point list) preserves the
    # exact (x1,y1) -> (x2,y2) order we were given.
    shape.PolyPolygon = ((p1, p2),)

    line_color = el.get("line_color", "#000000")
    if line_color:
        shape.LineStyle = uno.Enum("com.sun.star.drawing.LineStyle", "SOLID")
        shape.LineColor = hex_to_color(line_color)
    else:
        shape.LineStyle = uno.Enum("com.sun.star.drawing.LineStyle", "NONE")
    shape.LineWidth = round(el.get("line_width", 1) * 35.28)  # pt -> 1/100mm

    arrow_size = round(el.get("arrow_size", 0.12) * inches(1))
    if el.get("arrow_end"):
        shape.LineEndName = "Arrow"
        shape.LineEndWidth = arrow_size
    if el.get("arrow_start"):
        shape.LineStartName = "Arrow"
        shape.LineStartWidth = arrow_size

    return shape


def _create_text(doc, page, el):
    shape = doc.createInstance("com.sun.star.drawing.TextShape")
    page.add(shape)
    _position_and_size(shape, el)

    shape.TextWordWrap = True
    shape.TextAutoGrowHeight = False
    shape.TextAutoGrowWidth = False

    horiz = el.get("align", "left")
    if horiz not in _HORIZ_ADJUST:
        raise ValueError(f"align must be one of {list(_HORIZ_ADJUST)}, got {horiz!r}")
    shape.TextHorizontalAdjust = uno.Enum(
        "com.sun.star.drawing.TextHorizontalAdjust", _HORIZ_ADJUST[horiz]
    )
    valign = el.get("valign", "top")
    if valign not in _VERT_ADJUST:
        raise ValueError(f"valign must be one of {list(_VERT_ADJUST)}, got {valign!r}")
    shape.TextVerticalAdjust = _VERT_ADJUST[valign]

    shape.setString(el.get("text", ""))
    _apply_text_formatting(shape.Text.createTextCursor(), el)
    return shape


def _create_table(doc, page, el):
    rows_data = el.get("rows")
    if not rows_data or not rows_data[0]:
        raise ValueError("table element requires a non-empty 'rows' list of lists")
    n_rows = len(rows_data)
    n_cols = len(rows_data[0])
    for r in rows_data:
        if len(r) != n_cols:
            raise ValueError("every row in a table must have the same number of cells")

    shape = doc.createInstance("com.sun.star.presentation.TableShape")
    page.add(shape)
    _position_and_size(shape, el)

    model = shape.Model
    if n_rows > model.RowCount:
        model.Rows.insertByIndex(model.RowCount, n_rows - model.RowCount)
    if n_cols > model.ColumnCount:
        model.Columns.insertByIndex(model.ColumnCount, n_cols - model.ColumnCount)

    # Distribute column widths (equal by default, or per col_widths ratios).
    # Newly-inserted rows/columns default to 0 width/height until set
    # explicitly, so both must always be assigned here.
    total_width = inches(el["width"])
    col_widths = el.get("col_widths") or [1] * n_cols
    if len(col_widths) != n_cols:
        raise ValueError("col_widths must have one entry per column")
    weight_sum = sum(col_widths)
    for i in range(n_cols):
        model.Columns.getByIndex(i).Width = round(total_width * col_widths[i] / weight_sum)

    total_height = inches(el["height"])
    row_heights = el.get("row_heights") or [1] * n_rows
    if len(row_heights) != n_rows:
        raise ValueError("row_heights must have one entry per row")
    weight_sum = sum(row_heights)
    for i in range(n_rows):
        model.Rows.getByIndex(i).Height = round(total_height * row_heights[i] / weight_sum)

    header_fill = el.get("header_fill_color")
    body_fill = el.get("fill_color")
    header_font_color = el.get("header_font_color", el.get("font_color", "#000000"))

    for r in range(n_rows):
        for c in range(n_cols):
            cell = model.getCellByPosition(c, r)
            cell.setString(str(rows_data[r][c]))

            fill = header_fill if (r == 0 and header_fill) else body_fill
            if fill:
                cell.FillColor = hex_to_color(fill)

            cursor = cell.Text.createTextCursor()
            cursor.gotoStart(False)
            cursor.gotoEnd(True)
            if el.get("font_family"):
                cursor.CharFontName = el["font_family"]
            cursor.CharHeight = el.get("font_size", 14)
            cursor.CharWeight = 150.0 if (r == 0 or el.get("bold")) else 100.0
            font_color = header_font_color if r == 0 else el.get("font_color", "#000000")
            cursor.CharColor = hex_to_color(font_color)
            align = el.get("align", "left")
            if align not in _PARA_ADJUST:
                raise ValueError(f"align must be one of {list(_PARA_ADJUST)}, got {align!r}")
            cursor.ParaAdjust = _PARA_ADJUST[align]

    return shape


def _create_image(doc, page, el):
    icon_name = el.get("icon")
    path = resolve_icon(icon_name, el.get("icons_dir")) if icon_name else el.get("path")
    if not path:
        raise ValueError("image element requires either 'icon' or 'path'")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"image not found: {path}")

    # Note: loading the image via a com.sun.star.graphic.GraphicProvider
    # instantiated from uno.getComponentContext() looks like the "proper"
    # UNO way to do this, but that call returns the *local* client-process
    # context rather than the remote LibreOffice one -- assigning a graphic
    # built from the wrong context into a remote shape's Graphic property
    # corrupts the cross-process bridge and crashes LibreOffice. Setting
    # GraphicURL directly (a plain string property on the shape, resolved
    # inside the remote process) avoids the mismatch entirely.
    shape = doc.createInstance("com.sun.star.drawing.GraphicObjectShape")
    page.add(shape)
    _position_and_size(shape, el)
    shape.GraphicURL = uno.systemPathToFileUrl(os.path.abspath(path))
    return shape
