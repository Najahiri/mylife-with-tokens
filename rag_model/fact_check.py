"""Ask the configured generation model whether facts follow from their cited pages."""

import json
from pathlib import Path

from haystack.dataclasses import ChatMessage
from jsonschema import Draft202012Validator
import yaml

from rag_model import config
from rag_model.llm import generator, parse_json, run_logged
from rag_model.pipeline_log import record

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "check_facts.yaml"


def check_facts(facts: list[str], sources: list[dict]) -> list[dict]:
    """Return one semantic verdict per fact; incomplete checks fail rather than guessing."""
    if not facts:
        return []
    if not sources:
        raise ValueError("Cited source pages are required for LLM fact checking")
    spec = yaml.safe_load(PROMPT.read_text(encoding="utf-8"))
    cfg = config.load()["llm"]
    schema = spec["schema"]
    checks = schema["properties"]["checks"]
    checks.update(minItems=len(facts), maxItems=len(facts))
    properties = checks["items"]["properties"]
    properties["fact_id"].update(minimum=1, maximum=len(facts))
    properties["sources"]["items"]["enum"] = [s["number"] for s in sources]
    validator = Draft202012Validator(schema)
    llm = generator("agent", {**cfg, "response_format": "json_schema"}, schema=schema)
    messages = [
        ChatMessage.from_system(spec["system"]),
        ChatMessage.from_user(
            json.dumps(
                {
                    "facts": [
                        {"fact_id": i, "text": fact} for i, fact in enumerate(facts, 1)
                    ],
                    "sources": sources,
                },
                ensure_ascii=False,
            )
        ),
    ]
    record(
        "fact_check_start",
        prompt_version=spec["version"],
        facts=facts,
        source_numbers=[s["number"] for s in sources],
    )
    attempts = max(1, cfg.get("json_attempts", 2))
    for attempt in range(1, attempts + 1):
        reply = run_logged(llm, messages=messages, purpose="fact_check")["replies"][0]
        try:
            if reply.meta.get("finish_reason") == "length":
                raise ValueError("Fact-check response was cut off")
            result = parse_json(reply.text or "")
            errors = list(validator.iter_errors(result))
            if errors:
                raise ValueError(
                    "Invalid fact-check response: " + errors[0].message[:300]
                )
            verdicts = result["checks"]
            if sorted(v["fact_id"] for v in verdicts) != list(range(1, len(facts) + 1)):
                raise ValueError("Return each fact_id exactly once")
            if any(
                not v["reason"].strip() or (v["supported"] and not v["sources"])
                for v in verdicts
            ):
                raise ValueError(
                    "Every verdict needs a reason; supported facts need a cited source"
                )
            verdicts = sorted(verdicts, key=lambda v: v["fact_id"])
            record("fact_check_result", facts=facts, checks=verdicts)
            return verdicts
        except (ValueError, TypeError) as error:
            record("fact_check_rejected", attempt=attempt, error=str(error))
            if attempt == attempts:
                raise ValueError(
                    "Could not complete the LLM fact check; no facts were accepted"
                ) from error
            messages.append(
                ChatMessage.from_user(
                    f"Your previous response was invalid: {error}. "
                    "Check the original facts and sources again. Return complete JSON matching the schema, "
                    "with each fact_id exactly once."
                )
            )
    raise AssertionError("No fact-check attempt was made")
