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
    /usr/bin/python3 generate_slide.py instructions.txt --deck examples/my_deck.pptx --after 2
    /usr/bin/python3 generate_slide.py instructions.txt --model qwen/qwen3.5-9b --show-prompt
    /usr/bin/python3 generate_slide.py instructions.txt \\
        --base-url https://generativelanguage.googleapis.com/v1beta/openai \\
        --model gemini-2.0-flash --api-key "$GEMINI_API_KEY"
    /usr/bin/python3 generate_slide.py instructions.txt --use-cache

Every real LLM call's parsed element list is cached to a .json file next to
the instructions file (instructions.txt -> instructions.json). Edit that
file by hand and re-run with --use-cache to replay it without calling the
LLM again -- useful for debugging generation issues or hand-tweaking a
slide's elements directly.

The instructions file may also carry sections that are applied to the
slide verbatim and never sent to the LLM (see slidebuilder/sections.py):

    === SPEAKER NOTES ===
    ...becomes the slide's speaker notes

    === COMMENT ===
    ...becomes a review comment on the slide (e.g. animations to build)

Absent or empty sections add nothing. --no-notes / --no-comments ignore
them for one run (e.g. to build a clean copy to share). Since sections
never touch the LLM, edit them and re-run with --use-cache to apply the
change without another LLM call.

