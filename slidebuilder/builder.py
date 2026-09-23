"""
High-level functions: open/create a deck, append a slide built from a list
of element definitions, and save it back to disk.

Typical usage (from a Python interpreter that can `import uno`, i.e.
/usr/bin/python3 on this machine -- see slidebuilder/connection.py):

    from slidebuilder.connection import connect
    from slidebuilder.builder import open_deck, add_slide, save_deck

    ctx, desktop = connect()
    doc, is_new = open_deck(desktop, "/path/to/deck.pptx")
    add_slide(doc, [
        {"type": "rectangle", "x": 1, "y": 1, "width": 4, "height": 1.5,
         "fill_color": "#1F4E79", "text": "Hello", "font_color": "#FFFFFF",
         "align": "center", "valign": "middle", "font_size": 28},
    ])
    save_deck(doc, "/path/to/deck.pptx")

Because open_deck() reuses an already-open document instead of reloading it,
you can call add_slide()/save_deck() again later in a fresh script -- any
manual edits you made in the LibreOffice window in between are preserved.
"""

import datetime
import os
import re
import tempfile
import zipfile

import uno
from com.sun.star.beans import PropertyValue

from .elements import create_element
from .theme import apply_theme, load_theme
from .units import DEFAULT_SLIDE_HEIGHT_IN, DEFAULT_SLIDE_WIDTH_IN, inches, to_inches

BLANK_LAYOUT = 20  # com.sun.star.presentation.DrawPage Layout: no placeholders

_FILTER_BY_EXT = {
    ".pptx": "Impress MS PowerPoint 2007 XML",
    ".ppt": "MS PowerPoint 97",
    ".odp": "impress8",
}


def _mkprop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _find_open_doc(desktop, file_url: str):
    """Return an already-open Impress document matching file_url, if any."""
    it = desktop.Components.createEnumeration()
    while it.hasMoreElements():
        comp = it.nextElement()
        if hasattr(comp, "DrawPages") and getattr(comp, "getURL", None):
            if comp.getURL() == file_url:
                return comp
    return None


def open_deck(
    desktop,
    path: str | None,
    width_in: float = DEFAULT_SLIDE_WIDTH_IN,
    height_in: float = DEFAULT_SLIDE_HEIGHT_IN,
):
    """Open an existing deck, reusing it if already open in this LibreOffice
    instance, or create a brand-new blank presentation if `path` is None or
    doesn't exist yet.

    width_in/height_in only matter for that brand-new case: a fresh
    presentation is given this page size explicitly, rather than left at
    whatever LibreOffice's own internal default happens to be (confirmed
    NOT to be 10x7.5in on this machine -- see units.py). Ignored when
    opening/reusing an existing deck, so its actual page size (whatever it
    already is) is never overridden.

    Returns (doc, is_new) where is_new is True if the returned document has
    no content slides yet (a freshly created presentation, whose single
    default blank page should be reused rather than appended after).
    """
    if path is not None:
        path = os.path.abspath(path)

    if path:
        file_url = uno.systemPathToFileUrl(path)
        # Check for an already-open document with this URL first, even if
        # the file no longer exists on disk (e.g. it was only ever saved
        # in-memory under this identity) -- a live document always takes
        # precedence over reloading/recreating.
        doc = _find_open_doc(desktop, file_url)
        if doc is not None:
            return doc, False
        if os.path.isfile(path):
            doc = desktop.loadComponentFromURL(
                file_url, "_blank", 0, (_mkprop("Hidden", False),)
            )
            return doc, False

    # No existing file: create a fresh blank presentation, with an explicit
    # page size (see the width_in/height_in docstring note above).
    doc = desktop.loadComponentFromURL(
        "private:factory/simpress", "_blank", 0, (_mkprop("Hidden", False),)
    )
    page = doc.DrawPages.getByIndex(0)
    page.Width = inches(width_in)
    page.Height = inches(height_in)
    return doc, True


def get_page_size_in(doc) -> tuple[float, float]:
    """Return (width_in, height_in) -- `doc`'s actual current page size, in
    inches. For a deck open_deck() just created, this simply echoes back
    whatever width_in/height_in was passed to it; for an existing deck, it's
    that deck's real, already-established size (whatever that is), which
    open_deck() never touches. Use this rather than assuming a deck matches
    DEFAULT_SLIDE_WIDTH_IN/HEIGHT_IN -- an existing deck's actual size can
    be anything.
    """
    page = doc.DrawPages.getByIndex(0)
    return to_inches(page.Width), to_inches(page.Height)


_NOTES_SHAPE_TYPE = "com.sun.star.presentation.NotesShape"


