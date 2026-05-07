import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import litellm
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

_MOCK_RESPONSE = (
    "MOCK RESPONSE: No API keys configured. "
    "Add keys to .env and set MOCK_LLM=false to enable real LLM calls."
)


def _build_provider_configs(settings: Any) -> dict[str, dict[str, Any]]:
    return {
        "ollama": {
            "fast":      "ollama/mistral:7b-instruct",
            "standard":  "ollama/mistral:7b-instruct",
            "advanced":  "ollama/mistral:7b-instruct",
            "api_base":  settings.ollama_base_url,
            "api_key":   None,
            "cost_free": True,
        },
        "google": {
            "fast":      "gemini/gemini-2.0-flash-lite",
            "standard":  "gemini/gemini-2.0-flash",
            "advanced":  "gemini/gemini-2.5-pro",
            "api_base":  None,
            "api_key":   settings.gemini_api_key,
            "cost_free": False,
        },
        "anthropic": {
            "fast":      "claude-haiku-4-5-20251001",
            "standard":  "claude-sonnet-4-6",
            "advanced":  "claude-opus-4-7",
            "api_base":  None,
            "api_key":   settings.anthropic_api_key,
            "cost_free": False,
        },
        "openai": {
            "fast":      "gpt-4o-mini",
            "standard":  "gpt-4o",
            "advanced":  "o1",
            "api_base":  None,
            "api_key":   settings.openai_api_key,
            "cost_free": False,
        },
    }


class LLMUnavailableError(Exception):
    pass


class LLMRouter:
    def __init__(self, config_path: Path, cost_tracker: "CostTracker", settings: Any) -> None:
        with open(config_path) as fh:
            self._config: dict = yaml.safe_load(fh)
        self._cost_tracker = cost_tracker
        self._settings = settings

        all_configs = _build_provider_configs(settings)
        provider = settings.llm_provider.lower()
        if provider not in all_configs:
            logger.warning("Unknown LLM_PROVIDER '%s', falling back to 'ollama'", provider)
            provider = "ollama"
        self._provider = provider
        self._cfg = all_configs[provider]
        logger.info("LLMRouter initialised — provider: %s", provider)

        self.last_tokens_used: int = 0
        self.last_cost_usd: float = 0.0

    async def complete(
        self,
        prompt: str,
        tier: str,
        org_id: str,
        run_id: str,
        db: AsyncSession,
        **kwargs: Any,
    ) -> str:
        within_limit = await self._cost_tracker.check_limit(
            org_id, self._settings.daily_cost_limit_usd, db
        )
        if not within_limit:
            raise LLMUnavailableError(f"Daily cost limit exceeded for org {org_id}")

        tier_cfg = self._config["tiers"][tier]
        max_tokens: int = tier_cfg.get("max_tokens", 4096)
        temperature: float = kwargs.pop("temperature", tier_cfg.get("temperature", 0.7))

        model: str = self._cfg[tier]
        api_key: str | None = self._cfg.get("api_key") or None
        api_base: str | None = self._cfg.get("api_base") or None

        if not self._cfg["cost_free"] and not api_key:
            logger.warning(
                "Provider '%s' has no API key configured — returning mock response",
                self._provider,
            )
            self.last_tokens_used = 100
            self.last_cost_usd = 0.0
            return _MOCK_RESPONSE

        call_kwargs: dict[str, Any] = {}
        if api_key:
            call_kwargs["api_key"] = api_key
        if api_base:
            call_kwargs["api_base"] = api_base

        try:
            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **call_kwargs,
                **kwargs,
            )
            content: str = response.choices[0].message.content or ""  # type: ignore[union-attr]
            tokens_in: int = response.usage.prompt_tokens  # type: ignore[union-attr]
            tokens_out: int = response.usage.completion_tokens  # type: ignore[union-attr]
            cost = 0.0 if self._cfg["cost_free"] else self.get_cost(model, tokens_in, tokens_out)

            await self._cost_tracker.add(
                org_id=org_id,
                run_id=run_id,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                db=db,
            )
            self.last_tokens_used = tokens_in + tokens_out
            self.last_cost_usd = cost
            return content

        except LLMUnavailableError:
            raise
        except Exception as exc:
            logger.warning("LLM %s/%s failed: %s", self._provider, model, exc)
            raise LLMUnavailableError(
                f"Provider '{self._provider}' failed for tier '{tier}': {exc}"
            ) from exc

    def get_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        try:
            return float(
                litellm.completion_cost(
                    model=model,
                    prompt_tokens=tokens_in,
                    completion_tokens=tokens_out,
                )
            )
        except Exception:
            return 0.0
