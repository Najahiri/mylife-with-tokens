"""An LLM decides whether this user turn needs indexed source retrieval."""

import json
from pathlib import Path

from haystack.dataclasses import ChatMessage
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import yaml

from rag_model import config
from rag_model.llm import generator, parse_json, run_logged
from rag_model.pipeline_log import record

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "retrieval.yaml"


def assess_retrieval(request: str, context: dict, *, on_chunk=None) -> dict:
    spec = yaml.safe_load(PROMPT.read_text(encoding="utf-8"))
    cfg = config.load()["llm"]
    llm = generator(
        "agent",
        {**cfg, "response_format": "json_schema"},
        schema=spec["schema"],
        on_chunk=on_chunk,
    )
    messages = [
        ChatMessage.from_system(spec["system"]),
        ChatMessage.from_user(
            json.dumps({"request": request, "context": context}, ensure_ascii=False)
        ),
    ]
    attempts = max(1, cfg.get("json_attempts", 2))
    for attempt in range(1, attempts + 1):
        if on_chunk:
            on_chunk(None)
        output = run_logged(llm, messages=messages, purpose="retrieval_assessment")
        if on_chunk:
            on_chunk(None)
        reply = output["replies"][0]
        try:
            if reply.meta.get("finish_reason") == "length":
                raise ValueError("Retrieval assessment was cut off")
            result = parse_json(reply.text or "")
            Draft202012Validator(spec["schema"]).validate(result)
            if not result["reason"].strip():
                raise ValueError("Provide a reason for the retrieval assessment")
            record("retrieval_assessed", **result, routing=output.get("routing"))
            return {**result, "routing": output.get("routing")}
        except (ValueError, TypeError, ValidationError) as error:
            record("retrieval_assessment_rejected", attempt=attempt, error=str(error))
            if attempt == attempts:
                raise ValueError(
                    "The LLM could not determine whether retrieval is needed"
                ) from error
            messages.append(
                ChatMessage.from_user(
                    f"Invalid assessment: {error}. Return JSON matching the schema."
                )
            )
