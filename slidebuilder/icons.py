"""
Resolve a predefined icon name (e.g. "person") to a file path in the
project's icons/ folder.
"""

import os

DEFAULT_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons"
)

_EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg")


def resolve_icon(name: str, icons_dir: str | None = None) -> str:
    """Return the file path for icon `name`, searching `icons_dir` (default:
    the repo's icons/ folder) for name.svg, then .png, .jpg, .jpeg.

    Raises FileNotFoundError (listing the icons that ARE available) if none
    of those files exist.
    """
    icons_dir = icons_dir or DEFAULT_ICONS_DIR
    for ext in _EXTENSIONS:
        candidate = os.path.join(icons_dir, name + ext)
        if os.path.isfile(candidate):
            return candidate

    available = sorted(
        {
            os.path.splitext(f)[0]
            for f in os.listdir(icons_dir)
            if os.path.splitext(f)[1].lower() in _EXTENSIONS
        }
        if os.path.isdir(icons_dir)
        else []
    )
    raise FileNotFoundError(
        f"No icon named {name!r} in {icons_dir}. "
        f"Available icons: {', '.join(available) if available else '(none found)'}"
    )
