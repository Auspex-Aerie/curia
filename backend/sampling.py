"""Per-turn sampling overrides for model calls (directive plumbing).

``@temp`` / ``@maxtokens`` are parsed into ``ParsedDirectives`` and applied for
the duration of a full turn via contextvars so every ``query_model`` call in
the arena sees the same overrides without threading kwargs through every mode
runner.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_temperature: ContextVar[Optional[float]] = ContextVar("curia_temperature", default=None)
_max_tokens: ContextVar[Optional[int]] = ContextVar("curia_max_tokens", default=None)


@contextmanager
def sampling_overrides(
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Iterator[None]:
    """Install sampling overrides for the current async task for the turn."""
    temp_token = _temperature.set(temperature)
    max_token = _max_tokens.set(max_tokens)
    try:
        yield
    finally:
        _temperature.reset(temp_token)
        _max_tokens.reset(max_token)


def current_temperature() -> Optional[float]:
    return _temperature.get()


def current_max_tokens() -> Optional[int]:
    return _max_tokens.get()
