"""Client for the fine-tuned model, independent of the OpenAI chat API."""

import math
import time
from urllib.parse import urlsplit

import httpx

from rag_model.llm import load_settings, normalize_decision_url
from rag_model.pipeline_log import model_call, record


def decide(state, question: str, options: list[str], *, timeout: float = 300) -> dict:
    if (
        not question.strip()
        or not options
        or any(not isinstance(o, str) or not o.strip() for o in options)
    ):
        raise ValueError("A question and non-empty string options are required")
    settings = load_settings()
    if not settings.get("decision_url") or not settings.get("decision_api_key"):
        raise RuntimeError(
            "Configure APERTUS_DECISION_URL and APERTUS_DECISION_API_KEY"
        )
    payload = {"state": state, "question": question, "options": options}
    if settings.get("decision_model"):
        payload["model"] = settings["decision_model"]
    with model_call(
        "decision",
        endpoint=normalize_decision_url(settings["decision_url"]),
        request=payload,
    ) as log_response:
        return _request_decision(settings, payload, timeout, log_response)


def _request_decision(settings, payload, timeout, log_response):
    options = payload["options"]
    if timeout <= 0:
        raise ValueError("Decision timeout must be positive")
    url = normalize_decision_url(settings["decision_url"]).rstrip("/")
    is_hf = (urlsplit(url).hostname or "").endswith(".endpoints.huggingface.cloud")
    deadline = time.monotonic() + timeout
    attempt = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Decision service remained unavailable for {timeout:g} seconds. "
                "It may still be starting; check the HF endpoint status and container logs, then retry."
            )
        attempt += 1
        headers = {
            "X-Decision-API-Key": settings["decision_api_key"],
            "Authorization": f"Bearer {settings['decision_api_key']}",
        }
        if is_hf:
            # HF can hold a request during scale-up instead of immediately returning 503.
            headers["X-Scale-Up-Timeout"] = str(max(1, min(30, int(remaining))))
        response = httpx.post(url, json=payload, headers=headers, timeout=remaining)
        try:
            output = response.json()
        except ValueError:
            output = response.text
        log_response(http_status=response.status_code, output=output, attempt=attempt)
        if response.status_code != 503:
            response.raise_for_status()
            break
        delay = min(2 ** min(attempt, 4), 10)
        try:
            retry_after = float(response.headers.get("Retry-After", ""))
            if math.isfinite(retry_after) and retry_after > 0:
                delay = retry_after
        except ValueError:
            pass
        delay = max(0, min(delay, deadline - time.monotonic()))
        record(
            "decision_wait",
            attempt=attempt,
            http_status=503,
            delay_s=delay,
            message="Decision service is unavailable; waiting for it to become ready.",
        )
        time.sleep(delay)
    result = output
    index, probabilities = result.get("prediction_index"), result.get("probabilities")
    valid_index = type(index) is int and 0 <= index < len(options)
    valid_probs = (
        isinstance(probabilities, list)
        and len(probabilities) == len(options)
        and all(
            type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1
            for p in probabilities
        )
        and math.isclose(sum(probabilities), 1.0, abs_tol=1e-4)
    )
    if (
        not valid_index
        or not valid_probs
        or result.get("prediction") != options[index]
        or probabilities[index] != max(probabilities)
    ):
        raise ValueError(
            "Decision endpoint returned an invalid prediction or probability distribution"
        )
    if (
        settings.get("decision_model")
        and result.get("model") != settings["decision_model"]
    ):
        raise ValueError("Decision endpoint returned a different model than requested")
    return result
