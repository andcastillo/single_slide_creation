"""
Talks to an LLM served over an OpenAI-compatible chat completions API and
turns its response into a validated list of slidebuilder element dicts.

Works against any such API, local or cloud -- LM Studio's built-in server
by default (`lms server start`, http://localhost:1234/v1, no api_key
needed), but equally a cloud provider's OpenAI-compatible endpoint (e.g.
Gemini's: https://generativelanguage.googleapis.com/v1beta/openai, with an
api_key) just by passing different base_url/model/api_key. See README.md's
"Using a cloud API instead" section.

Uses only the standard library (urllib), not `requests` -- deliberately, so
this works from whatever Python interpreter can `import uno` (see
connection.py) without needing to get a third-party package installed into
it too. That matters most on macOS, where LibreOffice's bundled
interpreter (unlike Fedora's system Python, which is what this repo was
built against) has no pip/site-packages of its own to install into.
"""

import json
import os
import re
import urllib.error
import urllib.request

from .elements import _VALID_SHAPE_PRESETS
from .icons import resolve_icon

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen/qwen3.5-9b"

_VALID_TYPES = {"rectangle", "oval", "shape", "line", "text", "table", "image"}
_REQUIRED_FIELDS = {
    "rectangle": {"x", "y", "width", "height"},
    "oval": {"x", "y", "width", "height"},
    "shape": {"x", "y", "width", "height", "preset"},
    "text": {"x", "y", "width", "height", "text"},
    "table": {"x", "y", "width", "height", "rows"},
    "image": {"x", "y", "width", "height"},  # plus one of icon/path, checked separately
    "line": {"x1", "y1", "x2", "y2"},
}
_VALID_ALIGN = {"left", "center", "right"}
_VALID_VALIGN = {"top", "middle", "bottom"}


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
    temperature: float = 0.2,
    timeout: float = 300.0,
    max_tokens: int | None = 4000,
    enable_thinking: bool | None = None,
) -> str:
    """Send one chat completion request, return the assistant's raw text.

    api_key, when given, is sent as "Authorization: Bearer <api_key>" --
    needed for a cloud provider (e.g. Gemini), not for a local server like
    LM Studio, which doesn't check it.

    Some (especially local, reasoning-capable) models spend a large,
    hard-to-predict number of tokens on chain-of-thought before the actual
    answer -- max_tokens bounds that so a request can't run away; if
    generation gets cut off before finishing, this raises a clear error
    rather than returning truncated/unparseable JSON silently (that
    reasoning, when present, is a separate `reasoning_content` field on
    OpenAI-compatible responses -- not part of the returned text here).

    enable_thinking=False asks the backend (via the OpenAI-compatible
    "chat_template_kwargs" field llama.cpp-based servers, including LM
    Studio, forward straight into the model's own chat template) to skip
    most of that reasoning -- confirmed live, this is a soft hint, not a
    reliable/complete fix: on a trivial request it cut reasoning from
    ~1200 tokens to ~50, but on a real, non-trivial prompt it barely
    changed runtime at all -- disabling thinking in the backend's own
    settings (e.g. LM Studio's per-model "Enable thinking" toggle) is what
    actually mattered there (~3.4x faster, confirmed, same output
    quality). This is also Qwen3-chat-template-specific -- leave as None
    (the default, field not sent at all) for a backend/model that doesn't
    use that template, e.g. Gemini.
    """
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        **({"max_tokens": max_tokens} if max_tokens else {}),
        **({"chat_template_kwargs": {"enable_thinking": enable_thinking}} if enable_thinking is not None else {}),
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )
    hint = (
        "Is it running? Start it with: lms server start, and load a model with: lms load <name>"
        if not api_key
        else "Check --base-url, --model, and --api-key."
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise ConnectionError(
            f"LLM server at {base_url} returned HTTP {e.code}: {e.read()[:500]!r}\n{hint}"
        ) from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not reach LLM server at {base_url}: {e.reason}\n{hint}") from e

    data = json.loads(body)
    try:
        choice = data["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Unexpected response shape from LLM server: {data!r}") from e

    if choice.get("finish_reason") == "length":
        raise ValueError(
            "The model hit max_tokens before finishing its response (likely still "
            "'thinking' when cut off) -- pass a larger --max-tokens and try again.\n"
            f"--- partial output ---\n{content}"
        )
    if not content.strip():
        raise ValueError(f"LLM returned an empty response. Full response: {data!r}")
    return content


def extract_json_object(text: str) -> dict:
    """Pull a JSON object out of raw LLM output -- stripping markdown code
    fences and any stray text before/after -- and parse it. Raises
    ValueError (with the raw text attached) if nothing parseable is found.
    """
    stripped = text.strip()
    # Reasoning-capable local models (e.g. Qwen3-style, DeepSeek-R1-style)
    # commonly prepend a <think>...</think> chain-of-thought block before
    # the actual answer, regardless of instructions -- drop it if present.
    stripped = re.sub(r"^\s*<think>.*?</think>\s*", "", stripped, flags=re.DOTALL)
    # Strip a ```json ... ``` or ``` ... ``` fence if the whole response is one.
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*)\n?```$", stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} span found anywhere in the text -- a
    # small local model will sometimes add a stray sentence despite
    # instructions not to.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = stripped[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Could not parse JSON from LLM output. Error: {e}\n--- raw output ---\n{text}"
            ) from e

    raise ValueError(f"No JSON object found in LLM output.\n--- raw output ---\n{text}")


def validate_elements(elements: list, icons_dir: str | None = None) -> list[str]:
    """Sanity-check a list of element dicts against the schema, INCLUDING
    every condition slidebuilder/elements.py's shape-building functions
    would otherwise only discover by raising mid-way through actually
    building the slide -- e.g. a table whose rows don't all have the same
    number of cells. Catching that here instead means a bad response
    fails before anything touches LibreOffice, rather than leaving a
    slide half-built in the live document (confirmed happening exactly
    that way once, from a table with uneven row lengths this function
    didn't yet check for -- this function was written to close that gap).

    Returns a list of human-readable problem descriptions (empty if none
    found) -- doesn't raise, so callers can decide whether to proceed,
    retry, or surface the problems to the user.

    icons_dir, if given, also checks that every "icon" name an image
    element specifies actually resolves to a file there (catching a
    hallucinated icon name); omit to skip that one check.
    """
    problems = []
    if not isinstance(elements, list):
        return [f"'elements' must be a JSON array, got {type(elements).__name__}"]

    for i, el in enumerate(elements):
        tag = f"element[{i}]"
        if not isinstance(el, dict):
            problems.append(f"{tag}: expected an object, got {type(el).__name__}")
            continue

        el_type = el.get("type")
        if el_type not in _VALID_TYPES:
            problems.append(f"{tag}: unknown or missing type {el_type!r} (expected one of {sorted(_VALID_TYPES)})")
            continue

        missing = _REQUIRED_FIELDS[el_type] - el.keys()
        if missing:
            problems.append(f"{tag} (type={el_type!r}): missing required field(s) {sorted(missing)}")

        if "align" in el and el["align"] not in _VALID_ALIGN:
            problems.append(f"{tag}: 'align' must be one of {sorted(_VALID_ALIGN)}, got {el['align']!r}")
        if "valign" in el and el["valign"] not in _VALID_VALIGN:
            problems.append(f"{tag}: 'valign' must be one of {sorted(_VALID_VALIGN)}, got {el['valign']!r}")

        if el_type == "shape" and el.get("preset") not in _VALID_SHAPE_PRESETS:
            problems.append(
                f"{tag} (type='shape'): 'preset' must be one of "
                f"{sorted(_VALID_SHAPE_PRESETS)}, got {el.get('preset')!r}"
            )

        if el_type == "image":
            icon, path = el.get("icon"), el.get("path")
            if not icon and not path:
                problems.append(f"{tag} (type='image'): needs either 'icon' or 'path'")
            elif icon and icons_dir:
                try:
                    resolve_icon(icon, icons_dir)
                except FileNotFoundError as e:
                    problems.append(f"{tag} (type='image'): {e}")
            elif path and not os.path.isfile(path):
                problems.append(f"{tag} (type='image'): path {path!r} does not exist")

        if el_type == "table":
            rows = el.get("rows")
            if rows is not None:
                if not isinstance(rows, list) or not rows or not isinstance(rows[0], list):
                    problems.append(f"{tag} (type='table'): 'rows' must be a non-empty list of lists")
                else:
                    n_cols = len(rows[0])
                    if any(not isinstance(r, list) or len(r) != n_cols for r in rows):
                        problems.append(
                            f"{tag} (type='table'): every row in 'rows' must have the same "
                            f"number of cells ({n_cols}, from the first row)"
                        )
                    for size_field, expected_len, unit in (
                        ("col_widths", n_cols, "column"),
                        ("row_heights", len(rows), "row"),
                    ):
                        sizes = el.get(size_field)
                        if sizes is not None and (not isinstance(sizes, list) or len(sizes) != expected_len):
                            problems.append(
                                f"{tag} (type='table'): '{size_field}' must have exactly "
                                f"{expected_len} entries, one per {unit}"
                            )

                    # A model that's pattern-matched on markdown tables will
                    # sometimes cram "a | b | c" into a single cell instead
                    # of splitting it into separate list entries --
                    # syntactically valid (a 1-column table), but not what
                    # was meant. Confirmed happening in practice (Gemini
                    # Flash Lite). Require 2+ pipes (3+ segments), not just
                    # one: a single stray "|" is plausible in real content
                    # (a false positive confirmed directly, e.g. "Bob |
                    # Smith Jr."), but three-plus crammed-together values
                    # essentially never is.
                    if n_cols == 1:
                        for r_idx, r in enumerate(rows):
                            cell = r[0] if isinstance(r, list) and r else None
                            if isinstance(cell, str) and len([s for s in cell.split("|") if s.strip()]) >= 3:
                                problems.append(
                                    f"{tag} (type='table'): row {r_idx} looks like a "
                                    f"pipe-separated markdown row crammed into a single cell "
                                    f"({cell!r}) instead of separate cells in the list -- "
                                    f"each column's value must be its own string in the row's list"
                                )
                                break

        for num_field in ("x", "y", "width", "height", "x1", "y1", "x2", "y2"):
            if num_field in el and not isinstance(el[num_field], (int, float)):
                problems.append(f"{tag}: field {num_field!r} must be a number, got {el[num_field]!r}")

    return problems


def clamp_to_canvas(
    elements: list,
    slide_width_in: float,
    slide_height_in: float,
) -> tuple[list, list[str]]:
    """Reposition (and, only as a last resort, resize) any element that
    extends past the slide's bounds so it lands back on-canvas.

    The system prompt already tells the model the canvas size and asks it
    to respect it, but confirmed in practice, it sometimes doesn't --
    reported directly: elements occasionally end up placed partly or
    fully outside the slide. Preference stated for that case: move things
    back in rather than shrink/rearrange to avoid overlap, so that's what
    this does -- an element keeps its width/height and just gets
    repositioned to fit, UNLESS it's larger than the canvas itself in
    that dimension (impossible to fit by repositioning alone), in which
    case only that dimension is shrunk to the canvas size, as a fallback.

    Returns (adjusted_elements, notes) -- a new list (the input isn't
    mutated) and a human-readable description of every change made, empty
    if nothing needed adjusting.
    """
    adjusted = []
    notes = []
    for i, el in enumerate(elements):
        el = dict(el)
        tag = f"element[{i}]"

        if el.get("type") == "line":
            for x_key in ("x1", "x2"):
                if isinstance(el.get(x_key), (int, float)):
                    clamped = min(max(el[x_key], 0.0), slide_width_in)
                    if clamped != el[x_key]:
                        notes.append(f"{tag} (line): {x_key} {el[x_key]} -> {clamped}")
                        el[x_key] = clamped
            for y_key in ("y1", "y2"):
                if isinstance(el.get(y_key), (int, float)):
                    clamped = min(max(el[y_key], 0.0), slide_height_in)
                    if clamped != el[y_key]:
                        notes.append(f"{tag} (line): {y_key} {el[y_key]} -> {clamped}")
                        el[y_key] = clamped

        elif all(isinstance(el.get(k), (int, float)) for k in ("x", "y", "width", "height")):
            x, y, w, h = el["x"], el["y"], el["width"], el["height"]
            orig = (x, y, w, h)
            w = min(w, slide_width_in)
            h = min(h, slide_height_in)
            x = min(max(x, 0.0), max(slide_width_in - w, 0.0))
            y = min(max(y, 0.0), max(slide_height_in - h, 0.0))
            if (x, y, w, h) != orig:
                notes.append(
                    f"{tag} (type={el.get('type')!r}): adjusted to fit the canvas "
                    f"(x,y,width,height {orig} -> {(x, y, w, h)})"
                )
                el["x"], el["y"], el["width"], el["height"] = x, y, w, h

        adjusted.append(el)
    return adjusted, notes


def generate_elements(
    system_prompt: str,
    instructions: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str | None = None,
    temperature: float = 0.2,
    timeout: float = 300.0,
    max_tokens: int | None = 4000,
    enable_thinking: bool | None = None,
) -> tuple[list, str]:
    """Call the LLM and return (elements, raw_response_text). Raises
    ValueError if the response can't be parsed into a JSON object with an
    'elements' array. Does NOT raise on schema problems (missing fields
    etc.) -- check validate_elements(elements) yourself; this just gets you
    parsed data to check.
    """
    raw = call_llm(
        system_prompt, instructions, model=model, base_url=base_url, api_key=api_key,
        temperature=temperature, timeout=timeout, max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )
    obj = extract_json_object(raw)
    if "elements" not in obj:
        raise ValueError(f"LLM response JSON has no 'elements' key: {obj!r}\n--- raw output ---\n{raw}")
    return obj["elements"], raw