def _notes_shape(page):
    """Return the speaker-notes text shape on `page`'s notes page, or None.
    Confirmed present by default even on a BLANK_LAYOUT slide."""
    notes_page = page.NotesPage
    for i in range(notes_page.Count):
        shape = notes_page.getByIndex(i)
        if shape.ShapeType == _NOTES_SHAPE_TYPE:
            return shape
    return None


def set_notes(doc, page, text: str):
    """Set `page`'s speaker notes to `text` (plain text; newlines become
    separate paragraphs), replacing whatever notes it had. Creates the
    notes text shape if the notes page somehow lacks one. Exported to
    .pptx as a standard notesSlide, shown in PowerPoint's presenter view.
    """
    shape = _notes_shape(page)
    if shape is None:
        shape = doc.createInstance(_NOTES_SHAPE_TYPE)
        page.NotesPage.add(shape)
    shape.String = text


def get_notes(page) -> str:
    """Return `page`'s speaker notes as plain text ("" if none)."""
    shape = _notes_shape(page)
    return shape.String if shape is not None else ""


def add_comment(page, text: str, author: str = "slidebuilder", initials: str | None = None):
    """Attach a review comment (an Impress "annotation") holding `text` to
    `page`, pinned near its top-right corner. Exported to .pptx as a
    (legacy-format) slide comment.
    """
    now = datetime.datetime.now()
    stamp = uno.createUnoStruct("com.sun.star.util.DateTime")
    stamp.Year, stamp.Month, stamp.Day = now.year, now.month, now.day
    stamp.Hours, stamp.Minutes, stamp.Seconds = now.hour, now.minute, now.second

    annotation = page.createAndInsertAnnotation()
    annotation.Author = author
    annotation.Initials = initials if initials is not None else "".join(w[0] for w in author.split()).upper()[:3]
    annotation.DateTime = stamp
    # Position is in millimeters (page.Width is in 1/100 mm).
    annotation.Position = uno.createUnoStruct(
        "com.sun.star.geometry.RealPoint2D", max(page.Width / 100 - 15.0, 0.0), 5.0
    )
    annotation.TextRange.String = text
    return annotation


def _move_notes_and_comments(doc, src, dst):
    """Move `src`'s speaker notes and comments onto `dst`.

    Notes move as plain text, so formatting applied to them by hand in the
    GUI (bold, etc.) is lost. Moving the notes shape itself instead was
    tried and is NOT reliable: confirmed, right after a Layout change the
    moved shape can silently turn from a notes placeholder into a plain
    text shape, which is then not exported as speaker notes at all.
    Comments have no move API, so each is recreated on `dst` and removed
    from `src`.
    """
    text = get_notes(src)
    if text:
        set_notes(doc, dst, text)
        _notes_shape(src).String = ""

    annotations = []
    it = src.createAnnotationEnumeration()
    while it.hasMoreElements():
        annotations.append(it.nextElement())
    for old in annotations:
        new = dst.createAndInsertAnnotation()
        new.Author = old.Author
        new.Initials = old.Initials
        new.DateTime = old.DateTime
        new.Position = old.Position
        new.TextRange.String = old.TextRange.String
        src.removeAnnotation(old)


def add_slide(
    doc,
    elements: list[dict],
    is_new: bool = False,
    index: int | None = None,
    theme: dict | str | None = None,
    notes: str | None = None,
    comment: str | None = None,
    comment_author: str = "slidebuilder",
):
    """Append a slide built from `elements` to `doc` and return the new page.

    If is_new is True (freshly created presentation), the existing default
    blank page is reused instead of inserting an extra one after it.
    If `index` is given, the slide is inserted at that position instead of
    the end.

    `theme` (a dict from theme.load_theme(), or a path string to a theme
    JSON file) is optional. When given, each element's "style" field (if
    present) is resolved against theme["styles"] and "$color" tokens are
    resolved against theme["colors"] before the element is created -- see
    slidebuilder/theme.py.

    `notes`, if non-empty, becomes the slide's speaker notes (see
    set_notes()); `comment`, if non-empty, is attached as a review comment
    by `comment_author` (see add_comment()). None or "" adds nothing.
    """
    if isinstance(theme, str):
        theme = load_theme(theme)

    pages = doc.DrawPages

    if is_new and pages.Count == 1:
        # Reuse the single default page a freshly-created presentation
        # starts with (it may already carry title/content placeholder
        # shapes -- setting Layout below clears those).
        page = pages.getByIndex(0)
    elif index is None:
        # insertNewByIndex(n) lands the new page at n+1 (see below) --
        # but at this upper boundary (n == Count, one past the last valid
        # index) it clamps to a plain append, landing at exactly Count as
        # expected, so no adjustment is needed for the common append case.
        insert_at = pages.Count
        pages.insertNewByIndex(insert_at)
        page = pages.getByIndex(insert_at)
    elif index == 0:
        # insertNewByIndex(n) always lands the new page at n+1, for every
        # n (including 0, and even -1 which just clamps to append) -- so
        # there's no n that lands a page AT index 0. Work around it by
        # inserting after the current first page (-> lands at index 1),
        # then swapping the two pages' shapes so the new page ends up
        # holding the *old* first page's content and vice versa -- i.e.
        # the freshly generated slide ends up at index 0 as requested.
        # Its speaker notes and comments have to move along with the
        # shapes too -- confirmed: otherwise they stay behind on index 0,
        # attached to the new slide instead of the one they were written for.
        old_first = pages.getByIndex(0)
        pages.insertNewByIndex(0)
        new_page = pages.getByIndex(1)
        for shape in list(old_first):
            old_first.remove(shape)
            new_page.add(shape)
        new_page.Layout = old_first.Layout
        _move_notes_and_comments(doc, old_first, new_page)
        page = old_first
    else:
        # insertNewByIndex(n) lands the new page at n+1, so to land it AT
        # `index` we must insert after `index - 1` instead.
        pages.insertNewByIndex(index - 1)
        page = pages.getByIndex(index)

    page.Layout = BLANK_LAYOUT

    for el in elements:
        if theme is not None:
            el = apply_theme(theme, el)
        create_element(doc, page, el)

    if notes:
        set_notes(doc, page, notes)
    if comment:
        add_comment(page, comment, author=comment_author)

    return page


