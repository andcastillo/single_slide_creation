from .connection import connect, launch
from .builder import open_deck, add_slide, save_deck, create_or_append_slide
from .theme import load_theme, apply_theme
from .icons import resolve_icon

__all__ = [
    "connect",
    "launch",
    "open_deck",
    "add_slide",
    "save_deck",
    "create_or_append_slide",
    "load_theme",
    "apply_theme",
    "resolve_icon",
]
