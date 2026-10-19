"""Decision-model policy; chat is responsible only for arguments and answers."""

from rag_model.decision import decide
from rag_model.pipeline_log import record


def select_action(state: dict, tools: list) -> dict:
    names, options = [], []
    blocked = set(state.get("blocked_actions", []))
    unread = max(0, state["pages"] - state["read_pages"])
    pending = state.get("unfinished_step")
    must_finish = state.get("research_in_progress", False) and (
        (pending == "read_pages" and unread > 0 and "read_pages" not in blocked)
        or (
            pending == "add_items"
            and state["read_pages"] > 0
            and "add_items" not in blocked
        )
    )
    remaining = state.get("remaining_steps")
    reserved = None
    if remaining == 1 and state.get("turn_has_work", False):
        reserved = "answer"
        must_finish = False
    elif (
        remaining == 2
        and must_finish
        and state["read_pages"] > 0
        and "add_items" not in blocked
    ):
        reserved = "add_items"
    for tool in tools:
        name = tool.name
        if reserved is not None and name != reserved:
            continue
        if name in blocked:
            continue
        if name == "search" and must_finish:
            continue
        if name == "read_pages" and (
            not unread or (must_finish and pending == "add_items")
        ):
            continue
        if name == "add_items" and not state["read_pages"]:
            continue
        if name in ("remove_items", "edit_item") and not state["items"]:
            continue
        names.append(name)
        options.append(f"{name}: {tool.description[:180]}")
    if (
        reserved == "answer"
        or (reserved is None and not must_finish and "answer" not in blocked)
        or not names
    ):
        names.append("answer")
        options.append(
            "answer: Finish this turn with a user-facing response using the available evidence."
        )
    record(
        "action_options",
        actions=names,
        blocked_actions=sorted(blocked),
        research_in_progress=state.get("research_in_progress", False),
        unfinished_step=pending,
        remaining_steps=remaining,
        reserved_action=reserved,
    )
    result = decide(
        state,
        "Choose the single best next action to fulfil the user's request. "
        "For research and slides: search, read relevant pages, add checked items, then answer. "
        "Search results alone do not create slides. Complete unfinished work rather than "
        "repeating the same search; for editing requests, choose the requested edit.",
        options,
    )
    return {**result, "action": names[result["prediction_index"]], "actions": names}


def validate_generation(action: str, calls: list) -> None:
    """Never execute a chat-selected action different from the decision result."""
    if action == "answer":
        if calls:
            raise ValueError(
                "Chat returned tool calls when the decision model selected an answer"
            )
    elif len(calls) != 1 or calls[0].tool_name != action:
        raise ValueError(
            f"Chat must generate exactly one {action} call selected by the decision model"
        )


def rank_candidates(
    state: dict, candidates: list[dict], limit: int = 8
) -> tuple[list[int], dict | None]:
    """Rank a retrieval shortlist in one decision call; retain remaining retrieval order."""
    count = min(len(candidates), limit)
    if count < 2:
        return list(range(len(candidates))), None
    options = [
        f"{index + 1}. {page['title'][:40]} | {page['website'][:20]} | {page['snippet'][:60]}"
        for index, page in enumerate(candidates[:count])
    ]
    result = decide(
        state,
        "Which research candidate is most relevant to the user's request?",
        options,
    )
    ordered = sorted(range(count), key=lambda index: -result["probabilities"][index])
    record(
        "retrieval_ranking",
        state=state,
        candidates=candidates,
        ranked_candidates=count,
        order=ordered + list(range(count, len(candidates))),
        decision=result,
    )
    return ordered + list(range(count, len(candidates))), {
        **result,
        "ranked_candidates": count,
        "order": ordered,
        "candidate_ids": [
            page.get("page_id", str(index))
            for index, page in enumerate(candidates[:count])
        ],
    }
