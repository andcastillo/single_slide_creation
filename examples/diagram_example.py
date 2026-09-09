"""
Process-flow diagram: two input documents feed into a process box, which
produces one output document, connected with arrowed lines.

Demonstrates the "line" element (explicit x1,y1 -> x2,y2 endpoints, with
arrowheads) and the "document" icon, both added for this use case -- see
README.md's "Process-flow diagrams" section.

Run with: /usr/bin/python3 examples/diagram_example.py
(requires LibreOffice already running -- see README.md)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slidebuilder import connect, create_or_append_slide, load_theme

THEME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "theme.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "diagram_output_deck.pptx")

ICON_SIZE = 1.0

# Input document icons (left column) and their vertical centers.
IN1 = {"x": 0.8, "y": 1.6}
IN2 = {"x": 0.8, "y": 4.6}
# Process box.
BOX = {"x": 3.6, "y": 3.0, "width": 3.0, "height": 1.5}
# Output document icon.
OUT = {"x": 8.2, "y": 3.25}


def center_y(pos):
    return pos["y"] + ICON_SIZE / 2


ELEMENTS = [
    {
        "type": "rectangle", "style": "title",
        "x": 0.5, "y": 0.3, "width": 9.0, "height": 0.9,
        "text": "Document Summarization Pipeline",
    },
    # Connector lines first, so the icons/box are drawn on top of the line ends.
    {
        "type": "line", "style": "connector",
        "x1": IN1["x"] + ICON_SIZE, "y1": center_y(IN1),
        "x2": BOX["x"], "y2": BOX["y"] + BOX["height"] / 2,
    },
    {
        "type": "line", "style": "connector",
        "x1": IN2["x"] + ICON_SIZE, "y1": center_y(IN2),
        "x2": BOX["x"], "y2": BOX["y"] + BOX["height"] / 2,
    },
    {
        "type": "line", "style": "connector",
        "x1": BOX["x"] + BOX["width"], "y1": BOX["y"] + BOX["height"] / 2,
        "x2": OUT["x"], "y2": center_y(OUT),
    },
    # Input documents.
    {"type": "image", "icon": "document", "x": IN1["x"], "y": IN1["y"],
     "width": ICON_SIZE, "height": ICON_SIZE},
    {"type": "text", "style": "caption",
     "x": IN1["x"] - 0.3, "y": IN1["y"] + ICON_SIZE + 0.05, "width": 1.6, "height": 0.3,
     "text": "Document A", "align": "center"},
    {"type": "image", "icon": "document", "x": IN2["x"], "y": IN2["y"],
     "width": ICON_SIZE, "height": ICON_SIZE},
    {"type": "text", "style": "caption",
     "x": IN2["x"] - 0.3, "y": IN2["y"] + ICON_SIZE + 0.05, "width": 1.6, "height": 0.3,
     "text": "Document B", "align": "center"},
    # Process box.
    {
        "type": "rectangle", "style": "process",
        "x": BOX["x"], "y": BOX["y"], "width": BOX["width"], "height": BOX["height"],
        "text": "Summarization and Comprehension",
    },
    # Output document.
    {"type": "image", "icon": "document", "x": OUT["x"], "y": OUT["y"],
     "width": ICON_SIZE, "height": ICON_SIZE},
    {"type": "text", "style": "caption",
     "x": OUT["x"] - 0.3, "y": OUT["y"] + ICON_SIZE + 0.05, "width": 1.6, "height": 0.3,
     "text": "Summary", "align": "center"},
]

if __name__ == "__main__":
    ctx, desktop = connect()
    theme = load_theme(THEME_PATH)
    doc, page = create_or_append_slide(desktop, OUT_PATH, ELEMENTS, theme=theme)
    print(f"Slide added. Saved to {OUT_PATH}")
    print(f"Deck now has {doc.DrawPages.Count} slide(s).")
