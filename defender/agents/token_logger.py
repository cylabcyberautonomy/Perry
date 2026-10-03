"""Per-call token/cost logging for the LLM defender (one JSON row per call to token_usage.json)."""
from __future__ import annotations

import json
import threading
from datetime import datetime

_WRITE_LOCK = threading.Lock()


def header_float(headers: dict, key: str) -> float | None:
    """Parse a numeric proxy header, or None if absent or unparseable."""
    if not headers:
        return None
    value = headers.get(key) or headers.get(key.lower()) or headers.get(key.title())
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TokenUsageLogger:
    def __init__(self, path: str):
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def record(
        self,
        *,
        call_type: str,
        model: str,
        step: int,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        reasoning_tokens: int = 0,
        response_id: str | None = None,
        wall_clock_latency_ms: float | None = None,
        cost: float | None = None,
        provider: str | None = None,
        finish_reason: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        litellm_response_cost: float | None = None,
        served_model: str | None = None,
    ) -> None:
        # input_tokens and output_tokens are LangChain totals. Never sum a detail count onto its total.
        record = {
            "timestamp": datetime.now().isoformat(),
            "call_type": call_type,
            "model": model,
            "served_model": served_model,
            "step": step,
            "response_id": response_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "reasoning_tokens": reasoning_tokens,
            "wall_clock_latency_ms": wall_clock_latency_ms,
            "cost": cost,
            "provider": provider,
            "finish_reason": finish_reason,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "litellm_response_cost": litellm_response_cost,
        }
        line = json.dumps(record) + "\n"
        with _WRITE_LOCK:
            with open(self._path, "a") as f:
                f.write(line)
