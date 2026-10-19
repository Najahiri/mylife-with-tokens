"""Evaluation-only adaptations of the real pipeline; no application files are changed."""

import copy
import json
import os
import time
import uuid


def run_pipeline(job, directory):
    os.environ["HAYSTACK_TELEMETRY_ENABLED"] = "false"
    from haystack.dataclasses import ChatMessage
    import httpx
    from rag_model import config, llm, pipeline_log
    from eval.corpus import RemoteSearcher

    settings = job["runtime_settings"]
    frozen = job["pipeline_config"]
    choice = job["configuration"]
    config.load = lambda: copy.deepcopy(frozen)
    llm.load_settings = lambda: copy.deepcopy(settings)
    pipeline_log.LOG_DIR = directory / "pipeline"
    original_generator = llm.generator

    def generator(role, llm_cfg, *args, **kwargs):
        component = original_generator(role, llm_cfg, *args, **kwargs)
        original_run = component.run

        def run(*args, **run_kwargs):
            run_kwargs["generation_kwargs"] = {
                **run_kwargs.get("generation_kwargs", {}),
                "stream_options": {"include_usage": True},
            }
            return original_run(*args, **run_kwargs)

        component.run = run
        return component

    llm.generator = generator
    from rag_model import policy, decision

    policy.load_settings = decision.load_settings = llm.load_settings

    # Count every HF HTTP attempt, including explicit 503/startup retries.
    original_post = httpx.post

    def measured_post(url, **kwargs):
        call_id = uuid.uuid4().hex
        started = time.monotonic()
        model = kwargs.get("json", {}).get("model") or settings.get("decision_model")
        pipeline_log.record(
            "decision_http_request",
            call_id=call_id,
            model=model,
            purpose="capacity_routing",
            endpoint=str(url),
        )
        try:
            response = original_post(url, **kwargs)
            try:
                body = response.json()
            except ValueError:
                body = {}
            pipeline_log.record(
                "decision_http_response",
                call_id=call_id,
                elapsed_s=time.monotonic() - started,
                http_status=response.status_code,
                usage=body.get("usage") if isinstance(body, dict) else None,
                model_revision=body.get("revision") if isinstance(body, dict) else None,
            )
            return response
        except Exception as error:
            pipeline_log.record(
                "decision_http_error",
                call_id=call_id,
                elapsed_s=time.monotonic() - started,
                error=str(error),
            )
            raise

    decision.httpx.post = measured_post
    if choice["generation_policy"] == "fixed":
        policy.select_model = lambda *args, **kwargs: {
            "model": choice["generation_model"],
            "purpose": kwargs.get("purpose"),
            "decision_model": None,
        }
    elif choice["id"].startswith("llm_router_"):
        router_model = choice["decision_model"]

        def route(state, question, options, **kwargs):
            schema = {
                "type": "object",
                "additionalProperties": False,
                "required": ["prediction_index"],
                "properties": {"prediction_index": {"type": "integer", "enum": [0, 1]}},
            }
            component = generator(
                "agent",
                {**frozen["llm"], "response_format": "json_schema"},
                schema=schema,
            )
            messages = [
                ChatMessage.from_system(
                    question
                    + " Return only the selected zero-based prediction_index as JSON."
                ),
                ChatMessage.from_user(
                    json.dumps({"state": state, "options": options}, ensure_ascii=False)
                ),
            ]
            for attempt in range(frozen["llm"].get("json_attempts", 2)):
                with pipeline_log.model_call(
                    "chat",
                    model=router_model,
                    purpose="capacity_routing",
                    messages=[message.to_dict() for message in messages],
                ) as response:
                    output = component.run(
                        messages=messages, generation_kwargs={"model": router_model}
                    )
                    response(output=output)
                reply = output["replies"][0]
                try:
                    index = llm.parse_json(reply.text or "").get("prediction_index")
                    if (
                        not isinstance(index, int)
                        or isinstance(index, bool)
                        or index not in (0, 1)
                        or reply.meta.get("finish_reason") == "length"
                    ):
                        raise ValueError("Router must return prediction_index 0 or 1")
                    return {
                        "prediction_index": index,
                        "prediction": options[index],
                        "probabilities": [None, None],
                        "model": router_model,
                    }
                except (ValueError, AttributeError):
                    if attempt + 1 == frozen["llm"].get("json_attempts", 2):
                        raise
                    messages.append(
                        ChatMessage.from_user(
                            "Return complete JSON with prediction_index 0 or 1."
                        )
                    )

        policy.decide = route

    # Imports occur after generator/config adaptation so every call uses the same policy.
    from rag_model import agent, brief, fact_check, retrieval

    agent.generator = brief.generator = fact_check.generator = retrieval.generator = (
        generator
    )

    prompts = job["prompts_directory"]
    from pathlib import Path

    brief.PROMPTS = agent.PROMPTS = Path(prompts)
    retrieval.PROMPT = Path(prompts) / "retrieval.yaml"
    fact_check.PROMPT = Path(prompts) / "check_facts.yaml"
    agent.INDEX_DB = brief.INDEX_DB = job["corpus_database"]
    agent.SESSIONS = directory / "sessions"

    def write_trace(trace):
        path = directory / "brief_trace.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, default=str))
        return str(path)

    agent.write_trace = brief.write_trace = write_trace
    searcher = RemoteSearcher(job["corpus_address"], job["corpus_authkey"])
    session = agent.Session(id=job["id"])
    count = 0
    with (directory / "events.jsonl").open("a") as output:
        for event in agent.turn(session, job["task"]["question"], searcher):
            output.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            output.flush()
            count += 1
    return {"events": count, "presentation_items": len(session.items)}
