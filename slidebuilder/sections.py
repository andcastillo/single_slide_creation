"""
Splits a slide instructions file into its named sections.

A slide's .txt file is the slide description (the "body", sent to the
LLM) optionally followed by extra sections, each started by a marker line
of the form `=== NAME ===`:

    TITLE: "MONOVALUADO VS. MULTIVALUADO"
    The slide will show ...            <- body: sent to the LLM

    === SPEAKER NOTES ===
    Copied verbatim into the slide's speaker notes -- never sent to the LLM.

    === COMMENT ===
    Copied verbatim into a review comment on the slide -- never sent to the
    LLM. A good place to describe the animations to build by hand.

Only the body goes to the LLM, so a section's text comes through exactly
as written, costs no prompt tokens, and can be edited and re-applied with
--use-cache without another LLM call.

A section that's absent and one that's present but empty are
distinguished (None vs. ""): both mean "add nothing" today, but empty is
an explicit "none for this slide" -- kept separate so a future
LLM-generated-notes option can still honor it.
"""

import re

SPEAKER_NOTES = "SPEAKER NOTES"
COMMENT = "COMMENT"
KNOWN_SECTIONS = (SPEAKER_NOTES, COMMENT)

_MARKER_RE = re.compile(r"^\s*===\s*(.*?)\s*===\s*$")


def parse_instructions(text: str) -> dict:
    """Split instructions text into {"body": str, SPEAKER_NOTES: str | None,
    COMMENT: str | None}.

    Every value is stripped of surrounding whitespace. Section names are
    matched case-insensitively (and with runs of spaces collapsed). Raises
    ValueError for an unknown section name -- so a typo like
    `=== SPEAKR NOTES ===` fails loudly instead of its text silently
    ending up in the prompt -- or for a section given twice.
    """
    result = {"body": None, **{name: None for name in KNOWN_SECTIONS}}
    current = "body"
    lines = {"body": []}

    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _MARKER_RE.match(line)
        if not m:
            lines[current].append(line)
            continue
        name = " ".join(m.group(1).upper().split())
        if name not in KNOWN_SECTIONS:
            raise ValueError(
                f"line {lineno}: unknown section marker {line.strip()!r} -- "
                f"expected one of: {', '.join(f'=== {n} ===' for n in KNOWN_SECTIONS)}"
            )
        if name in lines:
            raise ValueError(f"line {lineno}: section '=== {name} ===' appears more than once")
        current = name
        lines[current] = []

    for name, section_lines in lines.items():
        result[name] = "\n".join(section_lines).strip()
    return result
