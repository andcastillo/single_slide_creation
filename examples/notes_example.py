"""
Demonstrates speaker notes and slide comments from the library API.

Run with: /usr/bin/python3 examples/notes_example.py
(requires LibreOffice already running -- see README.md)

Open the result in Impress and check View > Notes for the speaker notes,
and the comment marker near the slide's top-right corner. For the same
thing driven from an instructions file (=== SPEAKER NOTES === /
=== COMMENT === sections), see examples/sample_instructions_notes.txt.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slidebuilder import connect, create_or_append_slide, load_theme

THEME_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "theme.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "notes_output_deck.pptx")

ELEMENTS = [
    {
        "type": "rectangle", "style": "title",
        "x": 0.5, "y": 0.4, "width": 9.0, "height": 1.0,
        "text": "Quarterly Review",
    },
    {
        "type": "text", "style": "body",
        "x": 0.5, "y": 1.8, "width": 9.0, "height": 1.5,
        "text": "Revenue grew 12% quarter over quarter.",
    },
]

# Plain text; each line becomes its own paragraph in the notes.
NOTES = """Open with the headline number: 12% growth.

Mention that most of it came from the new enterprise tier."""

COMMENT = "Animation: fade in the body text on click."

if __name__ == "__main__":
    ctx, desktop = connect()
    theme = load_theme(THEME_PATH)
    doc, page = create_or_append_slide(
        desktop, OUT_PATH, ELEMENTS, theme=theme,
        notes=NOTES, comment=COMMENT, comment_author="slidebuilder",
    )
    print(f"Slide added with speaker notes and a comment. Saved to {OUT_PATH}")
    print(f"Deck now has {doc.DrawPages.Count} slide(s).")
