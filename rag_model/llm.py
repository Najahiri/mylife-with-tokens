"""Apertus API access: settings (URL, key, models per role) and an OpenAI-compatible Haystack generator.

Settings live in data/settings.json (never committed, never sent to the browser).
Environment variables override them: APERTUS_BASE_URL, APERTUS_API_KEY, APERTUS_MODEL_QUERIES, APERTUS_MODEL_BRIEF,
APERTUS_MODEL_AGENT.
Decision scoring uses APERTUS_DECISION_URL, APERTUS_DECISION_API_KEY and
APERTUS_DECISION_MODEL, independently of the chat provider.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from rag_model.pipeline_log import model_call

if TYPE_CHECKING:
    from haystack.components.generators.chat import OpenAIChatGenerator

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "data" / "settings.json"
ROLES = ("queries", "brief", "agent")  # B2, B4 and the orchestrator; one model per role
KEERA_BASE_URL = "https://gateway.keera.ch/api/v1"
CHAT_MODEL = "apertus-v1-5-8b"


def normalize_decision_url(value: str) -> str:
    """Accept an endpoint root or an explicit custom inference path."""
    parsed = urlsplit(value.strip())
    if parsed.path in ("", "/"):
        parsed = parsed._replace(path="/decide")
    return urlunsplit(parsed)


def load_settings() -> dict:
    s = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
    env = {
        "base_url": "APERTUS_BASE_URL",
        "api_key": "APERTUS_API_KEY",
        "model_queries": "APERTUS_MODEL_QUERIES",
        "model_brief": "APERTUS_MODEL_BRIEF",
        "model_agent": "APERTUS_MODEL_AGENT",
        "chat_model": "APERTUS_CHAT_MODEL",
        "decision_url": "APERTUS_DECISION_URL",
        "decision_api_key": "APERTUS_DECISION_API_KEY",
        "decision_model": "APERTUS_DECISION_MODEL",
    }
    for key, var in env.items():
        if os.environ.get(var):
            s[key] = os.environ[var]
    s.setdefault("base_url", KEERA_BASE_URL)
    if (
        s["base_url"].rstrip("/") == KEERA_BASE_URL
        and not os.environ.get("APERTUS_API_KEY")
        and os.environ.get("KEERA_API_KEY")
    ):
        s["api_key"] = os.environ["KEERA_API_KEY"]
    for role in ROLES:
        s[f"model_{role}"] = s.get(f"model_{role}") or s.get("chat_model") or CHAT_MODEL
    if s["base_url"].rstrip("/") == KEERA_BASE_URL:
        aliases = {
            "swiss-ai/Apertus-v1.5-8B": "apertus-v1-5-8b",
            "swiss-ai/Apertus-v1.5-70B": "apertus-v1-5-70b",
        }
        for key in ("chat_model", *(f"model_{role}" for role in ROLES)):
            if key in s:
                s[key] = aliases.get(s[key], s[key])
    if s.get("decision_url"):
        s["decision_url"] = normalize_decision_url(s["decision_url"])
    return s


def save_settings(update: dict) -> dict:
    s = load_settings()
    s.update({k: v for k, v in update.items() if v not in (None, "")})
    if s.get("decision_url"):
        s["decision_url"] = normalize_decision_url(s["decision_url"])
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))
    SETTINGS_FILE.chmod(0o600)
    return s


def public_settings() -> dict:
    """What the UI may see: everything except the key itself."""
    s = load_settings()
    key = s.pop("api_key", "")
    decision_key = s.pop("decision_api_key", "")
    return {
        **s,
        "key_set": bool(key),
        "key_last4": key[-4:] if key else "",
        "decision_key_set": bool(decision_key),
        "decision_key_last4": decision_key[-4:] if decision_key else "",
    }


def generator(
    role: str, llm_cfg: dict, schema: dict | None = None, tools: list | None = None
) -> OpenAIChatGenerator:
    """schema: JSON schema of the expected answer; used when the response format setting is json_schema.
    tools: Haystack tools the model may call; the answer is then free text or tool calls, no response format."""
    if role not in ROLES:
        raise ValueError(f"Unknown chat role: {role}")
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.utils import Secret

    s = load_settings()
    missing = [k for k in ("base_url", "api_key", f"model_{role}") if not s.get(k)]
    if missing:
        raise RuntimeError(
            f"Apertus API not configured, missing: {', '.join(missing)} "
            f"(set them in the UI settings or as APERTUS_* environment variables)"
        )
    kwargs = {"temperature": llm_cfg.get("temperature", 0)}
    if llm_cfg.get("max_tokens"):
        kwargs["max_tokens"] = llm_cfg["max_tokens"]
    fmt = llm_cfg.get("response_format")
    if tools:
        pass  # tool_choice "auto": with "required" Apertus can no longer plan in text and repeats its calls
    elif fmt == "json_schema" and schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": f"{role}_answer", "schema": schema},
        }
    elif fmt in ("json_object", "json_schema"):
        kwargs["response_format"] = {"type": "json_object"}
    # Streaming keeps data flowing while the model writes, so gateways with short timeouts do not cut long answers.
    stream = (lambda chunk: None) if llm_cfg.get("stream", True) else None
    return OpenAIChatGenerator(
        api_key=Secret.from_token(s["api_key"]),
        model=s[f"model_{role}"],
        api_base_url=s["base_url"],
        generation_kwargs=kwargs,
        streaming_callback=stream,
        tools=tools,
        timeout=llm_cfg.get("timeout", 300),
        max_retries=llm_cfg.get("max_retries", 2),
    )


def run_logged(llm, *, messages, **kwargs):
    """Record complete model-visible messages and raw replies before output cleanup."""
    tools = kwargs.get("tools", getattr(llm, "tools", None)) or []
    with model_call(
        "chat",
        model=getattr(llm, "model", None),
        endpoint=getattr(llm, "api_base_url", None),
        messages=[message.to_dict() for message in messages],
        tools=[
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ],
        generation_kwargs={
            **getattr(llm, "generation_kwargs", {}),
            **kwargs.get("generation_kwargs", {}),
        },
    ) as log_response:
        output = llm.run(messages=messages, **kwargs)
        log_response(output=output)
        return output


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
    data = json.loads(text[start : end + 1])
    return {list_key: data} if isinstance(data, list) else data
