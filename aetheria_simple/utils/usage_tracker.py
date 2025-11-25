"""Utilities for tracking token and latency usage across LLM calls."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, Mapping, Optional


@dataclass
class _ModelUsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    total_latency_seconds: float = 0.0


class LLMUsageTracker:
    """Thread-safe aggregator for per-model token and latency metrics."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stats: Dict[str, _ModelUsageStats] = {}

    def record(
        self,
        model_name: Optional[str],
        token_usage: Optional[Mapping[str, object]],
        latency_seconds: float,
    ) -> None:
        model_key = (model_name or "unknown").strip() or "unknown"
        prompt_tokens = self._extract_int(token_usage, "prompt_tokens")
        completion_tokens = self._extract_int(token_usage, "completion_tokens")
        total_tokens = self._extract_int(token_usage, "total_tokens")

        with self._lock:
            stats = self._stats.setdefault(model_key, _ModelUsageStats())
            stats.prompt_tokens += prompt_tokens
            stats.completion_tokens += completion_tokens
            stats.total_tokens += total_tokens or (prompt_tokens + completion_tokens)
            stats.call_count += 1
            stats.total_latency_seconds += max(latency_seconds, 0.0)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            per_model = {
                name: {
                    "prompt_tokens": stats.prompt_tokens,
                    "completion_tokens": stats.completion_tokens,
                    "total_tokens": stats.total_tokens,
                    "call_count": stats.call_count,
                    "total_latency_seconds": stats.total_latency_seconds,
                }
                for name, stats in self._stats.items()
            }

        total_prompt = sum(model["prompt_tokens"] for model in per_model.values())
        total_completion = sum(
            model["completion_tokens"] for model in per_model.values()
        )
        total_tokens = sum(model["total_tokens"] for model in per_model.values())
        total_latency = sum(
            model["total_latency_seconds"] for model in per_model.values()
        )
        total_calls = sum(model["call_count"] for model in per_model.values())

        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_latency_seconds": total_latency,
            "total_calls": total_calls,
            "by_model": per_model,
        }

    @staticmethod
    def _extract_int(
        token_usage: Optional[Mapping[str, object]], key: str
    ) -> int:
        if not token_usage:
            return 0
        value = token_usage.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        alt_key = f"{key}_count"
        value = token_usage.get(alt_key)
        if isinstance(value, (int, float)):
            return int(value)
        return 0
