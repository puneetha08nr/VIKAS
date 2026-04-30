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

_PROVIDER_KEY_ATTR: dict[str, str] = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "gemini_api_key",
}


class LLMUnavailableError(Exception):
    pass


class LLMRouter:
    def __init__(self, config_path: Path, cost_tracker: "CostTracker", settings: Any) -> None:
        with open(config_path) as fh:
            self._config: dict = yaml.safe_load(fh)
        self._cost_tracker = cost_tracker
        self._settings = settings
        # Updated after each complete() call — reflects the most recent LLM call's usage
        self.last_tokens_used: int = 0
        self.last_cost_usd: float = 0.0

    def _key_for(self, provider: str) -> str:
        attr = _PROVIDER_KEY_ATTR.get(provider, "")
        return getattr(self._settings, attr, "") if attr else ""

    async def complete(
        self,
        prompt: str,
        tier: str,
        org_id: str,
        run_id: str,
        db: AsyncSession,
        **kwargs: Any,
    ) -> str:
        """Call the LLM for the given tier, falling back on failure.

        Skips any non-ollama provider whose API key is missing.
        Ollama requires no API key — routes via OLLAMA_BASE_URL instead.
        """
        within_limit = await self._cost_tracker.check_limit(
            org_id, self._settings.daily_cost_limit_usd, db
        )
        if not within_limit:
            raise LLMUnavailableError(f"Daily cost limit exceeded for org {org_id}")

        tier_cfg = self._config["tiers"][tier]
        providers = [tier_cfg["primary"]] + tier_cfg.get("fallback", [])
        max_tokens: int = tier_cfg.get("max_tokens", 4096)
        temperature: float = kwargs.pop("temperature", tier_cfg.get("temperature", 0.7))

        last_error: Exception | None = None
        attempted = 0
        for provider in providers:
            provider_name: str = provider.get("provider", "")
            model: str = provider["model"]

            call_kwargs: dict[str, Any] = {}
            if provider_name == "ollama":
                call_kwargs["api_base"] = self._settings.ollama_base_url
            else:
                api_key = self._key_for(provider_name)
                if not api_key:
                    logger.warning("Skipping provider %s — API key not configured", provider_name)
                    continue
                call_kwargs["api_key"] = api_key

            attempted += 1
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **call_kwargs,
                    **kwargs,
                )
                content: str = response.choices[0].message.content or ""
                tokens_in: int = response.usage.prompt_tokens
                tokens_out: int = response.usage.completion_tokens
                cost = 0.0 if provider_name == "ollama" else self.get_cost(model, tokens_in, tokens_out)

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
                logger.warning("LLM provider %s failed: %s", model, exc)
                last_error = exc
                continue

        if attempted == 0:
            logger.warning("No providers available for tier '%s' — returning mock response", tier)
            self.last_tokens_used = 100
            self.last_cost_usd = 0.0
            return _MOCK_RESPONSE

        raise LLMUnavailableError(
            f"All providers failed for tier '{tier}'"
        ) from last_error

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
