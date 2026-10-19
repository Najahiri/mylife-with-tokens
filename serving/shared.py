"""Experimental decision and LM-head generation APIs sharing one trained backbone."""

import asyncio
from copy import deepcopy
import hmac
import json
import os
import time
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from serving.decision import DecisionRuntime, create_app as decision_app


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    messages: list[dict] = Field(min_length=1)
    tools: list[dict] | None = None
    tool_choice: str | dict = "auto"
    response_format: dict | None = None
    max_tokens: int = Field(default=512, ge=1)
    temperature: float = Field(default=0, ge=0, le=2)
    top_p: float = Field(default=1, gt=0, le=1)
    stream: bool = False
    stream_options: dict | None = None
    stop: str | list[str] | None = None
    n: int = Field(default=1, ge=1, le=1)


class GenerationOutputError(RuntimeError):
    pass


def structured_message(text, request):
    """Validate generated arguments/JSON after decoding; this is not constrained decoding."""
    from jsonschema import ValidationError, validate

    functions = {
        tool["function"]["name"]: tool["function"] for tool in request.tools or []
    }
    choice = request.tool_choice
    forced = (
        choice.get("function", {}).get("name") if isinstance(choice, dict) else None
    )
    candidate = text.strip()
    if "<|tools_prefix|>" in candidate:
        candidate = (
            candidate.split("<|tools_prefix|>", 1)[1]
            .split("<|tools_suffix|>", 1)[0]
            .strip()
        )
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(candidate)
    except ValueError:
        data = None
    calls = data if isinstance(data, list) else [data]
    is_call = bool(calls) and all(
        isinstance(call, dict) and "name" in call and "arguments" in call
        for call in calls
    )
    if choice != "none" and functions and (forced or choice == "required" or is_call):
        if not is_call or len(calls) != 1:
            raise GenerationOutputError(
                "LM head did not generate exactly one valid tool call"
            )
        call = calls[0]
        name, arguments = call["name"], call["arguments"]
        if name not in functions or (forced and name != forced):
            raise GenerationOutputError(
                "LM head generated a different tool from the requested action"
            )
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError as error:
                raise GenerationOutputError(
                    "Generated tool arguments are not JSON"
                ) from error
        try:
            validate(arguments, functions[name].get("parameters", {"type": "object"}))
        except ValidationError as error:
            raise GenerationOutputError(
                "Generated tool arguments do not match the tool schema"
            ) from error
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{uuid4().hex}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            ],
        }
    if request.response_format and request.response_format.get("type") in (
        "json_schema",
        "json_object",
    ):
        if not isinstance(data, dict):
            raise GenerationOutputError("LM head did not generate a JSON object")
        if request.response_format["type"] == "json_schema":
            try:
                validate(data, request.response_format["json_schema"]["schema"])
            except ValidationError as error:
                raise GenerationOutputError(
                    "Generated JSON does not match the requested schema"
                ) from error
        text = json.dumps(data, ensure_ascii=False)
    return {"role": "assistant", "content": text}


