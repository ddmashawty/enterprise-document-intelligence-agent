from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from doc_agent.config import get_settings

_max_tool_calls: ContextVar[int | None] = ContextVar("max_tool_calls", default=None)
_temperature: ContextVar[float | None] = ContextVar("temperature", default=None)


def effective_max_tool_calls() -> int:
    override = _max_tool_calls.get()
    if override is not None:
        return max(1, min(int(override), 10))
    return get_settings().max_tool_calls


def effective_temperature() -> float | None:
    return _temperature.get()


@contextmanager
def request_options(
    *,
    max_tool_calls: int | None = None,
    temperature: float | None = None,
) -> Iterator[None]:
    tokens = []
    if max_tool_calls is not None:
        tokens.append((_max_tool_calls, _max_tool_calls.set(max_tool_calls)))
    if temperature is not None:
        tokens.append((_temperature, _temperature.set(temperature)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
