#!/usr/bin/env /usr/bin/python3
"""
Turn a natural-language slide description into a slide, via a local LLM.

    1. Read a plain-text instructions file (a description of ONE slide).
    2. Build the system prompt from theme.json + icons/ (slidebuilder.prompt),
       and send it + the instructions to a local LLM (LM Studio's OpenAI-
       compatible server) to get back slidebuilder element definitions.
    3. Validate those elements, then add them as a slide in the LibreOffice
       session already running (via the UNO socket) -- creating the deck if
       it doesn't exist yet, or appending if it does.

Prerequisites:
    - LibreOffice running and listening on the UNO socket (see README.md).
    - LM Studio's local server running with a model loaded:
          lms server start
          lms load qwen/qwen3.5-9b --context-length 16384

Usage:
    /usr/bin/python3 generate_slide.py instructions.txt
    /usr/bin/python3 generate_slide.py instructions.txt --deck examples/my_deck.pptx
    /usr/bin/python3 generate_slide.py instructions.txt --model qwen/qwen3.5-9b --show-prompt
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slidebuilder import connect, create_or_append_slide, load_theme
from slidebuilder.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, generate_elements, validate_elements
from slidebuilder.prompt import build_system_prompt

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_THEME_PATH = os.path.join(REPO_ROOT, "theme.json")
DEFAULT_ICONS_DIR = os.path.join(REPO_ROOT, "icons")
DEFAULT_DECK_PATH = os.path.join(REPO_ROOT, "examples", "generated_deck.pptx")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instructions_file", help="Path to a text file describing the slide in natural language")
    parser.add_argument("--deck", default=DEFAULT_DECK_PATH, help=f"Output .pptx path (default: {DEFAULT_DECK_PATH})")
    parser.add_argument("--theme", default=DEFAULT_THEME_PATH, help="Path to theme JSON (default: theme.json)")
    parser.add_argument("--icons-dir", default=DEFAULT_ICONS_DIR, help="Path to icons/ folder")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model identifier (default: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"LLM server base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=900.0, help="LLM request timeout in seconds (default: 900 -- local CPU inference with a reasoning model can take several minutes)")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Cap on completion length; raise this if generation gets cut off (default: 4000)")
    parser.add_argument("--no-think", action="store_true", help="Ask the model to skip most of its reasoning (via chat_template_kwargs enable_thinking=false) -- much faster, but only cuts reasoning down, doesn't eliminate it, and only has an effect on models/backends that support it")
    parser.add_argument("--show-prompt", action="store_true", help="Print the system prompt and exit, without calling the LLM")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated elements as JSON, but don't touch LibreOffice")
    args = parser.parse_args()

    theme = load_theme(args.theme)
    system_prompt = build_system_prompt(theme, args.icons_dir)

    if args.show_prompt:
        print(system_prompt)
        return

    with open(args.instructions_file, "r", encoding="utf-8") as f:
        instructions = f.read().strip()
    if not instructions:
        parser.error(f"{args.instructions_file} is empty")

    print(f"Asking {args.model} to design the slide (this can take several minutes on local CPU inference)...")
    start = time.monotonic()
    try:
        elements, raw = generate_elements(
            system_prompt,
            instructions,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            enable_thinking=False if args.no_think else None,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    problems = validate_elements(elements)
    if problems:
        print("ERROR: the LLM's element list has problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n--- elements as parsed ---", file=sys.stderr)
        print(json.dumps(elements, indent=2), file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"Got {len(elements)} valid element(s) in {elapsed:.1f}s.")
    if args.dry_run:
        print(json.dumps(elements, indent=2))
        return

    ctx, desktop = connect()
    doc, page = create_or_append_slide(desktop, args.deck, elements, theme=theme)
    print(f"Slide added. Saved to {args.deck} ({doc.DrawPages.Count} slide(s) total).")


if __name__ == "__main__":
    main()
