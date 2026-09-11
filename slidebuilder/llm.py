"""
Talks to a local LLM served over an OpenAI-compatible chat completions API
(LM Studio's built-in server: `lms server start`, listening on
http://localhost:1234/v1 by default) and turns its response into a
validated list of slidebuilder element dicts.

Uses only the standard library (urllib), not `requests` -- deliberately, so
this works from whatever Python interpreter can `import uno` (see
connection.py) without needing to get a third-party package installed into
it too. That matters most on macOS, where LibreOffice's bundled
interpreter (unlike Fedora's system Python, which is what this repo was
built against) has no pip/site-packages of its own to install into.
"""

import json
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen/qwen3.5-9b"

_VALID_TYPES = {"rectangle", "oval", "line", "text", "table", "image"}
_REQUIRED_FIELDS = {
    "rectangle": {"x", "y", "width", "height"},
    "oval": {"x", "y", "width", "height"},
    "text": {"x", "y", "width", "height", "text"},
    "table": {"x", "y", "width", "height", "rows"},
    "image": {"x", "y", "width", "height"},  # plus one of icon/path, checked separately
    "line": {"x1", "y1", "x2", "y2"},
}


def call_local_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = 0.2,
    timeout: float = 300.0,
    max_tokens: int | None = 4000,
    enable_thinking: bool | None = None,
) -> str:
    """Send one chat completion request, return the assistant's raw text.

    Some local models (reasoning-capable ones especially, e.g. Qwen3-style)
    spend a large, hard-to-predict number of tokens on chain-of-thought
    before the actual answer -- max_tokens bounds that so a request can't
    run away; if generation gets cut off before finishing, this raises a
    clear error rather than returning truncated/unparseable JSON silently
    (that reasoning, when present, is a separate `reasoning_content` field
    on OpenAI-compatible responses -- not part of the returned text here).

    enable_thinking=False asks the backend (via the OpenAI-compatible
    "chat_template_kwargs" field llama.cpp-based servers, including LM
    Studio, forward straight into the model's own chat template) to skip
    most of that reasoning -- NOT a guaranteed zero, confirmed live: a
    trivial request went from ~1200 reasoning tokens/several minutes down
    to ~50 reasoning tokens/a few seconds with this set, but a short
    reasoning_content still came back. Leave as None (the default) to not
    send the field at all, for a model/backend that doesn't support it.
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
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise ConnectionError(
            f"Local LLM server at {base_url} returned HTTP {e.code}: {e.read()[:500]!r}\n"
            f"Is it running? Start it with: lms server start, and load a model with: lms load <name>"
        ) from e
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Could not reach local LLM server at {base_url}: {e.reason}\n"
            f"Is it running? Start it with: lms server start, and load a model with: lms load <name>"
        ) from e

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


def validate_elements(elements: list) -> list[str]:
    """Sanity-check a list of element dicts against the schema. Returns a
    list of human-readable problem descriptions (empty if none found) --
    doesn't raise, so callers can decide whether to proceed, retry, or
    surface the problems to the user.
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

        if el_type == "image" and "icon" not in el and "path" not in el:
            problems.append(f"{tag} (type='image'): needs either 'icon' or 'path'")

        if el_type == "table":
            rows = el.get("rows")
            if rows is not None and (not isinstance(rows, list) or not rows or not isinstance(rows[0], list)):
                problems.append(f"{tag} (type='table'): 'rows' must be a non-empty list of lists")

        for num_field in ("x", "y", "width", "height", "x1", "y1", "x2", "y2"):
            if num_field in el and not isinstance(el[num_field], (int, float)):
                problems.append(f"{tag}: field {num_field!r} must be a number, got {el[num_field]!r}")

    return problems


def generate_elements(
    system_prompt: str,
    instructions: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
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
    raw = call_local_llm(
        system_prompt, instructions, model=model, base_url=base_url,
        temperature=temperature, timeout=timeout, max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )
    obj = extract_json_object(raw)
    if "elements" not in obj:
        raise ValueError(f"LLM response JSON has no 'elements' key: {obj!r}\n--- raw output ---\n{raw}")
    return obj["elements"], raw