--llm-notes / --llm-comments instead ask the LLM to write the speaker
notes / an animation-plan comment itself, in the same call that designs
the slide -- but only for a section the instructions file doesn't have:
a section you wrote always wins, and a present-but-empty one means "none
for this slide". Meant for a larger model; without these flags the
prompt is unchanged, so a small model only handles the graphics. What
the LLM wrote is cached alongside the elements and replayed by
--use-cache (with the same flags).
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slidebuilder import add_slide, connect, get_page_size_in, load_theme, open_deck, save_deck
from slidebuilder.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_to_canvas, generate_response, text_field, validate_elements
from slidebuilder.prompt import DEFAULT_SLIDE_HEIGHT_IN, DEFAULT_SLIDE_WIDTH_IN, build_system_prompt
from slidebuilder.sections import COMMENT, SPEAKER_NOTES, parse_instructions

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_THEME_PATH = os.path.join(REPO_ROOT, "theme.json")
DEFAULT_ICONS_DIR = os.path.join(REPO_ROOT, "icons")
DEFAULT_DECK_PATH = os.path.join(REPO_ROOT, "examples", "generated_deck.pptx")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instructions_file", help="Path to a text file describing the slide in natural language")
    parser.add_argument("--deck", default=DEFAULT_DECK_PATH, help=f"Output .pptx path (default: {DEFAULT_DECK_PATH})")
    parser.add_argument("--after", type=int, default=None, help="1-based slide number to insert the new slide after (e.g. 2 inserts it as slide 3), for an existing deck. Default: append at the end. Use 0 to insert it as the new first slide.")
    parser.add_argument("--theme", default=DEFAULT_THEME_PATH, help="Path to theme JSON (default: theme.json)")
    parser.add_argument("--icons-dir", default=DEFAULT_ICONS_DIR, help="Path to icons/ folder")
    parser.add_argument("--slide-width", type=float, default=DEFAULT_SLIDE_WIDTH_IN, help=f"Slide width in inches, told to the model and used to keep elements on-canvas (default: {DEFAULT_SLIDE_WIDTH_IN}). Only actually used for a brand-new deck, or for --dry-run/--show-prompt -- appending to an existing deck auto-detects its real size instead and this is ignored")
    parser.add_argument("--slide-height", type=float, default=DEFAULT_SLIDE_HEIGHT_IN, help=f"Slide height in inches (default: {DEFAULT_SLIDE_HEIGHT_IN}). Same caveat as --slide-width")
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
    parser.add_argument("--use-cache", action="store_true", help="Skip the LLM call and load the element list from the cache file instead (see below) -- lets you re-run against a hand-edited or previously generated element list. Errors out if that file doesn't exist yet.")
    parser.add_argument("--no-notes", action="store_true", help="Ignore the instructions file's '=== SPEAKER NOTES ===' section for this run (the slide gets no speaker notes)")
    parser.add_argument("--no-comments", action="store_true", help="Ignore the instructions file's '=== COMMENT ===' section for this run (the slide gets no comment)")
    parser.add_argument("--comment-author", default="slidebuilder", help="Author name shown on the slide comment (default: slidebuilder)")
    parser.add_argument("--llm-notes", action="store_true", help="Ask the LLM to write the speaker notes, if the instructions file has no '=== SPEAKER NOTES ===' section (a section you wrote always wins; an empty one means no notes)")
    parser.add_argument("--llm-comments", action="store_true", help="Ask the LLM to write an animation-plan comment, if the instructions file has no '=== COMMENT ===' section (same rules as --llm-notes)")
    args = parser.parse_args()

    # Every real LLM call's parsed element list is written here (same path
    # as the instructions file, with a .json extension) so it can be
    # inspected, hand-edited, and replayed via --use-cache without paying
    # for another (slow, and for a cloud model, billed) LLM call. It's a
    # bare JSON array of elements -- or, when the LLM was also asked for
    # notes/comment, an object {"elements": [...], "notes": ..., "comment": ...}.
    cache_path = os.path.splitext(args.instructions_file)[0] + ".json"

    theme = load_theme(args.theme)

    # --show-prompt and --dry-run stay side-effect-free (no LibreOffice
    # connection at all -- opening/creating a deck just to preview would
    # pop up a visible window even though nothing gets saved) -- they use
    # --slide-width/--slide-height (CLI or default) directly, which is
    # only an approximation of an *existing* target deck's real size.
    # Only the real build below actually opens that deck and queries its
    # true page size instead, via get_page_size_in() -- since that's the
    # one case correctness actually depends on it.
    slide_width_in, slide_height_in = args.slide_width, args.slide_height

    with open(args.instructions_file, "r", encoding="utf-8") as f:
        try:
            sections = parse_instructions(f.read())
        except ValueError as e:
            parser.error(f"{args.instructions_file}: {e}")
    # Only the body is the slide description the LLM designs from; the
    # other sections are applied to the slide verbatim, below.
    instructions = sections["body"]
    if not instructions:
        parser.error(f"{args.instructions_file} has no slide description (before any '=== ... ===' section)")
    notes = None if args.no_notes else sections[SPEAKER_NOTES]
    comment = None if args.no_comments else sections[COMMENT]

    # The LLM is only asked for notes/comment the file doesn't already
    # settle: a written section wins, and an empty one means "none".
    want_notes = args.llm_notes and not args.no_notes and notes is None
    want_comment = args.llm_comments and not args.no_comments and comment is None

    def prompt_for(width_in, height_in):
        return build_system_prompt(
            theme, args.icons_dir, width_in, height_in,
            want_notes=want_notes, want_comment=want_comment,
        )

    system_prompt = prompt_for(slide_width_in, slide_height_in)
    if args.show_prompt:
        print(system_prompt)
        return

    for flag, wanted, label in (("--llm-notes", args.llm_notes, SPEAKER_NOTES), ("--llm-comments", args.llm_comments, COMMENT)):
        if wanted and sections[label] is not None:
            kind = "a" if sections[label] else "an empty"
            meaning = "using it" if sections[label] else "meaning none for this slide"
            print(f"{flag}: the instructions file has {kind} '=== {label} ===' section -- {meaning}, not asking the LLM.")

    doc, is_new = None, None
    if not args.dry_run:
        # Connect and open/create the target deck FIRST, before the (slow)
        # LLM call -- both to fail fast if LibreOffice isn't running rather
        # than after minutes of waiting, and because we need the deck open
        # to know its real page size.
        ctx, desktop = connect()
        doc, is_new = open_deck(desktop, args.deck, width_in=slide_width_in, height_in=slide_height_in)
        slide_width_in, slide_height_in = get_page_size_in(doc)
        if not is_new:
            print(
                f"Appending to an existing deck -- using its actual page size "
                f"({slide_width_in:.2f} x {slide_height_in:.2f}in), not --slide-width/--slide-height."
            )
            system_prompt = prompt_for(slide_width_in, slide_height_in)

    if args.use_cache:
        if not os.path.isfile(cache_path):
            parser.error(f"--use-cache given but {cache_path} doesn't exist yet -- run once without it first")
        print(f"Using cached element list from {cache_path} (skipping the LLM).")
        with open(cache_path, "r", encoding="utf-8") as f:
            response = json.load(f)
        # Older caches (and any written without --llm-notes/--llm-comments)
        # are a bare element list.
        if isinstance(response, list):
            response = {"elements": response}
        elements = response.get("elements")
    else:
        print(f"Asking {args.model} at {args.base_url} to design the slide...")
        start = time.monotonic()
        try:
            response, raw = generate_response(
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
        elapsed = time.monotonic() - start
        elements = response["elements"]
        extra_keys = [k for k, want in (("notes", want_notes), ("comment", want_comment)) if want and k in response]
        cached = {"elements": elements, **{k: response[k] for k in extra_keys}} if extra_keys else elements
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f, indent=2, ensure_ascii=False)
        print(f"Cached the LLM's response to {cache_path}.")

    # LLM-written notes/comment: fresh from this call, or replayed from the
    # cache. Missing or unusable ones are a warning, not an error -- the
    # slide itself is still fine without them.
    llm_written = set()
    for key, wanted in (("notes", want_notes), ("comment", want_comment)):
        if not wanted:
            continue
        text, problem = text_field(response, key)
        if problem:
            hint = " (re-run without --use-cache to generate it)" if args.use_cache else ""
            print(f"WARNING: {problem}{hint}; the slide gets no {key}.", file=sys.stderr)
            continue
        llm_written.add(key)
        if key == "notes":
            notes = text
        else:
            comment = text

    problems = validate_elements(elements, icons_dir=args.icons_dir)
    if problems:
        print("ERROR: the LLM's element list has problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n--- elements as parsed ---", file=sys.stderr)
        print(json.dumps(elements, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.use_cache:
        print(f"Got {len(elements)} valid element(s) from cache.")
    else:
        print(f"Got {len(elements)} valid element(s) in {elapsed:.1f}s.")

    if not args.no_clamp:
        elements, clamp_notes = clamp_to_canvas(elements, slide_width_in, slide_height_in)
        if clamp_notes:
            print(f"Adjusted {len(clamp_notes)} element(s) that extended past the slide bounds:")
            for n in clamp_notes:
                print(f"  - {n}")

    if args.dry_run:
        print(json.dumps(elements, indent=2))
        if notes:
            print(f"\n--- speaker notes ---\n{notes}")
        if comment:
            print(f"\n--- comment ---\n{comment}")
        return

    index = None
    if args.after is not None:
        if is_new:
            parser.error("--after doesn't apply to a brand-new deck (it only has the one slide being created)")
        if not (0 <= args.after <= doc.DrawPages.Count):
            parser.error(f"--after {args.after} is out of range for a deck with {doc.DrawPages.Count} slide(s)")
        index = args.after

    add_slide(
        doc, elements, is_new=is_new, index=index, theme=theme,
        notes=notes, comment=comment, comment_author=args.comment_author,
    )
    save_deck(doc, args.deck)
    extras = [
        label + (" (written by the LLM)" if key in llm_written else "")
        for key, label, text in (("notes", "speaker notes", notes), ("comment", "a comment", comment))
        if text
    ]
    with_extras = f" with {' and '.join(extras)}" if extras else ""
    print(f"Slide added{with_extras}. Saved to {args.deck} ({doc.DrawPages.Count} slide(s) total).")


if __name__ == "__main__":
    main()