class SharedRuntime(DecisionRuntime):
    def __init__(self):
        super().__init__()  # Loads the adapter/backbone once; also used by /decide.
        from huggingface_hub import hf_hub_download

        template_model = os.environ.get(
            "CHAT_TEMPLATE_MODEL", "swiss-ai/Apertus-v1.5-8B"
        )
        self.template_revision = os.environ.get("CHAT_TEMPLATE_REVISION", "main")
        template = hf_hub_download(
            template_model, "chat_template.jinja", revision=self.template_revision
        )
        with open(template) as template_file:
            self.tokenizer.chat_template = template_file.read()
        self.chat_max_length = int(os.environ.get("CHAT_MAX_MODEL_LEN", "8192"))
        self.max_new_tokens = int(os.environ.get("CHAT_MAX_NEW_TOKENS", "1024"))

    def generate_chat(self, request):
        import torch

        if request.model != self.model_id:
            raise ValueError(f"This endpoint serves {self.model_id}")
        if request.max_tokens > self.max_new_tokens:
            raise ValueError(f"max_tokens must not exceed {self.max_new_tokens}")
        messages = deepcopy(request.messages)
        choice = request.tool_choice
        functions = {
            tool["function"]["name"]: tool["function"] for tool in request.tools or []
        }
        if isinstance(choice, dict):
            name = choice.get("function", {}).get("name")
            if choice.get("type") != "function" or name not in functions:
                raise ValueError("tool_choice must name a supplied function")
            instruction = f'Return only one JSON object with "name": "{name}" and "arguments": an object matching the supplied function schema.'
        elif choice == "required":
            if not functions:
                raise ValueError("tool_choice=required requires tools")
            instruction = 'Return only one JSON object with "name" and "arguments" for one supplied function.'
        elif choice == "none":
            instruction = "Answer the user in text. Do not call any tools."
        elif choice == "auto":
            instruction = 'If calling a tool, return one JSON object with "name" and "arguments". Otherwise answer in text.'
        else:
            raise ValueError("Unsupported tool_choice")
        if request.response_format:
            instruction += " Return a JSON object. Requested format: " + json.dumps(
                request.response_format
            )
        if messages[0].get("role") == "system":
            messages[0]["content"] = (
                str(messages[0].get("content", "")) + "\n" + instruction
            )
        else:
            messages.insert(0, {"role": "system", "content": instruction})
        for message in messages:
            if message.get("role") not in ("system", "user", "assistant", "tool"):
                raise ValueError("Unsupported message role")
            if message.get("content") is not None and not isinstance(
                message["content"], str
            ):
                raise ValueError("Shared generation supports text messages only")
            for call in message.get("tool_calls") or []:
                arguments = call.get("function", {}).get("arguments")
                if isinstance(arguments, str):
                    call["function"]["arguments"] = json.loads(arguments)
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tools=request.tools if choice != "none" else None,
            add_generation_prompt=True,
            tokenize=False,
            enable_thinking=False,
        )
        encoded = self.tokenizer(prompt, add_special_tokens=False, return_tensors="pt")
        input_length = encoded["input_ids"].shape[1]
        if input_length + request.max_tokens > self.chat_max_length:
            raise ValueError(
                f"Prompt plus max_tokens exceeds {self.chat_max_length} tokens; reduce context or max_tokens"
            )
        generation = dict(
            max_new_tokens=request.max_tokens,
            do_sample=request.temperature > 0,
            use_cache=True,
        )
        if request.temperature > 0:
            generation.update(temperature=request.temperature, top_p=request.top_p)
        # The exact same lock and adapter-loaded object serve decision and generation.
        with (
            self.lock,
            torch.inference_mode(),
            torch.autocast("cuda", dtype=torch.bfloat16),
        ):
            output = self.model.backbone.generate(
                input_ids=encoded["input_ids"].to(self.device),
                attention_mask=encoded["attention_mask"].to(self.device),
                **generation,
            )
        tokens = output[0, input_length:]
        text = self.tokenizer.decode(tokens, skip_special_tokens=False)
        for token in (self.tokenizer.eos_token, self.tokenizer.pad_token):
            if token:
                text = text.rstrip().removesuffix(token)
        stops = [request.stop] if isinstance(request.stop, str) else request.stop or []
        for stop in stops:
            if stop:
                text = text.split(stop, 1)[0]
        message = structured_message(text.strip(), request)
        reason = (
            "tool_calls"
            if message.get("tool_calls")
            else ("length" if len(tokens) >= request.max_tokens else "stop")
        )
        return {
            "id": f"chatcmpl-{uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_id,
            "checkpoint_revision": self.revision,
            "choices": [{"index": 0, "message": message, "finish_reason": reason}],
            "usage": {
                "prompt_tokens": input_length,
                "completion_tokens": len(tokens),
                "total_tokens": input_length + len(tokens),
            },
        }


async def completion_events(task, include_usage=False):
    # Keep the connection alive while generation is serialized on the shared GPU.
    while not task.done():
        await asyncio.wait({task}, timeout=10)
        if not task.done():
            yield ": keep-alive\n\n"
    try:
        completion = task.result()
    except Exception as error:
        yield (
            "data: "
            + json.dumps({"error": {"message": str(error), "type": "generation_error"}})
            + "\n\n"
        )
        yield "data: [DONE]\n\n"
        return
    header = {key: completion[key] for key in ("id", "created", "model")}
    header["object"] = "chat.completion.chunk"
    choice = completion["choices"][0]
    delta = dict(choice["message"])
    if delta.get("tool_calls"):
        delta["tool_calls"] = [
            {"index": index, **call} for index, call in enumerate(delta["tool_calls"])
        ]
    yield (
        "data: "
        + json.dumps(
            {**header, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
        )
        + "\n\n"
    )
    yield (
        "data: "
        + json.dumps(
            {
                **header,
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}
                ],
            }
        )
        + "\n\n"
    )
    if include_usage:
        yield (
            "data: "
            + json.dumps({**header, "choices": [], "usage": completion["usage"]})
            + "\n\n"
        )
    yield "data: [DONE]\n\n"


def create_app(runtime=None, decision_key=None, chat_key=None):
    app = decision_app(runtime, decision_key, runtime_factory=SharedRuntime)
    key = chat_key if chat_key is not None else os.environ.get("CHAT_API_KEY")
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        if (
            not key
            or not credentials
            or not hmac.compare_digest(credentials.credentials, key)
        ):
            raise HTTPException(401, "Invalid chat API key")

    @app.get("/v1/models", dependencies=[Depends(authenticate)])
    def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": app.state.runtime.model_id,
                    "object": "model",
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(authenticate)])
    async def chat(request: ChatRequest):
        task = asyncio.create_task(
            asyncio.to_thread(app.state.runtime.generate_chat, request)
        )
        if request.stream:
            return StreamingResponse(
                completion_events(
                    task, bool((request.stream_options or {}).get("include_usage"))
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        try:
            return await task
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except GenerationOutputError as error:
            raise HTTPException(502, str(error)) from error

    return app


app = create_app()
