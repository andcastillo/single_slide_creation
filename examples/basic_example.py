"""
Run with: /usr/bin/python3 examples/basic_example.py

Requires LibreOffice already running and listening on the UNO socket, e.g.:

    soffice --impress \
        -env:UserInstallation=file:///tmp/lo_automation_profile \
        --accept="socket,host=localhost,port=2002;urp;" \
        --norestore --nologo
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slidebuilder import connect, create_or_append_slide

OUT_PATH = os.path.join(os.path.dirname(__file__), "output_deck.pptx")

ELEMENTS = [
    {
        "type": "rectangle",
        "x": 0.5, "y": 0.4, "width": 12.33, "height": 1.0,
        "fill_color": "#1F4E79",
        "line_color": None,
        "text": "Quarterly Review",
        "font_color": "#FFFFFF",
        "font_size": 32,
        "bold": True,
        "align": "center",
        "valign": "middle",
    },
    {
        "type": "text",
        "x": 0.5, "y": 1.6, "width": 6.0, "height": 0.5,
        "text": "Key metrics",
        "font_size": 20,
        "bold": True,
        "font_color": "#1F4E79",
        "align": "left",
    },
    {
        "type": "table",
        "x": 0.5, "y": 2.2, "width": 6.0, "height": 2.0,
        "rows": [
            ["Metric", "Q1", "Q2"],
            ["Revenue", "$1.2M", "$1.5M"],
            ["Churn", "2.1%", "1.8%"],
        ],
        "col_widths": [2, 1, 1],
        "header_fill_color": "#1F4E79",
        "header_font_color": "#FFFFFF",
        "fill_color": "#F2F2F2",
        "font_size": 14,
        "align": "center",
    },
    {
        "type": "oval",
        "x": 7.0, "y": 1.6, "width": 2.0, "height": 2.0,
        "fill_color": "#70AD47",
        "line_color": "#375623",
        "line_width": 2,
        "text": "On\nTrack",
        "font_color": "#FFFFFF",
        "font_size": 16,
        "bold": True,
        "align": "center",
        "valign": "middle",
    },
]

_icon_path = os.path.join(os.path.dirname(__file__), "sample_icon.png")
if os.path.isfile(_icon_path):
    ELEMENTS.append(
        {"type": "image", "x": 10.0, "y": 1.6, "width": 1.0, "height": 1.0, "path": _icon_path}
    )

if __name__ == "__main__":
    ctx, desktop = connect()
    doc, page = create_or_append_slide(desktop, OUT_PATH, ELEMENTS)
    print(f"Slide added. Saved to {OUT_PATH}")
    print(f"Deck now has {doc.DrawPages.Count} slide(s).")
