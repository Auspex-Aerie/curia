"""Turn-level sampling overrides and OpenRouter payload wiring."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.openrouter import query_model
from backend.sampling import current_max_tokens, current_temperature, sampling_overrides


def test_sampling_overrides_context():
    assert current_temperature() is None
    assert current_max_tokens() is None
    with sampling_overrides(temperature=0.2, max_tokens=512):
        assert current_temperature() == 0.2
        assert current_max_tokens() == 512
    assert current_temperature() is None
    assert current_max_tokens() is None


@pytest.mark.asyncio
async def test_query_model_forwards_overrides_to_complete():
    complete = AsyncMock(return_value={"content": "ok", "usage": {}, "model": "m"})

    with patch("backend.openrouter.OpenRouterClient") as client_cls:
        client_cls.return_value.complete = complete
        with sampling_overrides(temperature=0.4, max_tokens=128):
            await query_model("m", [{"role": "user", "content": "hi"}])

    kwargs = complete.await_args.kwargs
    assert kwargs["temperature"] == 0.4
    assert kwargs["max_tokens"] == 128


@pytest.mark.asyncio
async def test_query_model_explicit_kwargs_win_over_context():
    complete = AsyncMock(return_value={"content": "ok", "usage": {}, "model": "m"})

    with patch("backend.openrouter.OpenRouterClient") as client_cls:
        client_cls.return_value.complete = complete
        with sampling_overrides(temperature=0.1, max_tokens=10):
            await query_model(
                "m",
                [{"role": "user", "content": "hi"}],
                temperature=0.9,
                max_tokens=99,
            )

    kwargs = complete.await_args.kwargs
    assert kwargs["temperature"] == 0.9
    assert kwargs["max_tokens"] == 99
