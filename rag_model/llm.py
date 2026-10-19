"""Apertus API access: settings (URL, key, models per role) and an OpenAI-compatible Haystack generator.

Settings live in data/settings.json (never committed, never sent to the browser).
Environment variables override them: APERTUS_BASE_URL, APERTUS_API_KEY, APERTUS_MODEL_QUERIES, APERTUS_MODEL_BRIEF,
APERTUS_MODEL_AGENT.
"""
import json
import os
import re
from pathlib import Path

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "data" / "settings.json"
ROLES = ("agent",)   # the chat agent; the CLI pipeline in rag_model/brief.py uses the same model unless
                     # model_queries / model_brief are set in data/settings.json


def load_settings() -> dict:
    s = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
    env = {"base_url": "APERTUS_BASE_URL", "api_key": "APERTUS_API_KEY",
           "model_queries": "APERTUS_MODEL_QUERIES", "model_brief": "APERTUS_MODEL_BRIEF",
           "model_agent": "APERTUS_MODEL_AGENT"}
    for key, var in env.items():
        if os.environ.get(var):
            s[key] = os.environ[var]
    return s


def save_settings(update: dict) -> dict:
    s = load_settings()
    s.update({k: v for k, v in update.items() if v not in (None, "")})
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))
    SETTINGS_FILE.chmod(0o600)
    return s


def public_settings() -> dict:
    """What the UI may see: everything except the key itself."""
    s = load_settings()
    key = s.pop("api_key", "")
    return {**s, "key_set": bool(key), "key_last4": key[-4:] if key else ""}


def generator(role: str, llm_cfg: dict, schema: dict | None = None, tools: list | None = None,
              on_chunk=None) -> OpenAIChatGenerator:
    """schema: JSON schema of the expected answer; used when the response format setting is json_schema.
    tools: Haystack tools the model may call; the answer is then free text or tool calls, no response format.
    on_chunk: called for every streamed chunk; raising there stops the answer (used for the stop button)."""
    s = load_settings()
    model = s.get(f"model_{role}") or s.get("model_agent")
    missing = [k for k, v in (("base_url", s.get("base_url")), ("api_key", s.get("api_key")), ("model_agent", model)) if not v]
    if missing:
        raise RuntimeError(f"Apertus API not configured, missing: {', '.join(missing)} "
                           f"(set them in the UI settings or as APERTUS_* environment variables)")
    kwargs = {"temperature": llm_cfg.get("temperature", 0)}
    if llm_cfg.get("max_tokens"):
        kwargs["max_tokens"] = llm_cfg["max_tokens"]
    fmt = llm_cfg.get("response_format")
    if tools:
        pass   # tool_choice "auto": with "required" Apertus can no longer plan in text and repeats its calls
    elif fmt == "json_schema" and schema:
        kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": f"{role}_answer", "schema": schema}}
    elif fmt in ("json_object", "json_schema"):
        kwargs["response_format"] = {"type": "json_object"}
    # Streaming keeps data flowing while the model writes, so gateways with short timeouts do not cut long answers.
    stream = (on_chunk or (lambda chunk: None)) if llm_cfg.get("stream", True) else None
    return OpenAIChatGenerator(api_key=Secret.from_token(s["api_key"]), model=model,
                               api_base_url=s["base_url"], generation_kwargs=kwargs, streaming_callback=stream, tools=tools,
                               timeout=llm_cfg.get("timeout", 300), max_retries=llm_cfg.get("max_retries", 2))


def parse_json(text: str, list_key: str = "items") -> dict:
    """Read the JSON from a model answer (tolerates code fences and text around it).

    A bare list is accepted too and returned as {list_key: [...]}.
    """
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON in answer")
    start = min(starts)
    end = text.rfind("}" if text[start] == "{" else "]")
    data = json.loads(text[start:end + 1])
    return {list_key: data} if isinstance(data, list) else data
