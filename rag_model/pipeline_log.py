"""Immediate local pipeline traces, scoped to a conversation and user turn.

Each conversation gets a readable .log and an equivalent structured .jsonl in
data/logs/pipeline/. No credentials or HTTP authentication headers are recorded.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs" / "pipeline"
_current = ContextVar("pipeline_trace", default=None)
_lock = threading.Lock()
_sensitive = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "decision_api_key",
    "x_decision_api_key",
    "hf_token",
    "password",
    "secret",
    "access_token",
}


def _secret_values():
    values = [
        value
        for name, value in os.environ.items()
        if value and (name.endswith("_API_KEY") or name.endswith("_TOKEN"))
    ]
    try:
        settings = json.loads((ROOT / "data" / "settings.json").read_text())
        values.extend(settings.get(key, "") for key in ("api_key", "decision_api_key"))
    except (OSError, ValueError):
        pass
    return sorted(
        {v for v in values if isinstance(v, str) and v}, key=len, reverse=True
    )


def _readable(value, depth=0):
    """Keep newlines in prompts and page text readable, unlike JSON string escapes."""
    pad = "  " * depth
    if isinstance(value, dict):
        return (
            "\n".join(
                f"{pad}{key}:\n{_readable(item, depth + 1)}"
                for key, item in value.items()
            )
            or pad + "{}"
        )
    if isinstance(value, list):
        return (
            "\n".join(
                f"{pad}[{index}]\n{_readable(item, depth + 1)}"
                for index, item in enumerate(value)
            )
            or pad + "[]"
        )
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return "\n".join(pad + line for line in text.split("\n"))


class PipelineTrace:
    def __init__(self, session_id):
        self.session_id = session_id
        self.turn_id = uuid.uuid4().hex[:12]
        self.step = None
        self.sequence = 0
        self.secrets = _secret_values()
        filename = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
        self.path = LOG_DIR / filename
        self.failed = False

    def _redact(self, value):
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]"
                if str(key).lower().replace("-", "_") in _sensitive
                else self._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._redact(item) for item in value]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        text = str(value)
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return re.sub(r"(?i)\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", text)

    @contextmanager
    def bind(self):
        token = _current.set(self)
        try:
            yield
        finally:
            _current.reset(token)

    def write(self, event, **data):
        if self.failed:
            return
        try:
            with _lock:
                self.sequence += 1
                entry = self._redact(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "session_id": self.session_id,
                        "turn_id": self.turn_id,
                        "sequence": self.sequence,
                        "step": self.step,
                        "event": event,
                        **data,
                    }
                )
                self.path.parent.mkdir(parents=True, exist_ok=True)
                for suffix, text in (
                    (".jsonl", json.dumps(entry, ensure_ascii=False) + "\n"),
                    (".log", f"\n{'=' * 72}\n" + _readable(entry) + "\n"),
                ):
                    path = self.path.with_suffix(suffix)
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    with os.fdopen(fd, "a", encoding="utf-8") as output:
                        output.write(text)
        except Exception:
            self.failed = True
            logging.getLogger(__name__).exception(
                "Cannot write local pipeline log %s", self.path
            )


def record(event, **data):
    trace = _current.get()
    if trace is not None:
        trace.write(event, **data)


def set_step(step):
    trace = _current.get()
    if trace is not None:
        trace.step = step


@contextmanager
def model_call(kind, **request):
    """Pair each exact model request with its response/error, even during failures."""
    call_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    record(f"{kind}_request", call_id=call_id, **request)

    def response(**data):
        record(
            f"{kind}_response",
            call_id=call_id,
            elapsed_s=round(time.monotonic() - started, 3),
            **data,
        )

    try:
        yield response
    except Exception as error:
        record(
            f"{kind}_error",
            call_id=call_id,
            elapsed_s=round(time.monotonic() - started, 3),
            error_type=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
        raise
