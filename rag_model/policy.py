"""The decision model chooses generation capacity, never the agent's tool or action."""

from rag_model.decision import decide
from rag_model.llm import load_settings
from rag_model.pipeline_log import record


def select_model(messages, tools, *, purpose: str, generation_kwargs: dict) -> dict:
    settings = load_settings()
    models = [settings["model_8b"], settings["model_70b"]]
    if models[0] == models[1]:
        raise ValueError("Configure distinct 8B and 70B generation models")
    recent = []
    for message in messages[-3:]:
        role = getattr(message, "role", None)
        recent.append(
            {
                "role": getattr(role, "value", role),
                "text": (message.text or "")[:220],
                "tools": [c.tool_name for c in message.tool_calls],
            }
        )
    system = next(
        (
            m.text or ""
            for m in messages
            if getattr(getattr(m, "role", None), "value", None) == "system"
        ),
        "",
    )
    latest_user = next(
        (
            m.text or ""
            for m in reversed(messages)
            if getattr(getattr(m, "role", None), "value", None) == "user"
        ),
        "",
    )
    state = {
        "purpose": purpose,
        "instructions": system[:350],
        "latest_request": latest_user[:350],
        "message_count": len(messages),
        "context_characters": sum(len(m.text or "") for m in messages),
        "recent_messages": recent,
        "available_tools": [t.name for t in tools],
        "structured_output": bool(generation_kwargs.get("response_format")),
        "tool_choice": generation_kwargs.get("tool_choice", "auto"),
    }
    result = decide(
        state,
        "Which instruction-tuned Apertus model should handle THIS LLM call? Select 8B for simple, "
        "routine work and 70B when reasoning difficulty, ambiguity, long context, or correctness needs "
        "justify its higher latency and compute. Choose the model, not a tool or retrieval action.",
        [
            f"{models[0]}: 8B, fast and economical; simple conversation, straightforward edits and extraction.",
            f"{models[1]}: 70B, stronger reasoning; difficult source verification, multi-source synthesis and complex instructions.",
        ],
    )
    choice = {
        **result,
        "decision_model": result.get("model"),
        "model": models[result["prediction_index"]],
        "models": models,
        "purpose": purpose,
    }
    record(
        "model_selected",
        **choice,
        model_probabilities=[
            {"model": model, "probability": p}
            for model, p in zip(models, result["probabilities"])
        ],
    )
    return choice
