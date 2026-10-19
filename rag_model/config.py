"""Pipeline parameters: defaults from config.yaml, changes from the UI in data/config_overrides.json.

Every parameter the pipeline reads must be listed in SCHEMA, so the settings page can show and edit it.
Code reads the merged values with `load()` at call time, so UI changes apply without a restart.
"""

import copy
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_FILE = ROOT / "config.yaml"
OVERRIDES_FILE = ROOT / "data" / "config_overrides.json"

# group -> (title, description, editable, fields); field: key, label, hint, type, extra
SCHEMA = [
    {
        "section": "queries",
        "title": "Search terms (B2)",
        "applies": "immediately, from the next search",
        "editable": True,
        "fields": [
            {
                "key": "mode",
                "label": "How buzzwords become search queries",
                "type": "select",
                "options": ["apertus", "direct"],
                "option_labels": {
                    "apertus": "Hypothetical passages by Apertus (HyDE)",
                    "direct": "Use buzzwords as is",
                },
                "hint": "HyDE: Apertus writes short passages as a matching website section would read; their embeddings find "
                'similar real pages. Empty buzzwords like "scale-up" are dropped. As is: every buzzword is searched '
                "unchanged, no language model.",
            },
            {
                "key": "passages_per_buzzword",
                "label": "Passages per buzzword",
                "type": "int",
                "min": 1,
                "max": 4,
                "hint": "How many hypothetical passages Apertus writes per buzzword, each from a different angle. "
                "More passages find more kinds of pages but take longer.",
            },
        ],
    },
    {
        "section": "search",
        "title": "Search (B3)",
        "applies": "immediately, from the next search",
        "editable": True,
        "fields": [
            {
                "key": "top_k",
                "label": "Chunks per search term (K)",
                "type": "int",
                "min": 1,
                "max": 1000,
                "hint": "How many of the most similar text chunks the search fetches per search term before grouping them into pages.",
            },
            {
                "key": "top_n",
                "label": "Pages sent to Apertus (N)",
                "type": "int",
                "min": 1,
                "max": 200,
                "hint": "How many pages remain after selection and are sent to Apertus in full.",
            },
            {
                "key": "max_per_site",
                "label": "Max. pages per website",
                "type": "int",
                "min": 1,
                "max": 200,
                "hint": "Keeps large websites from taking all the places (fairness).",
            },
            {
                "key": "min_similarity",
                "label": "Relevance threshold",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.01,
                "hint": "Pages with a lower similarity are not shown. If none remain, the search reports "
                '"nothing reliable found". 0 = off.',
            },
            {
                "key": "weak_similarity",
                "label": "Weak hit below",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.01,
                "hint": "Display only: pages with a lower similarity are marked as weak in the hit list.",
            },
            {
                "key": "variant_similarity",
                "label": "Same page from",
                "type": "float",
                "min": 0.5,
                "max": 1,
                "step": 0.01,
                "hint": "From this similarity on, two pages count as the same page (e.g. German and English version) "
                "and are merged.",
            },
        ],
    },
    {
        "section": "check",
        "title": "Evidence check (B5)",
        "applies": "immediately, from the next compose",
        "editable": True,
        "fields": [
            {
                "key": "evidence_min_ratio",
                "label": "Quote must match (%)",
                "type": "int",
                "min": 50,
                "max": 100,
                "hint": "How exactly Apertus' quote must appear on the cited page, otherwise the item is dropped. "
                "Lower = more items, but invented evidence can slip through.",
            },
            {
                "key": "summary_min_similarity",
                "label": "Summary matches quote from",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.01,
                "hint": 'Below this, an item is flagged with "summary differs from quote".',
            },
        ],
    },
    {
        "section": "llm",
        "title": "Apertus calls",
        "applies": "immediately, from the next call",
        "editable": True,
        "fields": [
            {
                "key": "temperature",
                "label": "Temperature",
                "type": "float",
                "min": 0,
                "max": 2,
                "step": 0.1,
                "hint": "0 = the same request gives the same answer. Higher = more varied, but less reliable.",
            },
            {
                "key": "stream",
                "label": "Stream the answer",
                "type": "bool",
                "hint": "Needed for long answers: without streaming the gateway cuts the request after about a minute.",
            },
            {
                "key": "response_format",
                "label": "API JSON mode",
                "type": "select",
                "options": ["json_schema", "json_object", "none"],
                "option_labels": {
                    "json_schema": "JSON schema (API enforces the structure)",
                    "json_object": "JSON object",
                    "none": "None (read JSON from the text)",
                },
                "hint": "JSON schema: the API forces the answer into the structure defined in the prompt file, so it is always "
                "valid. Use a weaker mode only if the API does not support it.",
            },
            {
                "key": "timeout",
                "label": "Timeout (seconds)",
                "type": "int",
                "min": 10,
                "max": 3600,
                "hint": "The longest the backend waits for the next part of an answer.",
            },
            {
                "key": "max_tokens",
                "label": "Maximum answer length (tokens)",
                "type": "int",
                "min": 500,
                "max": 32000,
                "hint": "A longer answer is cut off. Stops a model that keeps repeating itself; 15 items need about 4000.",
            },
            {
                "key": "max_retries",
                "label": "Retries on errors",
                "type": "int",
                "min": 0,
                "max": 5,
                "hint": "How often a failed call is repeated.",
            },
            {
                "key": "json_attempts",
                "label": "Attempts for valid JSON",
                "type": "int",
                "min": 1,
                "max": 5,
                "hint": "If an answer is not valid JSON, Apertus gets its answer and the error back to fix it, up to this many attempts.",
            },
        ],
    },
    {
        "section": "brief",
        "title": "Result (B4)",
        "applies": "immediately, from the next compose",
        "editable": True,
        "fields": [
            {
                "key": "language",
                "label": "Language of the items",
                "type": "select",
                "options": ["German", "English", "French"],
                "hint": "Language of title, category and summary. Quotes stay in the language of the page.",
            },
            {
                "key": "max_items",
                "label": "Maximum items",
                "type": "int",
                "min": 1,
                "max": 40,
                "hint": "Upper limit of pitch items per answer, enforced through the answer schema. Very long answers "
                "repeat items and are more likely to break the JSON.",
            },
        ],
    },
    {
        "section": "agent",
        "title": "Agent",
        "applies": "immediately, from the next message",
        "editable": True,
        "fields": [
            {
                "key": "max_steps",
                "label": "Maximum steps per message",
                "type": "int",
                "min": 1,
                "max": 50,
                "hint": "Maximum decision/generation steps per message. Each step selects one action. "
                "Stops a loop that does not converge.",
            },
            {
                "key": "rank_candidates",
                "label": "Decision ranking shortlist",
                "type": "int",
                "min": 2,
                "max": 8,
                "hint": "Rank this many retrieved pages with the decision model; remaining pages keep retrieval order.",
            },
        ],
    },
    {
        "section": "prepare",
        "title": "Preparation (A2–A3)",
        "applies": "at the next index rebuild",
        "editable": True,
        "fields": [
            {
                "key": "min_words",
                "label": "Minimum page length (words)",
                "type": "int",
                "min": 0,
                "max": 1000,
                "hint": "Shorter pages are dropped (mostly empty or navigation-only pages).",
            },
            {
                "key": "short_page_chars",
                "label": "Short page up to (characters)",
                "type": "int",
                "min": 200,
                "max": 50000,
                "hint": "Shorter pages stay a single chunk, longer ones are split.",
            },
            {
                "key": "chunk_words",
                "label": "Chunk size (words)",
                "type": "int",
                "min": 50,
                "max": 2000,
                "hint": "Target size of the chunks long pages are split into.",
            },
            {
                "key": "overlap_words",
                "label": "Overlap (words)",
                "type": "int",
                "min": 0,
                "max": 500,
                "hint": "How many words each chunk repeats from the previous one, so no context is lost at the cut.",
            },
            {
                "key": "boilerplate.max_words",
                "label": "Menu line: max. words",
                "type": "int",
                "min": 1,
                "max": 100,
                "hint": "Only lines this short can count as menu or footer.",
            },
            {
                "key": "boilerplate.min_pages",
                "label": "Menu line: on at least N pages",
                "type": "int",
                "min": 2,
                "max": 1000,
                "hint": "A line counts as menu if it appears on at least this many pages of the same website …",
            },
            {
                "key": "boilerplate.share",
                "label": "Menu line: or share",
                "type": "float",
                "min": 0,
                "max": 1,
                "step": 0.05,
                "hint": "… or on this share of a website's pages (for small websites).",
            },
            {
                "key": "boilerplate.cap",
                "label": "Menu line: cap",
                "type": "int",
                "min": 2,
                "max": 10000,
                "hint": "On large websites it is enough if the line appears on this many pages.",
            },
        ],
    },
    {
        "section": "embedding",
        "title": "Embedding model (A4, B3)",
        "applies": "only with re-embedding all chunks",
        "editable": False,
        "fields": [
            {
                "key": "model",
                "label": "Model",
                "type": "str",
                "hint": "Must be the same for indexing and search. Changing it requires re-embedding (GPU machine).",
            },
            {
                "key": "dim",
                "label": "Vector length",
                "type": "int",
                "hint": "Given by the model.",
            },
            {
                "key": "meta_fields_to_embed",
                "label": "Context header",
                "type": "list",
                "hint": "These fields are put in front of every chunk before embedding.",
            },
        ],
    },
]


