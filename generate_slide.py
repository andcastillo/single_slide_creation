#!/usr/bin/env /usr/bin/python3
"""
Turn a natural-language slide description into a slide, via an LLM.

    1. Read a plain-text instructions file (a description of ONE slide).
    2. Build the system prompt from theme.json + icons/ (slidebuilder.prompt),
       and send it + the instructions to an LLM served over an OpenAI-
       compatible API -- a local one (LM Studio, the default) or a cloud
       one (e.g. Gemini, with --api-key) -- to get back slidebuilder
       element definitions.
    3. Validate those elements, then add them as a slide in the LibreOffice
       session already running (via the UNO socket) -- creating the deck if
       it doesn't exist yet, or appending if it does.

Prerequisites:
    - LibreOffice running and listening on the UNO socket (see README.md).
    - An LLM reachable at --base-url. By default that's LM Studio's local
      server with a model loaded:
          lms server start
          lms load qwen/qwen3.5-9b --context-length 16384
      For a cloud API instead, see README.md's "Using a cloud API instead".

Usage:
    /usr/bin/python3 generate_slide.py instructions.txt
    /usr/bin/python3 generate_slide.py instructions.txt --deck examples/my_deck.pptx
    /usr/bin/python3 generate_slide.py instructions.txt --model qwen/qwen3.5-9b --show-prompt
    /usr/bin/python3 generate_slide.py instructions.txt \\
        --base-url https://generativelanguage.googleapis.com/v1beta/openai \\
        --model gemini-2.0-flash --api-key "$GEMINI_API_KEY"
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slidebuilder import connect, create_or_append_slide, load_theme
from slidebuilder.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_to_canvas, generate_elements, validate_elements
from slidebuilder.prompt import DEFAULT_SLIDE_HEIGHT_IN, DEFAULT_SLIDE_WIDTH_IN, build_system_prompt

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
    parser.add_argument("--slide-width", type=float, default=DEFAULT_SLIDE_WIDTH_IN, help=f"Slide width in inches, told to the model and used to keep elements on-canvas (default: {DEFAULT_SLIDE_WIDTH_IN})")
    parser.add_argument("--slide-height", type=float, default=DEFAULT_SLIDE_HEIGHT_IN, help=f"Slide height in inches (default: {DEFAULT_SLIDE_HEIGHT_IN})")
    parser.add_argument("--no-clamp", action="store_true", help="Don't reposition/resize elements that end up outside the slide bounds -- by default they're moved (and, only if larger than the canvas itself, shrunk) back on-canvas after generation")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model identifier (default: {DEFAULT_MODEL})")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"LLM server base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY"), help="Bearer token for a cloud provider (e.g. Gemini); not needed for a local server like LM Studio. Falls back to the LLM_API_KEY environment variable -- prefer that over this flag so the key doesn't end up in shell history/process listings.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=900.0, help="LLM request timeout in seconds (default: 900 -- local CPU inference with a reasoning model can take several minutes)")
    parser.add_argument("--max-tokens", type=int, default=4000, help="Cap on completion length; raise this if generation gets cut off (default: 4000)")
    parser.add_argument("--no-think", action="store_true", help="Ask the model to skip most of its reasoning (via chat_template_kwargs enable_thinking=false) -- much faster, but only cuts reasoning down, doesn't eliminate it, and only has an effect on models/backends that support it")
    parser.add_argument("--show-prompt", action="store_true", help="Print the system prompt and exit, without calling the LLM")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated elements as JSON, but don't touch LibreOffice")
    args = parser.parse_args()

    theme = load_theme(args.theme)
    system_prompt = build_system_prompt(theme, args.icons_dir, args.slide_width, args.slide_height)

    if args.show_prompt:
        print(system_prompt)
        return

    with open(args.instructions_file, "r", encoding="utf-8") as f:
        instructions = f.read().strip()
    if not instructions:
        parser.error(f"{args.instructions_file} is empty")

    print(f"Asking {args.model} at {args.base_url} to design the slide...")
    start = time.monotonic()
    try:
        elements, raw = generate_elements(
            system_prompt,
            instructions,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            temperature=args.temperature,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            enable_thinking=False if args.no_think else None,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    problems = validate_elements(elements, icons_dir=args.icons_dir)
    if problems:
        print("ERROR: the LLM's element list has problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n--- elements as parsed ---", file=sys.stderr)
        print(json.dumps(elements, indent=2), file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"Got {len(elements)} valid element(s) in {elapsed:.1f}s.")

    if not args.no_clamp:
        elements, clamp_notes = clamp_to_canvas(elements, args.slide_width, args.slide_height)
        if clamp_notes:
            print(f"Adjusted {len(clamp_notes)} element(s) that extended past the slide bounds:")
            for n in clamp_notes:
                print(f"  - {n}")

    if args.dry_run:
        print(json.dumps(elements, indent=2))
        return

    ctx, desktop = connect()
    doc, page = create_or_append_slide(
        desktop, args.deck, elements, theme=theme,
        width_in=args.slide_width, height_in=args.slide_height,
    )
    print(f"Slide added. Saved to {args.deck} ({doc.DrawPages.Count} slide(s) total).")


if __name__ == "__main__":
    main()