_BODY_PR_RE = re.compile(rb"<a:bodyPr(\s[^>]*)?(/?)>")
_SLIDE_XML_RE = re.compile(r"ppt/slides/slide\d+\.xml$")


def _ensure_wrap_square(xml_bytes: bytes) -> bytes:
    def add_wrap(m):
        attrs, self_close = m.group(1) or b"", m.group(2) or b""
        if b"wrap=" in attrs:
            return m.group(0)
        return b'<a:bodyPr wrap="square"' + attrs + self_close + b">"

    return _BODY_PR_RE.sub(add_wrap, xml_bytes)


def _force_pptx_text_wrap(path: str):
    """LibreOffice's own pptx export leaves the wrap="square" attribute off
    every <a:bodyPr> (relying on it being the OOXML spec default rather
    than stating it), and that turns out not to be interpreted consistently
    -- observed directly: the same file rendered word-wrapped via one
    LibreOffice profile/session but showed unwrapped, overflowing text
    when freshly opened in another. This patches every <a:bodyPr> in every
    slide of the just-saved pptx to state wrap="square" explicitly, so it
    can't be read either way.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pptx", dir=os.path.dirname(path) or ".")
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(
            tmp_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if _SLIDE_XML_RE.search(item.filename):
                    data = _ensure_wrap_square(data)
                zout.writestr(item, data)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def save_deck(doc, path: str):
    """Save `doc` to `path`, choosing the export filter from its extension
    (.pptx, .ppt, or .odp)."""
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    filter_name = _FILTER_BY_EXT.get(ext)
    if filter_name is None:
        raise ValueError(
            f"Unsupported extension {ext!r}; expected one of {list(_FILTER_BY_EXT)}"
        )
    url = uno.systemPathToFileUrl(path)
    # storeAsURL (not storeToURL) so the document's own identity/URL is
    # updated to `path` -- that's what lets a later open_deck() call find
    # this same live, already-open document instead of loading a stale
    # second copy from disk.
    doc.storeAsURL(url, (_mkprop("FilterName", filter_name), _mkprop("Overwrite", True)))
    if ext == ".pptx":
        _force_pptx_text_wrap(path)


def create_or_append_slide(
    desktop,
    path: str,
    elements: list[dict],
    index: int | None = None,
    theme: dict | str | None = None,
    width_in: float = DEFAULT_SLIDE_WIDTH_IN,
    height_in: float = DEFAULT_SLIDE_HEIGHT_IN,
    notes: str | None = None,
    comment: str | None = None,
    comment_author: str = "slidebuilder",
):
    """Convenience one-shot wrapper: open (or create) the deck at `path`,
    append a slide built from `elements` (optionally styled via `theme`),
    save, and return (doc, page).

    width_in/height_in are passed straight to open_deck() -- see its
    docstring; in short, they only take effect if `path` doesn't exist yet
    (a brand-new deck), never overriding an existing deck's actual size.

    notes/comment/comment_author are passed straight to add_slide().

    The document is left open in the LibreOffice window (not closed) so you
    can keep inspecting/editing it, or call this again to add more slides.
    """
    doc, is_new = open_deck(desktop, path, width_in=width_in, height_in=height_in)
    page = add_slide(
        doc, elements, is_new=is_new, index=index, theme=theme,
        notes=notes, comment=comment, comment_author=comment_author,
    )
    save_deck(doc, path)
    return doc, page