def _get(d: dict, dotted: str):
    for part in dotted.split("."):
        d = d[part]
    return d


def _set(d: dict, dotted: str, value) -> None:
    *path, last = dotted.split(".")
    for part in path:
        d = d.setdefault(part, {})
    d[last] = value


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = (
            _merge(out[k], v)
            if isinstance(v, dict) and isinstance(out.get(k), dict)
            else v
        )
    return out


def defaults() -> dict:
    return yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8"))


def overrides() -> dict:
    return json.loads(OVERRIDES_FILE.read_text()) if OVERRIDES_FILE.exists() else {}


def load() -> dict:
    return _merge(defaults(), overrides())


def describe() -> list[dict]:
    """Schema with current and default values, for the settings page."""
    cur, dflt = load(), defaults()
    groups = []
    for g in SCHEMA:
        fields = [
            {
                **f,
                "value": _get(cur[g["section"]], f["key"]),
                "default": _get(dflt[g["section"]], f["key"]),
            }
            for f in g["fields"]
        ]
        groups.append({**g, "fields": fields})
    return groups


def _coerce(field: dict, value):
    t = field["type"]
    if t == "int":
        value = int(value)
    elif t == "float":
        value = float(value)
    elif t == "bool":
        value = bool(value)
    elif t == "select" and value not in field["options"]:
        raise ValueError(
            f"{field['label']}: allowed values are {', '.join(field['options'])}"
        )
    if t in ("int", "float"):
        if (
            "min" in field
            and value < field["min"]
            or "max" in field
            and value > field["max"]
        ):
            raise ValueError(
                f"{field['label']}: value must be between {field.get('min')} and {field.get('max')}"
            )
    return value


