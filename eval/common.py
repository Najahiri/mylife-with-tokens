"""Fixed-model preparation/judging calls, kept separate from pipeline telemetry."""

import json
from pathlib import Path
import threading
import time
import uuid

from haystack.dataclasses import ChatMessage
from jsonschema import Draft202012Validator

from rag_model.llm import generator, parse_json

ROOT = Path(__file__).resolve().parent.parent
_write_lock = threading.Lock()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def append_jsonl(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path):
    path = Path(path)
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if path.exists()
        else []
    )


def fixed_json_call(*, model, system, payload, schema, settings, log_path, purpose):
    """No capacity routing here: preparation and judges must have fixed identities."""
    cfg = {
        "temperature": 0,
        "max_tokens": settings.get("max_tokens", 4500),
        "timeout": settings.get("timeout_seconds", 120),
        "max_retries": 0,
        "stream": True,
        "response_format": "json_schema",
    }
    component = generator("agent", cfg, schema=schema)
    messages = [
        ChatMessage.from_system(system),
        ChatMessage.from_user(json.dumps(payload, ensure_ascii=False)),
    ]
    for attempt in range(1, settings.get("output_repair_attempts", 2) + 1):
        call_id = uuid.uuid4().hex
        started = time.monotonic()
        entry = {
            "call_id": call_id,
            "phase": "preparation",
            "purpose": purpose,
            "model": model,
            "attempt": attempt,
            "started_at_unix": time.time(),
            "system_prompt": system,
            "schema": schema,
            "input": payload,
        }
        append_jsonl(log_path, {**entry, "event": "request"})
        reply = None
        try:
            output = component.run(
                messages=messages,
                generation_kwargs={
                    "model": model,
                    "stream_options": {"include_usage": True},
                },
            )
            reply = output["replies"][0]
            append_jsonl(
                log_path,
                {
                    **entry,
                    "event": "response",
                    "elapsed_s": time.monotonic() - started,
                    "reply": reply.to_dict(),
                    "usage": reply.meta.get("usage"),
                },
            )
            if reply.meta.get("finish_reason") == "length":
                raise ValueError("Structured output was truncated")
            result = parse_json(reply.text or "")
            errors = list(Draft202012Validator(schema).iter_errors(result))
            if errors:
                raise ValueError(errors[0].message[:300])
            return result
        except Exception as error:
            append_jsonl(
                log_path,
                {
                    "event": "error",
                    "call_id": call_id,
                    "phase": "preparation",
                    "purpose": purpose,
                    "model": model,
                    "elapsed_s": time.monotonic() - started,
                    "error": str(error),
                    "attempt": attempt,
                },
            )
            # Provider/transport failures are visible and are not disguised as JSON repair attempts.
            if reply is None or attempt == settings.get("output_repair_attempts", 2):
                raise
            messages.append(
                ChatMessage.from_user(
                    f"Invalid response: {error}. Return complete JSON matching the schema."
                )
            )
