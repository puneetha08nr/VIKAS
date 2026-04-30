import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_router import LLMRouter, LLMUnavailableError
from core.cost_tracker import CostTracker

# ── helpers ───────────────────────────────────────────────────────────────────

TIERS_YAML = {
    "tiers": {
        "fast": {
            "primary": {"provider": "openai", "model": "gpt-4o-mini"},
            "fallback": [{"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}],
            "max_tokens": 4096,
            "temperature": 0.3,
        }
    },
    "cost_limits": {"per_org_daily_usd": 50.0},
}


def _mock_response(content: str = "hello", tokens_in: int = 10, tokens_out: int = 5) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.usage.prompt_tokens = tokens_in
    resp.usage.completion_tokens = tokens_out
    return resp


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "model_tiers.yaml"
    cfg.write_text(yaml.dump(TIERS_YAML))
    return cfg


@pytest.fixture
def mock_tracker() -> MagicMock:
    tracker = MagicMock(spec=CostTracker)
    tracker.check_limit = AsyncMock(return_value=True)
    tracker.add = AsyncMock()
    return tracker


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.daily_cost_limit_usd = 50.0
    return s


@pytest.fixture
def router(config_file: Path, mock_tracker: MagicMock, mock_settings: MagicMock) -> LLMRouter:
    return LLMRouter(config_file, mock_tracker, mock_settings)


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_primary_provider_returns_content(
    router: LLMRouter, mock_tracker: MagicMock, db: AsyncMock
) -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_mock_response("hi")):
        result = await router.complete("say hi", "fast", "org-1", "run-1", db)

    assert result == "hi"


async def test_primary_provider_records_cost(
    router: LLMRouter, mock_tracker: MagicMock, db: AsyncMock
) -> None:
    with patch("litellm.acompletion", new_callable=AsyncMock, return_value=_mock_response()):
        await router.complete("ping", "fast", "org-1", "run-1", db)

    mock_tracker.add.assert_called_once()
    call_kwargs = mock_tracker.add.call_args.kwargs
    assert call_kwargs["tokens_in"] == 10
    assert call_kwargs["tokens_out"] == 5
    assert call_kwargs["org_id"] == "org-1"


async def test_fallback_fires_on_primary_failure(
    router: LLMRouter, mock_tracker: MagicMock, db: AsyncMock
) -> None:
    call_count = 0

    async def side_effect(**kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("primary down")
        return _mock_response("fallback ok")

    with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=side_effect):
        result = await router.complete("ping", "fast", "org-1", "run-1", db)

    assert result == "fallback ok"
    assert call_count == 2


async def test_all_providers_fail_raises_llm_unavailable(
    router: LLMRouter, db: AsyncMock
) -> None:
    with patch(
        "litellm.acompletion", new_callable=AsyncMock, side_effect=ConnectionError("all down")
    ):
        with pytest.raises(LLMUnavailableError, match="All providers failed"):
            await router.complete("ping", "fast", "org-1", "run-1", db)


async def test_daily_limit_exceeded_raises_before_llm_call(
    router: LLMRouter, mock_tracker: MagicMock, db: AsyncMock
) -> None:
    mock_tracker.check_limit = AsyncMock(return_value=False)

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        with pytest.raises(LLMUnavailableError, match="Daily cost limit exceeded"):
            await router.complete("ping", "fast", "org-1", "run-1", db)

    mock_llm.assert_not_called()


async def test_get_cost_returns_float(router: LLMRouter) -> None:
    with patch("litellm.completion_cost", return_value=0.0025):
        cost = router.get_cost("gpt-4o-mini", 100, 50)
    assert cost == pytest.approx(0.0025)


async def test_get_cost_returns_zero_on_error(router: LLMRouter) -> None:
    with patch("litellm.completion_cost", side_effect=Exception("unknown model")):
        cost = router.get_cost("unknown-model", 100, 50)
    assert cost == 0.0
