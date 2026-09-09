"""
Demonstrates theme.json (styles + color tokens) and the icons/ folder.

Run with: /usr/bin/python3 examples/themed_example.py
(requires LibreOffice already running -- see README.md)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slidebuilder import connect, create_or_append_slide, load_theme

THEME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "theme.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "themed_output_deck.pptx")

# Elements reference a named style from theme.json via "style"; any field
# can still be overridden per-element (e.g. position/size/text always are).
ELEMENTS = [
    {
        "type": "rectangle", "style": "title",
        "x": 0.5, "y": 0.4, "width": 12.33, "height": 1.0,
        "text": "Platform Overview",
    },
    {
        "type": "text", "style": "subtitle",
        "x": 0.5, "y": 1.6, "width": 6.0, "height": 0.5,
        "text": "Architecture",
    },
    {
        "type": "table", "style": "table",
        "x": 0.5, "y": 2.2, "width": 6.0, "height": 1.6,
        "rows": [["Component", "Status"], ["API", "Live"], ["Chatbot", "Beta"]],
        "col_widths": [2, 1],
    },
    {
        "type": "oval", "style": "callout",
        "x": 7.2, "y": 1.6, "width": 1.6, "height": 1.6,
        "text": "Live",
    },
    # Icons referenced by name from icons/ -- no path needed.
    {"type": "image", "icon": "person", "x": 9.2, "y": 1.6, "width": 1.0, "height": 1.0},
    {"type": "image", "icon": "chatbot", "x": 10.4, "y": 1.6, "width": 1.0, "height": 1.0},
    {"type": "image", "icon": "cloud", "x": 9.2, "y": 2.8, "width": 1.0, "height": 1.0},
    {"type": "image", "icon": "computer", "x": 10.4, "y": 2.8, "width": 1.0, "height": 1.0},
    {"type": "image", "icon": "chat_icon", "x": 9.2, "y": 4.0, "width": 1.0, "height": 1.0},
]

if __name__ == "__main__":
    ctx, desktop = connect()
    theme = load_theme(THEME_PATH)
    doc, page = create_or_append_slide(desktop, OUT_PATH, ELEMENTS, theme=theme)
    print(f"Slide added. Saved to {OUT_PATH}")
    print(f"Deck now has {doc.DrawPages.Count} slide(s).")