def update(changes: dict[str, dict]) -> None:
    """changes: {section: {dotted_key: value}}. Values equal to the default are removed from the overrides."""
    groups = {g["section"]: g for g in SCHEMA}
    over, dflt = overrides(), defaults()
    for section, values in changes.items():
        g = groups.get(section)
        if not g or not g["editable"]:
            raise ValueError(f"section {section!r} cannot be changed")
        fields = {f["key"]: f for f in g["fields"]}
        for key, value in values.items():
            if key not in fields:
                raise ValueError(f"unknown parameter {section}.{key}")
            value = _coerce(fields[key], value)
            if value == _get(dflt[section], key):
                _remove(over, section, key)
            else:
                _set(over.setdefault(section, {}), key, value)
    OVERRIDES_FILE.parent.mkdir(exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(over, indent=2, ensure_ascii=False))


def _remove(over: dict, section: str, dotted: str) -> None:
    node, parts = over.get(section, {}), dotted.split(".")
    for part in parts[:-1]:
        node = node.get(part, {})
    node.pop(parts[-1], None)


def reset(section: str | None = None) -> None:
    over = overrides()
    if section:
        over.pop(section, None)
    else:
        over = {}
    OVERRIDES_FILE.write_text(json.dumps(over, indent=2, ensure_ascii=False))
