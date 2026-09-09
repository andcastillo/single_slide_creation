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

import os

import uno
from com.sun.star.beans import PropertyValue

from .elements import create_element
from .theme import apply_theme, load_theme

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


def open_deck(desktop, path: str | None):
    """Open an existing deck, reusing it if already open in this LibreOffice
    instance, or create a brand-new blank presentation if `path` is None or
    doesn't exist yet.

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

    # No existing file: create a fresh blank presentation.
    doc = desktop.loadComponentFromURL(
        "private:factory/simpress", "_blank", 0, (_mkprop("Hidden", False),)
    )
    return doc, True


def add_slide(
    doc,
    elements: list[dict],
    is_new: bool = False,
    index: int | None = None,
    theme: dict | str | None = None,
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
    """
    if isinstance(theme, str):
        theme = load_theme(theme)

    pages = doc.DrawPages

    if is_new and pages.Count == 1:
        # Reuse the single default page a freshly-created presentation
        # starts with (it may already carry title/content placeholder
        # shapes -- setting Layout below clears those).
        page = pages.getByIndex(0)
    else:
        insert_at = pages.Count if index is None else index
        pages.insertNewByIndex(insert_at)
        page = pages.getByIndex(insert_at)

    page.Layout = BLANK_LAYOUT

    for el in elements:
        if theme is not None:
            el = apply_theme(theme, el)
        create_element(doc, page, el)

    return page


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


def create_or_append_slide(
    desktop,
    path: str,
    elements: list[dict],
    index: int | None = None,
    theme: dict | str | None = None,
):
    """Convenience one-shot wrapper: open (or create) the deck at `path`,
    append a slide built from `elements` (optionally styled via `theme`),
    save, and return (doc, page).

    The document is left open in the LibreOffice window (not closed) so you
    can keep inspecting/editing it, or call this again to add more slides.
    """
    doc, is_new = open_deck(desktop, path)
    page = add_slide(doc, elements, is_new=is_new, index=index, theme=theme)
    save_deck(doc, path)
    return doc, page
